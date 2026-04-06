#!/usr/bin/env python3
"""
import-from-finder.py — Generate projects/*.md from find-matrix-repos.sh output

Reads JSON from finder, skips projects that already have a .md file,
creates new project files for discovered repos.

Usage: python3 scripts/import-from-finder.py data/found-repos.json [--dry-run]
"""
import sys, json, os, re

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/import-from-finder.py <finder-output.json> [--dry-run]", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    dry_run = '--dry-run' in sys.argv

    with open(input_file) as f:
        data = json.load(f)

    repos = data.get('repos', [])
    projects_dir = 'projects'
    os.makedirs(projects_dir, exist_ok=True)

    # Index existing projects by repo URL to avoid duplicates
    existing_repos = set()
    existing_slugs = set()
    for fname in os.listdir(projects_dir):
        if not fname.endswith('.md'):
            continue
        existing_slugs.add(fname[:-3])
        with open(os.path.join(projects_dir, fname)) as f:
            content = f.read()
        m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
        if m:
            existing_repos.add(m.group(1).strip().rstrip('/').lower())

    created = 0
    skipped = 0

    for repo in repos:
        slug_candidate = repo['repo'].split('/')[-1].lower()
        repo_url = f"https://github.com/{repo['repo']}"

        # Skip if already tracked
        if repo_url.lower() in existing_repos:
            print(f"  SKIP {repo['repo']} (already tracked)", file=sys.stderr)
            skipped += 1
            continue

        # Build unique slug
        slug = slugify(slug_candidate)
        if slug in existing_slugs:
            slug = slugify(repo['repo'].replace('/', '-'))
        existing_slugs.add(slug)

        # Detect platform
        platform = 'github'  # finder currently only searches GitHub

        # Infer categories from language and topics
        categories = []
        topics = repo.get('topics', [])
        lang = repo.get('language', '')

        # Map well-known topics
        topic_map = {
            'matrix': 'Matrix', 'element': 'Matrix', 'chat': 'Messaging',
            'bridge': 'Bridging', 'homeserver': 'Infrastructure',
            'encryption': 'Security', 'e2ee': 'Security',
            'bot': 'Integrations', 'widget': 'Integrations',
            'moderation': 'Community', 'linux': 'Infrastructure',
            'rust': 'Development', 'python': 'Development',
        }
        for t in topics:
            cat = topic_map.get(t.lower())
            if cat and cat not in categories:
                categories.append(cat)

        if not categories and lang:
            categories.append('Development')

        # Name: use repo name, title-cased
        name = slug_candidate.replace('-', ' ').replace('_', ' ').title()
        # But if the repo has a description, that's better context
        desc = repo.get('description', '') or ''

        fm = ['---']
        fm.append(f'name: "{name}"')
        if desc:
            desc_clean = desc.replace('"', '\\"')
            fm.append(f'description: "{desc_clean}"')
        fm.append(f'repo: "{repo_url}"')
        fm.append(f'platform: {platform}')
        if categories:
            fm.append(f'categories: [{", ".join(categories)}]')
        fm.append(f'status: "{"Archived" if repo.get("archived") else "Active"}"')
        fm.append(f'issues: []')
        fm.append(f'updated: "{repo.get("pushed_at", "")}"')
        fm.append('---')

        if desc:
            fm.append('')
            fm.append(desc)

        # Add stats as a note
        fm.append('')
        fm.append(f'## Stats')
        fm.append('')
        fm.append(f'- Stars: {repo["stars"]}')
        fm.append(f'- Forks: {repo["forks"]}')
        if lang:
            fm.append(f'- Language: {lang}')
        if topics:
            fm.append(f'- Topics: {", ".join(topics)}')

        content = '\n'.join(fm) + '\n'

        fpath = os.path.join(projects_dir, f'{slug}.md')

        if dry_run:
            print(f"  WOULD CREATE {slug}.md — {name} ({repo['stars']} stars)", file=sys.stderr)
        else:
            with open(fpath, 'w') as f:
                f.write(content)
            print(f"  CREATED {slug}.md — {name} ({repo['stars']} stars)", file=sys.stderr)

        created += 1

    print(f"\n{'Would create' if dry_run else 'Created'}: {created}, Skipped: {skipped}", file=sys.stderr)

if __name__ == '__main__':
    main()
