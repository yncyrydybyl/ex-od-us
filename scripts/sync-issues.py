#!/usr/bin/env python3
"""
sync-issues.py — Create GitHub issues for projects that don't have one,
and sync labels from project file categories.

Reads projects/*.md, checks which have issues: [], creates issues for those,
updates the project file with the new issue number, and ensures labels match.

Requires: gh CLI (authenticated via GH_TOKEN)
"""
import os, re, subprocess, json, sys

REPO = os.environ.get('GITHUB_REPOSITORY', 'yncyrydybyl/ex-od-us')
PROJECTS_DIR = 'projects'

def gh(*args):
    """Run gh command and return stdout."""
    result = subprocess.run(['gh'] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  gh error: {result.stderr.strip()}", file=sys.stderr)
        return None
    return result.stdout.strip()

def parse_frontmatter(text):
    """Simple YAML frontmatter parser."""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    fm = {}
    current_key = None
    current_list = None
    for line in raw.split('\n'):
        list_m = re.match(r'^\s+-\s+(.*)', line)
        if list_m and current_key:
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            current_list.append(list_m.group(1).strip().strip('"').strip("'"))
            continue
        kv_m = re.match(r'^(\w[\w\-_]*):\s*(.*)', line)
        if kv_m:
            current_key = kv_m.group(1).strip()
            val = kv_m.group(2).strip().strip('"').strip("'")
            current_list = None
            if val.startswith('[') and val.endswith(']'):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(',')]
                fm[current_key] = [x for x in items if x]
            elif val == '' or val == '[]':
                fm[current_key] = []
                current_list = []
            elif val.lower() in ('true', 'false'):
                fm[current_key] = val.lower() == 'true'
            elif val.lower() in ('null', '~'):
                fm[current_key] = None
            else:
                try: fm[current_key] = int(val)
                except ValueError: fm[current_key] = val
    return fm, body

def ensure_label(label):
    """Create label if it doesn't exist."""
    gh('label', 'create', label, '--repo', REPO, '--color', '6e7681',
       '--description', f'Category: {label}', '--force')

def main():
    created = 0
    synced = 0

    for fname in sorted(os.listdir(PROJECTS_DIR)):
        if not fname.endswith('.md'):
            continue

        fpath = os.path.join(PROJECTS_DIR, fname)
        with open(fpath) as f:
            content = f.read()

        fm, body = parse_frontmatter(content)
        name = fm.get('name', fname[:-3])
        issues = fm.get('issues', [])
        categories = fm.get('categories', [])
        desc = fm.get('description', '')
        repo = fm.get('repo', '')
        status = fm.get('status', '')

        # Ensure issues is a list
        if isinstance(issues, (int, str)):
            issues = [int(issues)] if issues else []
        issues = [int(i) for i in issues if i]

        # Skip if already has an issue
        if issues:
            # Sync labels on existing issue
            for issue_num in issues:
                labels_to_add = ['project'] + categories
                for label in categories:
                    ensure_label(label)
                current = gh('issue', 'view', str(issue_num), '--repo', REPO,
                           '--json', 'labels', '--jq', '[.labels[].name] | join(",")')
                if current is None:
                    continue
                current_labels = set(current.split(',')) if current else set()
                missing = [l for l in labels_to_add if l not in current_labels]
                if missing:
                    gh('issue', 'edit', str(issue_num), '--repo', REPO,
                       '--add-label', ','.join(missing))
                    print(f"  SYNC #{issue_num} ({name}): added labels {missing}", file=sys.stderr)
                    synced += 1
            continue

        # Create issue for this project
        print(f"  CREATE issue for {name}...", file=sys.stderr)

        # Build issue body
        issue_body = f"**Project file:** [`projects/{fname}`](https://github.com/{REPO}/blob/main/projects/{fname})\n\n"
        if desc:
            issue_body += f"{desc}\n\n"
        if repo:
            issue_body += f"**Repository:** {repo}\n"
        if status:
            issue_body += f"**Status:** {status}\n"

        # Ensure category labels exist
        labels = ['project']
        for cat in categories:
            ensure_label(cat)
            labels.append(cat)

        result = gh('issue', 'create', '--repo', REPO,
                    '--title', f'[Project]: {name}',
                    '--label', ','.join(labels),
                    '--body', issue_body)

        if result and result.startswith('http'):
            # Extract issue number from URL
            issue_num = int(result.rstrip('/').split('/')[-1])
            print(f"  CREATED #{issue_num} for {name}", file=sys.stderr)

            # Update project file with issue number
            new_content = content.replace(
                'issues: []',
                f'issues: [{issue_num}]'
            )
            with open(fpath, 'w') as f:
                f.write(new_content)
            created += 1
        else:
            print(f"  FAILED to create issue for {name}", file=sys.stderr)

    print(f"\nCreated: {created}, Synced labels: {synced}", file=sys.stderr)

if __name__ == '__main__':
    main()
