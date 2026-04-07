#!/usr/bin/env python3
"""
import-from-slugs.py — Batch-import projects from data/discovered-slugs.txt

Reads repo slugs (owner/repo, one per line), skips already-tracked projects,
fetches metadata via GitHub API, creates project markdown files.

Usage:
  python3 scripts/import-from-slugs.py [--dry-run] [--limit N] [--min-stars N] [--offset N]

The slug list is saved by find-matrix-repos.sh in data/discovered-slugs.txt.
This lets you import in batches without re-running the Sourcegraph search.
"""
import sys, os, re, json, subprocess, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from exclusions import load_excluded_repos, is_excluded

SLUGS_FILE = 'data/discovered-slugs.txt'
PROJECTS_DIR = 'projects'

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

def gh_api(endpoint):
    """Fetch from GitHub API via gh CLI."""
    try:
        result = subprocess.run(
            ['gh', 'api', endpoint, '--jq', '.'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Batch-import from discovered slugs')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--limit', type=int, default=100, help='Max projects to import (default 100)')
    parser.add_argument('--min-stars', type=int, default=0, help='Minimum stars (default 0)')
    parser.add_argument('--offset', type=int, default=0, help='Skip first N slugs')
    parser.add_argument('--slugs-file', default=SLUGS_FILE)
    args = parser.parse_args()

    if not os.path.exists(args.slugs_file):
        print(f"Error: {args.slugs_file} not found. Run find-matrix-repos.sh first.", file=sys.stderr)
        sys.exit(1)

    with open(args.slugs_file) as f:
        all_slugs = [line.strip() for line in f if line.strip()]

    print(f"Loaded {len(all_slugs)} slugs from {args.slugs_file}", file=sys.stderr)

    # Index existing projects by repo URL
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    existing_repos = set()
    existing_file_slugs = set()
    for fname in os.listdir(PROJECTS_DIR):
        if not fname.endswith('.md'):
            continue
        existing_file_slugs.add(fname[:-3])
        with open(os.path.join(PROJECTS_DIR, fname)) as f:
            content = f.read()
        m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
        if m:
            # Normalize to owner/repo
            url = m.group(1).strip().rstrip('/')
            gm = re.search(r'github\.com/([^/]+/[^/\s#?.]+)', url)
            if gm:
                existing_repos.add(gm.group(1).lower().removesuffix('.git'))

    print(f"Already tracking {len(existing_repos)} repos", file=sys.stderr)

    excluded = load_excluded_repos()
    if excluded:
        print(f"Loaded {len(excluded)} excluded repos", file=sys.stderr)

    # Apply offset
    slugs = all_slugs[args.offset:]
    created = 0
    skipped = 0
    errors = 0

    for slug in slugs:
        if created >= args.limit:
            break

        if is_excluded(slug, excluded):
            skipped += 1
            continue

        if slug.lower() in existing_repos:
            skipped += 1
            continue

        # Fetch repo metadata
        data = gh_api(f'repos/{slug}')
        time.sleep(0.3)

        if not data:
            errors += 1
            continue

        stars = data.get('stargazers_count', 0)
        if stars < args.min_stars:
            skipped += 1
            continue

        name = slug.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
        desc = (data.get('description') or '').replace('"', '\\"')
        lang = data.get('language') or ''
        topics = data.get('topics') or []
        forks = data.get('forks_count', 0)
        pushed = data.get('pushed_at', '')
        archived = data.get('archived', False)

        # Categories from topics
        topic_map = {
            'matrix': 'Matrix', 'element': 'Matrix', 'chat': 'Messaging',
            'bridge': 'Bridging', 'homeserver': 'Infrastructure',
            'encryption': 'Security', 'e2ee': 'Security',
            'bot': 'Integrations', 'widget': 'Integrations',
        }
        categories = []
        for t in topics:
            cat = topic_map.get(t.lower())
            if cat and cat not in categories:
                categories.append(cat)
        if not categories:
            categories.append('Development')

        file_slug = slugify(slug.split('/')[-1])
        if file_slug in existing_file_slugs:
            file_slug = slugify(slug.replace('/', '-'))
        existing_file_slugs.add(file_slug)
        existing_repos.add(slug.lower())

        # Build markdown
        fm = ['---']
        fm.append(f'name: "{name}"')
        if desc:
            fm.append(f'description: "{desc[:300]}"')
        fm.append(f'repo: "https://github.com/{slug}"')
        fm.append(f'platform: github')
        fm.append(f'categories: [{", ".join(categories)}]')
        fm.append(f'status: "{"Archived" if archived else "Active"}"')
        fm.append(f'issues: []')
        fm.append(f'updated: "{pushed}"')
        fm.append('---')
        if desc:
            fm.append('')
            fm.append(desc[:300])
        fm.append('')
        fm.append('## Stats')
        fm.append('')
        fm.append(f'- Stars: {stars}')
        fm.append(f'- Forks: {forks}')
        if lang:
            fm.append(f'- Language: {lang}')
        if topics:
            fm.append(f'- Topics: {", ".join(topics)}')

        content = '\n'.join(fm) + '\n'
        fpath = os.path.join(PROJECTS_DIR, f'{file_slug}.md')

        if args.dry_run:
            print(f'  WOULD CREATE {file_slug}.md — {name} ({stars} stars)', file=sys.stderr)
        else:
            with open(fpath, 'w') as f:
                f.write(content)
            print(f'  CREATED {file_slug}.md — {name} ({stars} stars)', file=sys.stderr)

        created += 1

    print(f'\n{"Would create" if args.dry_run else "Created"}: {created}, '
          f'Skipped: {skipped}, Errors: {errors}, '
          f'Remaining: {len(all_slugs) - args.offset - created - skipped - errors}',
          file=sys.stderr)

if __name__ == '__main__':
    main()
