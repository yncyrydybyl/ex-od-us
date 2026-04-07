#!/usr/bin/env python3
"""
discover-codeberg.py — Find and import Matrix-related projects from Codeberg.

Searches Codeberg API for repos mentioning Matrix, fetches their READMEs
to check for matrix.to links, creates project files.

No auth needed. No rate limit issues (Codeberg API is generous).

Usage:
  python3 scripts/discover-codeberg.py [--dry-run] [--limit N] [--min-stars N]
"""

import os, sys, re, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(__file__))
from exclusions import load_excluded_repos, is_excluded

PROJECTS_DIR = Path('projects')
CODEBERG_API = 'https://codeberg.org/api/v1'
ROOM_PATTERN = re.compile(r'matrix\.to/#/(#[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)')

def log(msg):
    print(f'[{datetime.now(timezone.utc).strftime("%H:%M:%S")}] {msg}', file=sys.stderr, flush=True)

def codeberg_get(path, params=None):
    url = f'{CODEBERG_API}{path}'
    if params:
        url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
    try:
        req = Request(url, headers={'User-Agent': 'ex-od-us-enricher'})
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except Exception as e:
        log(f'  API error: {e}')
        return None

def fetch_readme(owner, repo):
    """Fetch README from Codeberg raw endpoint."""
    for name in ['README.md', 'readme.md', 'README.rst', 'README']:
        for branch in ['main', 'master', 'develop']:
            url = f'https://codeberg.org/{owner}/{repo}/raw/branch/{branch}/{name}'
            try:
                req = Request(url, headers={'User-Agent': 'ex-od-us-enricher'})
                resp = urlopen(req, timeout=10)
                return resp.read().decode('utf-8', errors='replace')
            except HTTPError:
                continue
            except Exception:
                continue
    return None

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--min-stars', type=int, default=0)
    args = parser.parse_args()

    PROJECTS_DIR.mkdir(exist_ok=True)

    # Index existing projects by repo URL
    existing_repos = set()
    existing_slugs = set()
    for f in PROJECTS_DIR.glob('*.md'):
        existing_slugs.add(f.stem)
        content = f.read_text()
        m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
        if m:
            existing_repos.add(m.group(1).strip().rstrip('/').lower())

    log(f'Already tracking {len(existing_repos)} repos')

    excluded = load_excluded_repos()
    if excluded:
        log(f'Loaded {len(excluded)} excluded repos')

    # Search Codeberg for Matrix-related repos
    log('Searching Codeberg...')
    queries = ['matrix', 'element', 'matrix.to', 'mautrix', 'conduit', 'dendrite']
    all_repos = {}

    for query in queries:
        page = 1
        while True:
            data = codeberg_get('/repos/search', {
                'q': query, 'sort': 'stars', 'order': 'desc',
                'limit': 50, 'page': page
            })
            if not data or not data.get('data'):
                break
            for repo in data['data']:
                slug = repo['full_name']
                if slug not in all_repos:
                    all_repos[slug] = repo
            if len(data['data']) < 50:
                break
            page += 1
            time.sleep(0.3)
        log(f'  "{query}": {len(all_repos)} total repos so far')

    log(f'Found {len(all_repos)} unique Codeberg repos')

    # Filter and import
    created = 0
    skipped = 0
    scanned = 0

    for full_name, repo in sorted(all_repos.items(), key=lambda x: -(x[1].get('stars_count', 0))):
        if created >= args.limit:
            break

        stars = repo.get('stars_count', 0)
        if stars < args.min_stars:
            continue

        repo_url = f'https://codeberg.org/{full_name}'
        if is_excluded(repo_url, excluded):
            skipped += 1
            continue
        if repo_url.lower() in existing_repos:
            skipped += 1
            continue

        # Fetch README and check for matrix.to
        owner, name = full_name.split('/', 1)
        readme = fetch_readme(owner, name)
        scanned += 1

        has_matrix = False
        rooms = []
        score = 0
        signals = []

        if readme:
            decoded = unquote(readme)
            rooms = list(set(ROOM_PATTERN.findall(decoded)))
            valid_rooms = [r for r in rooms if re.match(r'^#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', r)]

            if valid_rooms:
                has_matrix = True
                score += 2
                signals.append(f'matrix.to links: {len(valid_rooms)}')
            if re.search(r'shields\.io/matrix|matrix-badge', decoded, re.I):
                has_matrix = True
                score += 1
                signals.append('Matrix badge')
            if re.search(r'matrix\.to/#/@', decoded):
                has_matrix = True
                score += 1
                signals.append('Matrix user link')
            if re.search(r'join.*(matrix|element)|matrix\s+(room|channel|space)', decoded, re.I):
                has_matrix = True
                score += 1
                signals.append('Matrix mentioned')

            # Custom homeserver
            custom = [r.split(':')[1] for r in valid_rooms if ':' in r and 'matrix.org' not in r]
            if custom:
                score += 2
                signals.append(f'Custom HS: {custom[0]}')

            rooms = valid_rooms

        # Also count repos with matrix in topics
        topics = repo.get('topics', []) or []
        if any(t.lower() in ('matrix', 'element', 'matrix-org', 'mautrix') for t in topics):
            has_matrix = True
            if not signals:
                score = max(score, 1)
                signals.append('Matrix topic')

        if not has_matrix:
            skipped += 1
            continue

        score = min(score, 10)

        # Create project file
        file_slug = slugify(name)
        if file_slug in existing_slugs:
            file_slug = slugify(full_name.replace('/', '-'))
        existing_slugs.add(file_slug)
        existing_repos.add(repo_url.lower())

        desc = (repo.get('description') or '').replace('"', '\\"')[:300]
        lang = repo.get('language') or ''
        forks = repo.get('forks_count', 0)
        pushed = repo.get('updated_at', '')
        archived = repo.get('archived', False)

        categories = ['Development']
        for t in topics:
            if t.lower() in ('matrix', 'element'): categories = ['Matrix']; break
            if t.lower() in ('chat', 'messaging'): categories = ['Messaging']; break
            if t.lower() in ('bridge', 'bridging'): categories = ['Bridging']; break

        fm_lines = ['---']
        fm_lines.append(f'name: "{name}"')
        if desc: fm_lines.append(f'description: "{desc}"')
        fm_lines.append(f'repo: "{repo_url}"')
        fm_lines.append(f'platform: codeberg')
        fm_lines.append(f'categories: [{", ".join(categories)}]')
        if score > 0: fm_lines.append(f'exodus_score: {score}')
        fm_lines.append(f'status: "{"Archived" if archived else "Active"}"')
        if rooms:
            fm_lines.append('matrix_rooms:')
            for r in rooms[:5]:
                fm_lines.append(f'  - "https://matrix.to/#/{r}"')
        fm_lines.append(f'issues: []')
        fm_lines.append(f'updated: "{pushed}"')
        fm_lines.append(f'last_scanned: "{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}"')
        fm_lines.append('---')
        if desc: fm_lines.extend(['', desc])
        if stars or lang:
            fm_lines.extend(['', '## Stats', ''])
            if stars: fm_lines.append(f'- Stars: {stars}')
            if forks: fm_lines.append(f'- Forks: {forks}')
            if lang: fm_lines.append(f'- Language: {lang}')
            if topics: fm_lines.append(f'- Topics: {", ".join(topics)}')

        content = '\n'.join(fm_lines) + '\n'
        fpath = PROJECTS_DIR / f'{file_slug}.md'

        if args.dry_run:
            log(f'  WOULD CREATE {file_slug}.md — {name} ({stars} stars, score {score})')
        else:
            fpath.write_text(content)
            log(f'  CREATED {file_slug}.md — {name} ({stars} stars, score {score})')

        created += 1
        time.sleep(0.2)

    log(f'\nDone. Created: {created}, Skipped: {skipped}, READMEs scanned: {scanned}')

if __name__ == '__main__':
    main()
