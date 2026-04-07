#!/usr/bin/env python3
"""
readme_cache.py — Persistent README cache with conditional refetch.

Why this exists
---------------
The enricher used to refetch every project's README from
raw.githubusercontent.com on every run — ~2,300 HTTP fetches every six
hours of cron, with no caching, no conditional requests. Wasteful and
slow, especially since the vast majority of READMEs don't change between
runs.

Design — two tiers
------------------
1. **Index** (`data/readme-cache.json`, committed to git):
   one entry per repo with metadata only — etag, sha, last_modified,
   fetched, branch, filename, size. ~2,300 entries × ~300 bytes ≈ 700KB.
   Lives in git so CI starts each run with the cache primed and only
   refetches what actually changed.

2. **Bytes** (`data/readmes/<owner>__<repo>.md`, gitignored):
   the full README text. ~2,300 × ~20KB ≈ 45MB. Too big for git, fine
   on disk and in CI's `actions/cache`.

Refresh logic
-------------
- Have an ETag → conditional GET (`If-None-Match`). 304 → use cached.
  200 → store new bytes + new ETag.
- No ETag → unconditional GET, store bytes + ETag.
- 404 on the recorded branch/filename → fall back to the same probe
  ladder the legacy fetcher used (master/main × README.md/README.rst/etc),
  store the working combo.
- Total network failure → return cached bytes if any, else None.

Public API
----------
    cache = ReadmeCache()                    # opens data/readme-cache.json
    text = cache.get('brendoncarroll/webfs')  # bytes (cached or fresh)
    cache.flush()                             # persist index to disk
    with cache:                               # auto-flush on exit
        for repo in repos:
            text = cache.get(repo)
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = 'ex-od-us-readme-cache'

# Probe ladder for first-time discovery of a repo's README. Order matters
# slightly — README.md catches the vast majority on its own.
DEFAULT_BRANCHES = ('master', 'main')
DEFAULT_FILENAMES = ('README.md', 'readme.md', 'README.rst', 'README',
                     'Readme.md', 'README.MD', 'README.markdown')


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _bytes_filename(owner_repo: str) -> str:
    """`owner/repo` → `owner__repo.md`. Slashes are illegal on most FSes.

    Other separator characters that could legally appear in repo names
    (`.`, `-`, `_`) are left alone, since `__` is rare in real repos.
    """
    return owner_repo.replace('/', '__') + '.md'


class ReadmeCache:
    """Persistent README cache with conditional refetch."""

    def __init__(self,
                 index_path: str | Path = 'data/readme-cache.json',
                 bytes_dir: str | Path = 'data/readmes',
                 timeout_s: float = 15.0):
        self.index_path = Path(index_path)
        self.bytes_dir = Path(bytes_dir)
        self.timeout_s = timeout_s
        self.bytes_dir.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        # _dirty must be initialized *before* _load_index, because the
        # legacy-schema normalization sets it to True if any entry was
        # cleaned up. If we initialized after, we'd clobber that signal.
        self._dirty = False
        self._index: dict[str, dict] = self._load_index()

        # Stats — useful for the CI summary line.
        self.stats = {
            'hits_304': 0,        # ETag matched, file unchanged
            'hits_local': 0,      # used cached bytes without contacting network
            'fetches_new': 0,     # full GET, no prior ETag
            'fetches_updated': 0, # full GET, ETag mismatched
            'fetches_failed': 0,  # all probes returned 4xx/5xx/network err
        }

    # ---------------------------------------------------------------- index

    # Fields preserved by _normalize. Anything else (legacy `score`, `signals`,
    # `rooms`, `listed_on_matrixrooms`, `scanned`) is derived data and doesn't
    # belong in a README cache — it lives in the project files.
    _CACHE_FIELDS = ('branch', 'filename', 'etag', 'sha', 'fetched', 'size')

    def _load_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            raw = json.loads(self.index_path.read_text())
        except json.JSONDecodeError:
            print(f'WARN: {self.index_path} is corrupt, starting fresh',
                  file=sys.stderr)
            return {}
        # Normalize: keep only cache fields. The legacy file had derived
        # data mixed in; this drops it on next flush so the diff converges
        # to a clean schema.
        normalized = {}
        changed = False
        for repo, entry in raw.items():
            if not isinstance(entry, dict):
                continue
            clean = {k: entry[k] for k in self._CACHE_FIELDS if k in entry}
            if clean != entry:
                changed = True
            normalized[repo] = clean
        if changed:
            self._dirty = True
        return normalized

    def flush(self) -> None:
        if not self._dirty:
            return
        # Sort keys for stable diffs.
        self.index_path.write_text(json.dumps(self._index, indent=2,
                                               sort_keys=True) + '\n')
        self._dirty = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.flush()

    # ----------------------------------------------------------------- read

    def _bytes_path(self, owner_repo: str) -> Path:
        return self.bytes_dir / _bytes_filename(owner_repo)

    def _read_bytes(self, owner_repo: str) -> str | None:
        p = self._bytes_path(owner_repo)
        if not p.exists():
            return None
        try:
            return p.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return None

    def _write_bytes(self, owner_repo: str, text: str) -> None:
        self._bytes_path(owner_repo).write_text(text, encoding='utf-8')

    # ---------------------------------------------------------------- fetch

    def _conditional_get(self, owner_repo: str, branch: str, filename: str,
                         etag: str | None) -> tuple[int, str | None, str | None, str | None]:
        """Return (status, body, new_etag, last_modified).

        status: HTTP status code (200, 304, 4xx, 5xx, 0 for network error)
        body:   text on 200, None otherwise
        new_etag, last_modified: from response headers, possibly None
        """
        url = f'https://raw.githubusercontent.com/{owner_repo}/{branch}/{filename}'
        headers = {'User-Agent': USER_AGENT}
        if etag:
            headers['If-None-Match'] = etag
        req = Request(url, headers=headers)
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode('utf-8', errors='replace')
                return (resp.status, body,
                        resp.headers.get('ETag'),
                        resp.headers.get('Last-Modified'))
        except HTTPError as e:
            # 304 Not Modified → server confirms our cache is fresh.
            if e.code == 304:
                return (304, None, etag, None)
            return (e.code, None, None, None)
        except (URLError, TimeoutError, OSError):
            return (0, None, None, None)

    def _probe(self, owner_repo: str) -> tuple[str, str, str, str | None] | None:
        """First-time discovery: walk the branch × filename ladder until
        one combo returns 200. Returns (branch, filename, body, etag) or None."""
        for branch in DEFAULT_BRANCHES:
            for filename in DEFAULT_FILENAMES:
                status, body, etag, _ = self._conditional_get(
                    owner_repo, branch, filename, etag=None)
                if status == 200:
                    return (branch, filename, body, etag)
        return None

    # ----------------------------------------------------------------- core

    def get(self, owner_repo: str, *, force_refresh: bool = False) -> str | None:
        """Return README text for `owner/repo`, fetching only if needed.

        Steps:
        1. If forced or no index entry → probe ladder (full discovery).
        2. Else → conditional GET on the recorded branch/filename.
           - 304: stats hits_304, return cached bytes.
           - 200: stats fetches_updated, write new bytes + index, return.
           - 404: probe ladder again (file moved). On success, write +
             index. On failure, fall back to cached bytes if any.
           - Network error / 5xx: fall back to cached bytes if any.
        """
        entry = self._index.get(owner_repo) if not force_refresh else None

        if entry is None:
            # First-time fetch.
            probed = self._probe(owner_repo)
            if probed is None:
                self.stats['fetches_failed'] += 1
                return None
            branch, filename, body, etag = probed
            self._record(owner_repo, branch, filename, body, etag, kind='new')
            return body

        # Conditional refresh.
        branch = entry.get('branch') or DEFAULT_BRANCHES[0]
        filename = entry.get('filename') or DEFAULT_FILENAMES[0]
        etag = entry.get('etag')

        status, body, new_etag, last_mod = self._conditional_get(
            owner_repo, branch, filename, etag)

        if status == 304:
            self.stats['hits_304'] += 1
            cached = self._read_bytes(owner_repo)
            if cached is not None:
                return cached
            # ETag matched but bytes file is missing — refetch unconditionally.
            status, body, new_etag, last_mod = self._conditional_get(
                owner_repo, branch, filename, etag=None)

        if status == 200 and body is not None:
            self.stats['fetches_updated'] += 1
            self._record(owner_repo, branch, filename, body, new_etag, kind='updated')
            return body

        if status == 404:
            # File moved or branch renamed. Re-probe.
            probed = self._probe(owner_repo)
            if probed is not None:
                branch, filename, body, new_etag = probed
                self._record(owner_repo, branch, filename, body, new_etag, kind='updated')
                return body

        # Network failure or 5xx — fall back to whatever bytes we have.
        cached = self._read_bytes(owner_repo)
        if cached is not None:
            self.stats['hits_local'] += 1
            return cached
        self.stats['fetches_failed'] += 1
        return None

    def _record(self, owner_repo: str, branch: str, filename: str,
                body: str, etag: str | None, kind: str) -> None:
        self._write_bytes(owner_repo, body)
        self._index[owner_repo] = {
            'branch': branch,
            'filename': filename,
            'etag': etag or '',
            'fetched': _utcnow_iso(),
            'size': len(body),
        }
        self._dirty = True
        if kind == 'new':
            self.stats['fetches_new'] += 1

    # -------------------------------------------------------------- helpers

    def report(self) -> str:
        s = self.stats
        return (f"readme cache: "
                f"{s['hits_304']} 304s, "
                f"{s['hits_local']} local, "
                f"{s['fetches_new']} new, "
                f"{s['fetches_updated']} updated, "
                f"{s['fetches_failed']} failed")


# ─────────────────────────────────────────────────────────────────── CLI ──
# Minimal CLI for one-off ops: warm the cache, force-refresh one repo,
# print stats. Mostly used during development and migration.

def _cli():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', help='Owner/repo (single fetch)')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--from-projects', action='store_true',
                    help='Walk projects/*.md and refresh every GitHub repo')
    ap.add_argument('--seed', help='JSON file mapping owner/repo → README text '
                                   '(e.g. data/.dry-pass-readme-cache.json) — '
                                   'writes the bytes only, no network calls. '
                                   'Useful for migrating an existing cache.')
    ap.add_argument('--limit', type=int, default=None)
    args = ap.parse_args()

    cache = ReadmeCache()

    if args.seed:
        seed = json.loads(Path(args.seed).read_text())
        n = 0
        for repo, text in seed.items():
            if not text:
                continue
            cache._write_bytes(repo, text)
            cache._index[repo] = {
                'branch': '',     # unknown — will be filled on next refresh
                'filename': '',
                'etag': '',
                'fetched': _utcnow_iso(),
                'size': len(text),
            }
            cache._dirty = True
            n += 1
        cache.flush()
        print(f'Seeded {n} entries from {args.seed}', file=sys.stderr)
        return

    if args.repo:
        text = cache.get(args.repo, force_refresh=args.force)
        cache.flush()
        print(f'{args.repo}: {len(text or "")} bytes')
        print(cache.report(), file=sys.stderr)
        return

    if args.from_projects:
        import re
        repos = []
        for fpath in sorted(Path('projects').glob('*.md')):
            content = fpath.read_text()
            m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
            if not m:
                continue
            url = m.group(1).strip().rstrip('/')
            gm = re.search(r'github\.com/([^/]+/[^/\s#?]+?)(?:\.git)?$', url)
            if gm:
                repos.append(gm.group(1))
        if args.limit:
            repos = repos[:args.limit]
        print(f'Refreshing {len(repos)} repos...', file=sys.stderr)
        for i, repo in enumerate(repos):
            cache.get(repo)
            if (i + 1) % 50 == 0:
                cache.flush()
                print(f'  {i+1}/{len(repos)}: {cache.report()}', file=sys.stderr)
        cache.flush()
        print(cache.report(), file=sys.stderr)
        return

    ap.print_help()


if __name__ == '__main__':
    _cli()
