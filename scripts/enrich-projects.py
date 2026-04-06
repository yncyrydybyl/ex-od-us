#!/usr/bin/env python3
"""
enrich-projects.py — Unified pipeline to enrich project files with live data.

For each project in projects/*.md that has a repo URL:
1. Fetch the README via GitHub API (with ETag caching)
2. Score Matrix presence
3. Extract Matrix room links
4. Write findings back into the project markdown file
5. Rebuild data/projects.json

Designed to be idempotent and failure-isolated:
- Each project is processed independently; one failure doesn't stop others
- API calls retry with exponential backoff
- ETag caching avoids redundant fetches
- Data is validated before writing
- Writes are atomic (write to temp, validate, move)

Usage:
  python3 scripts/enrich-projects.py [--dry-run] [--force] [--project SLUG]

Requires: gh CLI (authenticated) or GITHUB_TOKEN env var
"""

import os, sys, re, json, time, shutil, subprocess, base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── Config ──────────────────────────────────────────────────────
PROJECTS_DIR = Path('projects')
CACHE_FILE = Path('data/readme-cache.json')
OUTPUT_FILE = Path('data/projects.json')
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, doubles each retry
RATE_LIMIT_DELAY = 0.5  # seconds between API calls

# ── Auth ────────────────────────────────────────────────────────
def get_token():
    """Get GitHub token from gh CLI or environment."""
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        return token
    try:
        result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None

TOKEN = get_token()

# ── HTTP with retries ───────────────────────────────────────────
def api_get(url, headers=None, etag=None):
    """GET with retries, ETag support, and rate limit handling."""
    if headers is None:
        headers = {}
    headers['Accept'] = 'application/vnd.github.v3+json'
    headers['User-Agent'] = 'ex-od-us-enricher'
    if TOKEN:
        headers['Authorization'] = f'token {TOKEN}'
    if etag:
        headers['If-None-Match'] = etag

    delay = RETRY_DELAY
    for attempt in range(MAX_RETRIES):
        try:
            req = Request(url, headers=headers)
            resp = urlopen(req, timeout=30)
            new_etag = resp.headers.get('ETag', '')
            body = resp.read().decode('utf-8')
            return {'status': resp.status, 'body': body, 'etag': new_etag}
        except HTTPError as e:
            if e.code == 304:
                return {'status': 304, 'body': None, 'etag': etag}
            if e.code == 403 and 'rate limit' in str(e.read()).lower():
                wait = int(e.headers.get('Retry-After', 60))
                log(f'    Rate limited. Waiting {wait}s...', 'WARN')
                time.sleep(wait)
                continue
            if e.code == 404:
                return {'status': 404, 'body': None, 'etag': ''}
            if attempt < MAX_RETRIES - 1:
                log(f'    HTTP {e.code}, retrying in {delay}s...', 'WARN')
                time.sleep(delay)
                delay *= 2
                continue
            return {'status': e.code, 'body': None, 'etag': ''}
        except (URLError, TimeoutError) as e:
            if attempt < MAX_RETRIES - 1:
                log(f'    Network error: {e}, retrying in {delay}s...', 'WARN')
                time.sleep(delay)
                delay *= 2
                continue
            return {'status': 0, 'body': None, 'etag': ''}

# ── Logging ─────────────────────────────────────────────────────
def log(msg, level='INFO'):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f'[{ts}] {level}: {msg}', file=sys.stderr)

# ── YAML frontmatter parser ─────────────────────────────────────
def parse_frontmatter(text):
    """Parse YAML frontmatter. Returns (dict, body_text)."""
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    fm = {}
    current_key = None
    current_list = None

    for line in raw.split('\n'):
        # List item
        list_m = re.match(r'^\s+-\s+"?([^"]*)"?\s*$', line)
        if list_m and current_key is not None and current_list is not None:
            current_list.append(list_m.group(1))
            continue

        # Key: value
        kv_m = re.match(r'^(\w[\w\-_]*):\s*(.*)', line)
        if kv_m:
            current_key = kv_m.group(1).strip()
            val = kv_m.group(2).strip()
            current_list = None

            # Remove surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]

            # Inline list: [a, b, c]
            if val.startswith('[') and val.endswith(']'):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(',')]
                fm[current_key] = [x for x in items if x]
                current_list = fm[current_key]
            elif val == '' or val == '[]':
                fm[current_key] = []
                current_list = fm[current_key]
            elif val.lower() == 'true':
                fm[current_key] = True
            elif val.lower() == 'false':
                fm[current_key] = False
            elif val.lower() in ('null', '~'):
                fm[current_key] = None
            else:
                try:
                    fm[current_key] = int(val)
                except ValueError:
                    fm[current_key] = val
            continue

    return fm, body.strip()

def write_frontmatter(fm, body):
    """Serialize frontmatter dict + body back to markdown."""
    lines = ['---']
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                lines.append(f'{k}: []')
            elif all(isinstance(x, str) and ',' not in x and len(x) < 60 for x in v):
                lines.append(f'{k}: [{", ".join(v)}]')
            else:
                lines.append(f'{k}:')
                for item in v:
                    lines.append(f'  - "{item}"')
        elif isinstance(v, bool):
            lines.append(f'{k}: {"true" if v else "false"}')
        elif v is None:
            lines.append(f'{k}: null')
        elif isinstance(v, int):
            lines.append(f'{k}: {v}')
        else:
            s = str(v)
            if any(c in s for c in ':"\'#{}[]') or s != s.strip():
                lines.append(f'{k}: "{s}"')
            else:
                lines.append(f'{k}: {s}')
    lines.append('---')
    if body:
        lines.append('')
        lines.append(body)
    return '\n'.join(lines) + '\n'

# ── Matrix scoring ──────────────────────────────────────────────
ROOM_PATTERN = re.compile(r'matrix\.to/#/(#[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)')
USER_PATTERN = re.compile(r'matrix\.to/#/(@[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)')

def score_readme(content):
    """Score Matrix presence in a README. Returns (score, signals, rooms)."""
    score = 0
    signals = []
    rooms = list(set(ROOM_PATTERN.findall(content)))

    # Also detect user links (@user:server)
    users = list(set(USER_PATTERN.findall(content)))

    if rooms:
        score += 2
        signals.append(f'matrix.to room links: {len(rooms)}')
    elif users:
        score += 1
        signals.append(f'matrix.to user links: {len(users)}')

    if re.search(r'shields\.io/matrix|matrix-badge|badge.*matrix', content, re.I):
        score += 1
        signals.append('Matrix badge found')

    if re.search(r'join\s+(us\s+)?(on|in)\s+matrix|our\s+matrix|matrix\s+room|matrix\s+channel|matrix\s+space', content, re.I):
        score += 1
        signals.append('Matrix mentioned as channel')

    # Own homeserver (not matrix.org)
    custom_hs = [r.split(':')[1] for r in rooms if ':' in r and 'matrix.org' not in r and 'gitter.im' not in r]
    if custom_hs:
        score += 2
        signals.append(f'Custom homeserver: {custom_hs[0]}')

    if len(rooms) > 2:
        score += 1
        signals.append('Multiple Matrix rooms (3+)')

    # Matrix listed before other platforms
    m_pos = next((i for i, l in enumerate(content.split('\n')) if re.search(r'matrix', l, re.I)), 9999)
    d_pos = next((i for i, l in enumerate(content.split('\n')) if re.search(r'discord', l, re.I)), 9999)
    t_pos = next((i for i, l in enumerate(content.split('\n')) if re.search(r'telegram', l, re.I)), 9999)
    s_pos = next((i for i, l in enumerate(content.split('\n')) if re.search(r'slack', l, re.I)), 9999)
    if m_pos < min(d_pos, t_pos, s_pos) and m_pos < 9999:
        score += 1
        signals.append('Matrix listed before other platforms')

    if re.search(r'(bridge|bridged|bridging).{0,30}(matrix|element|mautrix)', content, re.I):
        score += 1
        signals.append('Bridge mentioned')

    if re.search(r'element\.(io|im)|app\.element', content, re.I):
        score += 1
        signals.append('Element client mentioned')

    # Detect other platforms
    if re.search(r'discord\.(gg|com)/|join.*discord|discord\s+server', content, re.I):
        signals.append('Discord present')
    if re.search(r't\.me/|telegram\.me/|join.*telegram', content, re.I):
        signals.append('Telegram present')
    if re.search(r'slack\.(com|gg)|join.*slack', content, re.I):
        signals.append('Slack present')
    if re.search(r'libera\.chat|oftc\.net|irc\.(freenode|oftc|libera)', content, re.I):
        signals.append('IRC present')

    return min(score, 10), signals, rooms

# ── Validate a room link ────────────────────────────────────────
def validate_room(room_id):
    """Check if a room ID looks valid: #name:server.tld"""
    return bool(re.match(r'^#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', room_id))

# ── Check matrixrooms.info ──────────────────────────────────────
def check_matrixrooms(room_id):
    """Check if a room is listed on matrixrooms.info."""
    from urllib.parse import quote
    url = f'https://matrixrooms.info/room/{quote(room_id, safe="")}'
    try:
        req = Request(url, method='HEAD')
        req.add_header('User-Agent', 'ex-od-us-enricher')
        resp = urlopen(req, timeout=10)
        return resp.status == 200
    except Exception:
        return False

# ── Liveness checks ─────────────────────────────────────────────
def check_repo_alive(gh_slug):
    """Check if a GitHub repo exists and is accessible. Returns (alive, note)."""
    resp = api_get(f'https://api.github.com/repos/{gh_slug}')
    if resp['status'] == 200:
        data = json.loads(resp['body'])
        if data.get('archived'):
            return True, 'repo archived'
        return True, 'repo alive'
    elif resp['status'] == 404:
        return False, 'repo not found (404)'
    elif resp['status'] == 451:
        return False, 'repo unavailable for legal reasons (451)'
    else:
        return None, f'repo check failed (HTTP {resp["status"]})'

def check_matrix_room_alive(room_id):
    """Check if a Matrix room is discoverable via client API.
    Uses matrix.org's client API to check if the room alias resolves."""
    from urllib.parse import quote
    # Try resolving the room alias via matrix.org
    alias = quote(room_id, safe='')
    try:
        req = Request(f'https://matrix-client.matrix.org/_matrix/client/v3/directory/room/{alias}')
        req.add_header('User-Agent', 'ex-od-us-enricher')
        resp = urlopen(req, timeout=10)
        if resp.status == 200:
            return True, 'room alias resolves'
    except HTTPError as e:
        if e.code == 404:
            return False, 'room alias not found'
        return None, f'room check error (HTTP {e.code})'
    except Exception as e:
        return None, f'room check failed ({e})'
    return None, 'room check inconclusive'

# ── Extract GitHub slug from repo URL ───────────────────────────
def repo_slug(url):
    """Extract owner/repo from a GitHub URL."""
    m = re.search(r'github\.com[/:]([^/]+/[^/\s#?.]+)', url)
    if m:
        return m.group(1).removesuffix('.git').rstrip('/')
    return None

# ── Main pipeline ───────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Enrich project files with live data')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without writing')
    parser.add_argument('--force', action='store_true', help='Ignore ETag cache, re-fetch everything')
    parser.add_argument('--project', help='Only process this project slug')
    parser.add_argument('--skip-matrixrooms', action='store_true', help='Skip matrixrooms.info checks')
    args = parser.parse_args()

    if not TOKEN:
        log('No GitHub token found. Using unauthenticated API (60 req/hr).', 'WARN')
        log('Run "gh auth login" or set GITHUB_TOKEN for 5000 req/hr.', 'WARN')

    # Load cache
    cache = {}
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            log('Cache file corrupt, starting fresh.', 'WARN')

    # Collect project files
    md_files = sorted(PROJECTS_DIR.glob('*.md'))
    if args.project:
        md_files = [f for f in md_files if f.stem == args.project]
        if not md_files:
            log(f'Project "{args.project}" not found.', 'ERROR')
            sys.exit(1)

    log(f'Processing {len(md_files)} projects...')

    stats = {'processed': 0, 'enriched': 0, 'skipped': 0, 'errors': 0, 'unchanged': 0}

    for md_path in md_files:
        slug = md_path.stem
        try:
            content = md_path.read_text()
            fm, body = parse_frontmatter(content)

            repo_url = fm.get('repo', '')
            gh_slug = repo_slug(repo_url)

            if not gh_slug:
                stats['skipped'] += 1
                continue

            stats['processed'] += 1
            log(f'  {slug} ({gh_slug})')

            # Fetch README
            cached = cache.get(gh_slug, {})
            etag = cached.get('etag', '') if not args.force else ''

            resp = api_get(f'https://api.github.com/repos/{gh_slug}/readme', etag=etag)
            time.sleep(RATE_LIMIT_DELAY)

            if resp['status'] == 304:
                log(f'    Unchanged (304)')
                stats['unchanged'] += 1
                # Still update last_scanned
                fm['last_scanned'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                if not args.dry_run:
                    new_content = write_frontmatter(fm, body)
                    md_path.write_text(new_content)
                continue

            if resp['status'] == 404:
                # Repo README not found — check if repo itself is dead
                repo_alive, repo_note = check_repo_alive(gh_slug)
                time.sleep(RATE_LIMIT_DELAY)
                if repo_alive is False:
                    log(f'    DEAD: {repo_note}', 'WARN')
                    fm['verified'] = False
                    fm['verified_note'] = repo_note
                    fm['status'] = 'Dead'
                    fm['last_scanned'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                    if not args.dry_run:
                        new_content = write_frontmatter(fm, body)
                        md_path.write_text(new_content)
                    stats['enriched'] += 1
                else:
                    log(f'    No README but repo exists ({repo_note})', 'WARN')
                    stats['errors'] += 1
                continue

            if resp['status'] != 200:
                log(f'    Failed: HTTP {resp["status"]}', 'WARN')
                stats['errors'] += 1
                continue

            # Decode README
            data = json.loads(resp['body'])
            readme_b64 = data.get('content', '')
            try:
                readme_text = base64.b64decode(readme_b64).decode('utf-8', errors='replace')
            except Exception:
                log(f'    Failed to decode README', 'WARN')
                stats['errors'] += 1
                continue

            if not readme_text.strip():
                log(f'    Empty README')
                stats['skipped'] += 1
                continue

            # Score
            score, signals, rooms = score_readme(readme_text)
            valid_rooms = [r for r in rooms if validate_room(r)]

            # Check matrixrooms.info for first valid room
            listed_on_matrixrooms = False
            if valid_rooms and not args.skip_matrixrooms:
                listed_on_matrixrooms = check_matrixrooms(valid_rooms[0])
                if listed_on_matrixrooms:
                    score = min(score + 1, 10)
                    signals.append('Listed on matrixrooms.info')
                time.sleep(RATE_LIMIT_DELAY)

            # Check Matrix room liveness (first room only)
            room_alive = None
            if valid_rooms and not args.skip_matrixrooms:
                room_alive, room_note = check_matrix_room_alive(valid_rooms[0])
                time.sleep(RATE_LIMIT_DELAY)
                if room_alive is False:
                    signals.append(f'Matrix room dead: {room_note}')
                elif room_alive is True:
                    signals.append('Matrix room verified alive')

            log(f'    Score: {score}/10 | Rooms: {len(valid_rooms)} | Signals: {len(signals)}')

            # Update frontmatter
            changed = False

            # Verification status
            fm['verified'] = True
            fm['verified_note'] = 'repo alive' + (', room alive' if room_alive else ', room not checked' if room_alive is None else ', room dead')

            # Matrix rooms
            room_urls = [f'https://matrix.to/#/{r}' for r in valid_rooms]
            old_rooms = fm.get('matrix_rooms', [])
            if set(room_urls) != set(old_rooms) and room_urls:
                fm['matrix_rooms'] = room_urls
                changed = True

            # Scanner score (only write if we don't have a manual score)
            if fm.get('exodus_score') is None and score > 0:
                fm['exodus_score'] = score
                changed = True

            # Scanner metadata
            fm['last_scanned'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            changed = True

            # Update cache
            cache[gh_slug] = {
                'sha': data.get('sha', ''),
                'etag': resp['etag'],
                'score': score,
                'signals': signals,
                'rooms': valid_rooms,
                'listed_on_matrixrooms': listed_on_matrixrooms,
                'scanned': fm['last_scanned'],
            }

            if changed:
                stats['enriched'] += 1
                if args.dry_run:
                    log(f'    Would update {slug}.md')
                else:
                    # Atomic write: temp file, validate, move
                    new_content = write_frontmatter(fm, body)
                    tmp = md_path.with_suffix('.md.tmp')
                    tmp.write_text(new_content)
                    # Validate: can we parse what we just wrote?
                    test_fm, _ = parse_frontmatter(tmp.read_text())
                    if test_fm.get('name'):
                        shutil.move(str(tmp), str(md_path))
                    else:
                        log(f'    Validation failed, keeping original', 'ERROR')
                        tmp.unlink()
                        stats['errors'] += 1
                        stats['enriched'] -= 1
            else:
                stats['unchanged'] += 1

        except Exception as e:
            log(f'    Error processing {slug}: {e}', 'ERROR')
            stats['errors'] += 1
            continue

    # Write cache
    if not args.dry_run:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=2))

    # Summary
    log('')
    log(f'Done. Processed: {stats["processed"]}, Enriched: {stats["enriched"]}, '
        f'Unchanged: {stats["unchanged"]}, Skipped: {stats["skipped"]}, Errors: {stats["errors"]}')

    # Build projects.json
    if not args.dry_run and stats['enriched'] > 0:
        log('Rebuilding projects.json...')
        result = subprocess.run(['bash', 'scripts/build-projects.sh'], capture_output=True, text=True)
        if result.returncode == 0:
            log('projects.json rebuilt.')
        else:
            log(f'build-projects.sh failed: {result.stderr}', 'ERROR')

    return 0 if stats['errors'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
