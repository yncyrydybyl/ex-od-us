#!/usr/bin/env python3
"""
exclusions.py — Shared helper for the excluded-repos list.

A handful of projects look Matrix-related (because they have "matrix"
in the name) but actually aren't — XCSSMatrix is a CSS matrix transform
polyfill, not a Matrix-protocol thing. Discovery scripts kept re-creating
their project files. This module is the single source of truth for which
repos are excluded; every discovery / import / build script consults it.

The store is `data/excluded-repos.txt`, plain text, one entry per line:
    github.com/jfsiii/XCSSMatrix    # reason

Comparison is case-insensitive against the canonical
`<host>/<owner>/<repo>` form. Trailing `.git` and trailing slashes are
stripped before comparison.
"""
import re
from pathlib import Path

DEFAULT_PATH = Path('data/excluded-repos.txt')


def _normalize(repo_url_or_slug: str) -> str | None:
    """Reduce any of the following to `host/owner/repo` (lowercased):

        https://github.com/Owner/Repo
        https://github.com/Owner/Repo.git
        github.com/Owner/Repo
        Owner/Repo                  (assumed github.com)
        git@github.com:Owner/Repo.git

    Returns None if the input doesn't look like a repo identifier.
    """
    if not repo_url_or_slug:
        return None
    s = repo_url_or_slug.strip().rstrip('/')
    if not s:
        return None

    # git@host:owner/repo[.git]
    m = re.match(r'^git@([\w.-]+):([^/]+/[^/\s]+?)(?:\.git)?$', s)
    if m:
        return f'{m.group(1)}/{m.group(2)}'.lower()

    # http(s)://host/owner/repo[.git]
    m = re.match(r'^https?://([\w.-]+)/([^/]+/[^/\s?#]+?)(?:\.git)?(?:[?#].*)?$', s)
    if m:
        return f'{m.group(1)}/{m.group(2)}'.lower()

    # host/owner/repo[.git]
    m = re.match(r'^([\w.-]+)/([^/]+/[^/\s]+?)(?:\.git)?$', s)
    if m:
        return f'{m.group(1)}/{m.group(2)}'.lower()

    # bare owner/repo — assume github.com
    m = re.match(r'^([^/\s]+/[^/\s]+?)(?:\.git)?$', s)
    if m:
        return f'github.com/{m.group(1)}'.lower()

    return None


def load_excluded_repos(path: Path | str = DEFAULT_PATH) -> set[str]:
    """Return the set of normalized excluded `host/owner/repo` strings.

    Missing file → empty set (no exclusions). Comments and blank lines
    ignored. Returns lowercased canonical forms.
    """
    p = Path(path)
    if not p.exists():
        return set()
    out: set[str] = set()
    for raw_line in p.read_text().splitlines():
        # Strip inline comments after `#`. The repo identifier itself
        # never contains `#`, so this is safe.
        line = raw_line.split('#', 1)[0].strip()
        if not line:
            continue
        norm = _normalize(line)
        if norm:
            out.add(norm)
    return out


def is_excluded(repo_url_or_slug: str, excluded: set[str]) -> bool:
    """Return True if the given repo is in the excluded set."""
    norm = _normalize(repo_url_or_slug)
    return norm is not None and norm in excluded


if __name__ == '__main__':
    # CLI smoke test: print the loaded set.
    import sys
    excl = load_excluded_repos()
    print(f'{len(excl)} excluded repos:', file=sys.stderr)
    for r in sorted(excl):
        print(f'  {r}')
