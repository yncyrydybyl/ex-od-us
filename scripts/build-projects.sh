#!/usr/bin/env bash
#
# build-projects.sh — Build data/projects.json from projects/*.md files
#
# Reads YAML frontmatter from each markdown file in projects/,
# merges with the markdown body, and writes a single JSON file
# that the static site can load without hitting the GitHub API.
#
# Requires: python3 (with PyYAML or a fallback parser)
# Usage: ./scripts/build-projects.sh
#
set -euo pipefail

PROJECTS_DIR="projects"
OUTPUT="data/projects.json"

if [[ ! -d "$PROJECTS_DIR" ]]; then
  echo "Error: $PROJECTS_DIR directory not found." >&2
  exit 1
fi

# Use Python to parse YAML frontmatter — it's the only reliable way
# without adding dependencies. Python3 is available everywhere.
python3 - "$PROJECTS_DIR" "$OUTPUT" << 'PYEOF'
import sys, os, json, re
from datetime import datetime, timezone

# Defense in depth: even if a .md for an excluded repo sneaks back in,
# the site never shows it. The exclusion list is the source of truth.
sys.path.insert(0, 'scripts')
try:
    from exclusions import load_excluded_repos, is_excluded
    excluded_repos = load_excluded_repos()
except Exception:
    excluded_repos = set()

projects_dir = sys.argv[1]
output_file = sys.argv[2]

def parse_frontmatter(text):
    """Parse YAML-ish frontmatter without PyYAML — handles our known fields."""
    fm = {}
    body = text
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', text, re.DOTALL)
    if not m:
        return fm, text
    raw, body = m.group(1), m.group(2)

    current_key = None
    current_list = None

    for line in raw.split('\n'):
        # List item
        list_m = re.match(r'^(\s+)-\s+(.*)', line)
        if list_m and current_key:
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            val = list_m.group(2).strip().strip('"').strip("'")
            current_list.append(val)
            continue

        # Key: value
        kv_m = re.match(r'^(\w[\w\-_]*):\s*(.*)', line)
        if kv_m:
            current_key = kv_m.group(1).strip()
            val = kv_m.group(2).strip().strip('"').strip("'")
            current_list = None

            # Handle inline lists: [a, b, c]
            if val.startswith('[') and val.endswith(']'):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(',')]
                fm[current_key] = [x for x in items if x]
            elif val == '' or val == '[]':
                current_list = []
                fm[current_key] = current_list
            elif val.lower() == 'true':
                fm[current_key] = True
            elif val.lower() == 'false':
                fm[current_key] = False
            elif val.lower() == 'null' or val == '~':
                fm[current_key] = None
            else:
                # Try number
                try:
                    fm[current_key] = int(val)
                except ValueError:
                    try:
                        fm[current_key] = float(val)
                    except ValueError:
                        fm[current_key] = val
            continue

    return fm, body.strip()


def parse_matrix_links(text):
    """Special parser for the matrix_links list-of-dicts in YAML."""
    m = re.search(r'^matrix_links:\s*\n((?:  - target:.*\n(?:    \w+:.*\n)*)+)', text, re.MULTILINE)
    if not m:
        return []
    block = m.group(1)
    links = []
    current = None
    for line in block.split('\n'):
        if re.match(r'^  - target:', line):
            if current: links.append(current)
            current = {}
            v = line.split('target:', 1)[1].strip().strip('"').strip("'")
            current['target'] = v
        elif current and re.match(r'^    \w+:', line):
            key, _, val = line.strip().partition(':')
            val = val.strip().strip('"').strip("'")
            try: val = int(val)
            except ValueError: pass
            current[key.strip()] = val
    if current: links.append(current)
    return links


projects = []

for fname in sorted(os.listdir(projects_dir)):
    if not fname.endswith('.md'):
        continue

    fpath = os.path.join(projects_dir, fname)
    with open(fpath, 'r') as f:
        content = f.read()

    fm, body = parse_frontmatter(content)
    matrix_links = parse_matrix_links(content)

    # Skip excluded repos as a backstop. Normally the .md is deleted
    # when the repo is excluded, but this guards against a stale file
    # being committed by accident.
    repo_field = fm.get('repo', '')
    if excluded_repos and repo_field and is_excluded(repo_field, excluded_repos):
        print(f"Skipping excluded repo: {fname}", file=sys.stderr)
        continue

    slug = fname[:-3]  # remove .md

    # Normalize fields
    project = {
        'slug': slug,
        'name': str(fm.get('name', slug)),
        'description': fm.get('description', ''),
        'website': fm.get('website', ''),
        'repo': fm.get('repo', ''),
        'platform': fm.get('platform', 'none'),
        'categories': fm.get('categories', []),
        'exodus_score': fm.get('exodus_score'),
        'status': fm.get('status', ''),
        'community_size': fm.get('community_size', ''),
        'channels': {
            'matrix_space': fm.get('matrix_space', ''),
            'matrix_rooms': fm.get('matrix_rooms', []),
            'discord': fm.get('discord', ''),
            'telegram': fm.get('telegram', ''),
            'slack': fm.get('slack', ''),
            'irc': fm.get('irc', ''),
            'whatsapp': fm.get('whatsapp', ''),
            'signal': fm.get('signal', ''),
            'xmpp': fm.get('xmpp', ''),
            'zulip': fm.get('zulip', ''),
            'mattermost': fm.get('mattermost', ''),
            'rocketchat': fm.get('rocketchat', ''),
            'other': fm.get('other_channels', []),
        },
        'score_details': {
            'presence': fm.get('score_presence', ''),
            'primary_platform': fm.get('score_primary', ''),
            'federation': fm.get('score_federation', ''),
            'bridges': fm.get('score_bridges', ''),
            'community_health': fm.get('score_community', ''),
            'native_ratio': fm.get('score_native_ratio', ''),
            'migration_intent': fm.get('score_migration_intent', ''),
            'features': fm.get('score_features', []),
        },
        'issues': fm.get('issues', []),
        'avatar_url': fm.get('avatar_url', ''),
        'notes': body if body else fm.get('notes', ''),
        'updated': fm.get('updated', ''),
        'last_scanned': fm.get('last_scanned', ''),
        'verified': fm.get('verified', None),
        'verified_note': fm.get('verified_note', ''),
        'matrix_links': matrix_links,
    }

    # Auto-detect platform from repo URL if not set
    if project['platform'] == 'none' and project['repo']:
        repo = project['repo']
        if 'github.com' in repo:
            project['platform'] = 'github'
        elif 'gitlab.com' in repo:
            project['platform'] = 'gitlab'
        elif 'codeberg.org' in repo:
            project['platform'] = 'codeberg'
        else:
            project['platform'] = 'other'

    # Auto-generate avatar URL if not set
    if not project['avatar_url'] and project['repo']:
        repo = project['repo']
        gm = re.search(r'github\.com/([^/]+)', repo)
        cm = re.search(r'codeberg\.org/([^/]+)', repo)
        if gm:
            project['avatar_url'] = f"https://github.com/{gm.group(1)}.png?size=64"
        elif cm:
            project['avatar_url'] = f"https://codeberg.org/avatars/{cm.group(1)}"

    # Ensure issues is a list of ints
    if isinstance(project['issues'], (int, str)):
        project['issues'] = [int(project['issues'])]
    project['issues'] = [int(i) for i in project['issues'] if i]

    projects.append(project)

# Sort by exodus_score descending (None last), then name
projects.sort(key=lambda p: (-(p['exodus_score'] or -1), str(p['name']).lower()))

# Full output (for enricher, sync, local dev)
result = {
    'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'count': len(projects),
    'projects': projects,
}

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, 'w') as f:
    json.dump(result, f, indent=2)

# Slim output for the website (short keys, truncated descriptions, no bloat)
slim = []
for p in projects:
    rooms = p.get('channels', {}).get('matrix_rooms', [])
    ch = {k: v for k, v in p.get('channels', {}).items()
          if v and k not in ('matrix_rooms', 'other')}
    # Compact matrix links: keep top 5 by quality
    ml = [{
        't': l.get('target', ''),
        'k': l.get('kind', 'room'),
        'v': l.get('via', ''),
        'src': l.get('source', ''),
        'q': l.get('quality', 0),
    } for l in (p.get('matrix_links') or [])[:5]]

    slim.append({
        's': p['slug'],
        'n': p['name'],
        'd': (p.get('description') or '')[:140],
        'x': p.get('exodus_score'),
        'p': p['platform'],
        'c': p.get('categories', []),
        'r': p.get('repo', ''),
        'w': p.get('website', ''),
        'm': rooms[:3],  # legacy: list of matrix room URLs
        'ml': ml,  # structured matrix links
        'st': p.get('status', ''),
        'i': p.get('issues', []),
        'u': p.get('updated', ''),
        'ls': p.get('last_scanned', ''),
        'ch': ch if ch else None,
    })

# Load score history for trend data
history_file = output_file.replace('projects.json', 'score-history.jsonl')
history = []
if os.path.exists(history_file):
    with open(history_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

# Include last 30 snapshots as trend data
trend = [{'ts': h['ts'], 'avg': h['avg'], 'scanned': h.get('scanned', h.get('scored', 0)), 'dist': h.get('distribution', {})}
         for h in history[-30:]]

slim_file = output_file.replace('projects.json', 'projects-slim.json')
with open(slim_file, 'w') as f:
    json.dump({'c': len(slim), 'p': slim, 'trend': trend}, f, separators=(',', ':'))

full_kb = os.path.getsize(output_file) // 1024
slim_kb = os.path.getsize(slim_file) // 1024
print(f"Built {len(projects)} projects → {output_file} ({full_kb}KB) + {slim_file} ({slim_kb}KB)", file=sys.stderr)
PYEOF
