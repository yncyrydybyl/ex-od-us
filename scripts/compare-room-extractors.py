#!/usr/bin/env python3
"""
compare-room-extractors.py — Compare OLD vs NEW room extractor across all projects.

Reports how many *new* room links the SHIELDS_PATTERN + room-ID extension
in `enrich-via-sourcegraph.py` would surface, without writing anything.

Strategy:
1. Read every projects/*.md to get repo URLs.
2. For GitHub repos, fetch the README via raw.githubusercontent.com,
   trying common branches and a few README filenames.
3. Apply OLD regex (matrix.to + element + plain) and NEW regex
   (OLD + room-ID `!` form + shields badges).
4. Print every project where NEW finds rooms OLD did not.
5. Use the shared ReadmeCache (data/readme-cache.json + data/readmes/)
   so a single source of README bytes is used across enricher and tools.

Usage:
  python3 scripts/compare-room-extractors.py
  python3 scripts/compare-room-extractors.py --limit 50         # fetch first 50 only
  python3 scripts/compare-room-extractors.py --project webfs    # one project, verbose
  python3 scripts/compare-room-extractors.py --no-network       # only use cache
"""
import os, sys, re, argparse
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(__file__))
from readme_cache import ReadmeCache

PROJECTS_DIR = Path('projects')

# OLD patterns (verbatim from main branch enrich-via-sourcegraph.py)
OLD_ROOM = re.compile(
    r'(?:matrix\.to/#/|element\.io/#/room/|/#/room/)'
    r'(#[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)'
)
OLD_PLAIN = re.compile(
    r'(?:^|[`"\s(\[>])(#[a-zA-Z0-9._=-]{2,}:[a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b'
)
OLD_VALID = re.compile(r'^#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

# NEW patterns
NEW_ROOM = re.compile(
    r'(?:matrix\.to/#/|element\.io/#/room/|/#/room/)'
    r'([#!][a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)'
)
NEW_PLAIN = OLD_PLAIN  # unchanged
NEW_SHIELDS = re.compile(
    r'img\.shields\.io/matrix/([a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
)
NEW_VALID = re.compile(r'^[#!][a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def extract_old(text):
    text = unquote(text)
    rooms = set(OLD_ROOM.findall(text))
    rooms.update(OLD_PLAIN.findall(text))
    return [r for r in rooms if OLD_VALID.match(r)]


def extract_new(text):
    text = unquote(text)
    rooms = set(NEW_ROOM.findall(text))
    rooms.update(NEW_PLAIN.findall(text))
    rooms.update('#' + r for r in NEW_SHIELDS.findall(text))
    return [r for r in rooms if NEW_VALID.match(r)]


def parse_repo(content):
    m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
    if not m:
        return None
    url = m.group(1).strip().rstrip('/')
    gm = re.search(r'github\.com/([^/]+/[^/\s#?]+?)(?:\.git)?$', url)
    if gm:
        return ('github', gm.group(1))
    return None


def fetch_readme_github(owner_repo, cache: ReadmeCache, no_network=False):
    """Use the persistent cache. `no_network` returns cached bytes only."""
    if no_network:
        return cache._read_bytes(owner_repo) or ''
    return cache.get(owner_repo) or ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--project', help='Single slug, verbose')
    ap.add_argument('--no-network', action='store_true')
    args = ap.parse_args()

    cache = ReadmeCache()
    print(f'Opened ReadmeCache: {len(cache._index)} index entries', file=sys.stderr)

    files = sorted(PROJECTS_DIR.glob('*.md'))
    if args.project:
        files = [f for f in files if f.stem == args.project]
        if not files:
            sys.exit(f'No project file: {args.project}')

    if args.limit:
        files = files[:args.limit]

    new_finds = []  # (slug, owner/repo, [new rooms not in old])
    fetched = 0
    skipped_no_repo = 0
    skipped_no_readme = 0

    for i, fpath in enumerate(files):
        slug = fpath.stem
        content = fpath.read_text()
        repo_info = parse_repo(content)
        if not repo_info or repo_info[0] != 'github':
            skipped_no_repo += 1
            continue

        owner_repo = repo_info[1]
        readme = fetch_readme_github(owner_repo, cache, args.no_network)
        if not readme:
            skipped_no_readme += 1
            continue
        fetched += 1

        old_rooms = set(extract_old(readme))
        new_rooms = set(extract_new(readme))
        diff = new_rooms - old_rooms

        if args.project:
            print(f'{slug} ({owner_repo}):')
            print(f'  OLD: {sorted(old_rooms) or "[]"}')
            print(f'  NEW: {sorted(new_rooms) or "[]"}')
            print(f'  DIFF: {sorted(diff) or "[]"}')

        if diff:
            new_finds.append((slug, owner_repo, sorted(diff), sorted(old_rooms)))

        if (i + 1) % 50 == 0:
            print(f'  ... {i+1}/{len(files)} processed, {len(new_finds)} new finds so far',
                  file=sys.stderr)

    cache.flush()

    print()
    print(f'Processed {len(files)} files')
    print(f'  fetched READMEs:    {fetched}')
    print(f'  no repo / non-GH:   {skipped_no_repo}')
    print(f'  README unavailable: {skipped_no_readme}')
    print(f'  {cache.report()}')
    print()
    print(f'Projects where NEW regex finds rooms OLD missed: {len(new_finds)}')
    print()
    for slug, repo, diff, old in new_finds[:50]:
        print(f'  {slug:35s} ({repo})')
        for r in diff:
            print(f'    + {r}')
        if old:
            for r in old:
                print(f'      (had: {r})')
    if len(new_finds) > 50:
        print(f'  ... and {len(new_finds) - 50} more')


if __name__ == '__main__':
    main()
