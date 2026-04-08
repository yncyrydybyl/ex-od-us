#!/usr/bin/env python3
"""
enrich-via-sourcegraph.py — Enrich projects using Sourcegraph + raw.githubusercontent.com

No GitHub API rate limits. Two phases:
1. Sourcegraph search: extract matrix.to room links from search match lines.
   Bulk mode runs `matrix.to file:README` + `img.shields.io/matrix file:README`
   across all of Sourcegraph (~6000 results). Single-project mode (--project)
   scopes the queries to one repo with `repo:^github\\.com/owner/name$` and
   also looks for `app.element.io` references.
2. raw.githubusercontent.com: fetch full READMEs for deeper scoring (--full).

Usage:
  python3 scripts/enrich-via-sourcegraph.py [--dry-run] [--full] [--project SLUG] [--summary]

Flags:
  --dry-run    Score and report but don't write project files.
  --full       Also fetch full READMEs via raw.githubusercontent.com for deeper
               scoring. Without it, only Sourcegraph match lines are scored.
  --project SLUG
               Only process the project at projects/<SLUG>.md. Sourcegraph
               queries are scoped to that one repo (much faster than the bulk
               firehose, and finds matches the bulk queries miss because the
               global result cap drops them).
  --summary    Print a structured before/after report to stdout for every
               processed project: repo, match count, score, rooms, signals,
               and a field-level diff of exodus_score / matrix_rooms /
               last_scanned. Auto-enabled when --project is set.

Examples:
  # Recheck one project, full README, preview only:
  python3 scripts/enrich-via-sourcegraph.py --project keepassxc --full --dry-run

  # Recheck one project for real:
  python3 scripts/enrich-via-sourcegraph.py --project keepassxc --full

  # Bulk run, default behavior:
  python3 scripts/enrich-via-sourcegraph.py
"""

import os, sys, re, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(__file__))
from readme_cache import ReadmeCache

PROJECTS_DIR = Path('projects')
SGRAPH = 'https://sourcegraph.com/.api/graphql'

# Room *aliases* start with `#` (human-readable, e.g. #element-web:matrix.org).
# Room *IDs* start with `!` (opaque server-assigned, e.g. !BLOSvIyKTDLIVjRKSc:server).
# matrix.to/#/<target> accepts both forms; we need to capture both.
ROOM_PATTERN = re.compile(
    r'(?:matrix\.to/#/|element\.io/#/room/|/#/room/)'
    r'([#!][a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)'
)
PLAIN_ROOM_PATTERN = re.compile(
    r'(?:^|[`"\s(\[>])(#[a-zA-Z0-9._=-]{2,}:[a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b'
)
# shields.io Matrix badges encode the room as a path segment:
#   img.shields.io/matrix/<room>:<server>
# The room is given without the leading `#`. We capture it and prepend.
# This is one of the most common ways projects advertise their Matrix room.
SHIELDS_PATTERN = re.compile(
    r'img\.shields\.io/matrix/([a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
)
USER_PATTERN = re.compile(r'matrix\.to/#/(@[a-zA-Z0-9._=/-]+:[a-zA-Z0-9.-]+)')

def extract_rooms(text):
    """Extract Matrix room aliases and room IDs from various URL formats,
    plain text, and shields.io badges."""
    text = unquote(text)
    rooms = set(ROOM_PATTERN.findall(text))
    rooms.update(PLAIN_ROOM_PATTERN.findall(text))
    rooms.update('#' + r for r in SHIELDS_PATTERN.findall(text))
    return [r for r in rooms if re.match(r'^[#!][a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', r)]

def log(msg, level='INFO'):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f'[{ts}] {level}: {msg}', file=sys.stderr, flush=True)

# ── Sourcegraph bulk search ─────────────────────────────────────
def sourcegraph_search(query, total=3000, chunk=500):
    """Search Sourcegraph in chunks and return {repo_slug: [matching_lines]}."""
    repo_lines = {}
    fetched = 0

    # Sourcegraph doesn't support offset, but we can use 'after:' cursor
    # Simpler: just request in one go with moderate count, retry on failure
    for attempt_count in [chunk, chunk // 2, chunk // 4]:
        gql = json.dumps({'query': f'query {{ search(query: "{query} count:{attempt_count}", version: V3, patternType: literal) {{ results {{ matchCount results {{ ... on FileMatch {{ repository {{ name }} lineMatches {{ preview }} }} }} }} }} }}'})
        try:
            req = Request(SGRAPH, data=gql.encode(), headers={
                'Content-Type': 'application/json',
                'User-Agent': 'ex-od-us-enricher'
            })
            resp = urlopen(req, timeout=60)
            data = json.loads(resp.read().decode())

            match_count = data.get('data', {}).get('search', {}).get('results', {}).get('matchCount', 0)
            results = data.get('data', {}).get('search', {}).get('results', {}).get('results', [])

            for r in results:
                repo = r.get('repository', {}).get('name', '')
                if not repo.startswith('github.com/'):
                    continue
                slug = repo.removeprefix('github.com/')
                lines = [m.get('preview', '') for m in r.get('lineMatches', [])]
                if slug in repo_lines:
                    repo_lines[slug].extend(lines)
                else:
                    repo_lines[slug] = lines

            log(f'Sourcegraph: {match_count} matches, {len(repo_lines)} repos (chunk {attempt_count})')
            return repo_lines

        except HTTPError as e:
            if e.code == 403:
                log(f'Sourcegraph 403 with count:{attempt_count}, retrying smaller...', 'WARN')
                time.sleep(2)
                continue
            log(f'Sourcegraph error: {e}', 'ERROR')
            return repo_lines
        except Exception as e:
            log(f'Sourcegraph error: {e}', 'ERROR')
            return repo_lines

    log('Sourcegraph: all chunk sizes failed', 'ERROR')
    return repo_lines

# ── Extract signals from match lines ────────────────────────────
def score_from_lines(lines_text):
    """Score Matrix presence from Sourcegraph match lines (not full README)."""
    text = unquote('\n'.join(lines_text))
    score = 0
    signals = []
    rooms = extract_rooms(text)
    users = list(set(USER_PATTERN.findall(text)))

    if rooms:
        score += 2
        signals.append(f'matrix.to room links: {len(rooms)}')
    elif users:
        score += 1
        signals.append(f'matrix.to user links: {len(users)}')

    if re.search(r'shields\.io/matrix|matrix-badge|badge.*matrix', text, re.I):
        score += 1
        signals.append('Matrix badge found')

    # Custom homeserver
    custom_hs = [r.split(':')[1] for r in rooms if ':' in r and 'matrix.org' not in r and 'gitter.im' not in r]
    if custom_hs:
        score += 2
        signals.append(f'Custom homeserver: {custom_hs[0]}')

    if len(rooms) > 2:
        score += 1
        signals.append('Multiple rooms (3+)')

    # ── Other chat networks ───────────────────────────────────────
    if re.search(r'discord\.(gg|com)/invite|discord\s+server', text, re.I):
        signals.append('Discord present')
    if re.search(r't\.me/|telegram\.me/', text, re.I):
        signals.append('Telegram present')
    if re.search(r'slack\.com|join\s.*slack', text, re.I):
        signals.append('Slack present')
    if re.search(r'chat\.whatsapp\.com|wa\.me/', text, re.I):
        signals.append('WhatsApp present')
    if re.search(r'signal\.group', text, re.I):
        signals.append('Signal present')
    irc_m = re.search(r'(libera\.chat|oftc\.net|irc\.freenode)', text, re.I)
    if irc_m:
        irc_chan = re.search(r'(#\S+)\s+on\s+(libera\.chat|oftc\.net|irc\.freenode\S*)', text, re.I)
        if irc_chan:
            signals.append(f'IRC: {irc_chan.group(1)} on {irc_chan.group(2)}')
        else:
            signals.append(f'IRC: {irc_m.group(1)}')
    if re.search(r'zulipchat\.com', text, re.I):
        signals.append('Zulip present')
    if re.search(r'mattermost', text, re.I):
        signals.append('Mattermost present')
    if re.search(r'rocket\.chat', text, re.I):
        signals.append('Rocket.Chat present')
    if re.search(r'gitter\.im', text, re.I):
        signals.append('Gitter present')

    # ── Microblogging / Fediverse ─────────────────────────────────
    mastodon_user = re.search(r'(@\w+@[\w.-]+\.\w+)', text)
    if mastodon_user:
        signals.append(f'Mastodon: {mastodon_user.group(1)}')
    elif re.search(r'mastodon\.(social|online)', text, re.I):
        signals.append('Mastodon present')
    if re.search(r'lemmy', text, re.I):
        signals.append('Lemmy present')
    if re.search(r'peertube', text, re.I):
        signals.append('PeerTube present')
    if re.search(r'activitypub|fediverse', text, re.I):
        signals.append('Fediverse/ActivityPub present')

    # ── Bridge detection ──────────────────────────────────────────
    bridge_m = re.search(r'mautrix-(telegram|discord|signal|whatsapp|slack|facebook|instagram|googlechat|twitter)', text, re.I)
    if bridge_m:
        signals.append(f'Bridge: mautrix-{bridge_m.group(1).lower()}')
    if re.search(r'matrix-appservice-irc', text, re.I):
        signals.append('Bridge: matrix-appservice-irc')
    bridged_m = re.search(r'bridged\s+(?:to|from|with|via)\s+(\w+)', text, re.I)
    if bridged_m:
        signals.append(f'Bridged to {bridged_m.group(1)}')

    # ── Fork detection ────────────────────────────────────────────
    fork_m = re.search(r'(?:fork\s+of|forked\s+from|based\s+on)\s+\[?([^\]\n,]+)', text, re.I)
    if fork_m:
        parent = fork_m.group(1).strip().strip('[]()').split('(')[0].strip()
        if parent:
            signals.append(f'Fork of: {parent}')

    # Validate rooms
    valid_rooms = [r for r in rooms if re.match(r'^#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', r)]

    return min(score, 10), signals, valid_rooms

# Backed by ReadmeCache: persistent etag-conditional cache. The instance
# is constructed once in main() and threaded through; this thin wrapper
# keeps existing call sites unchanged.
_readme_cache: ReadmeCache | None = None

def fetch_raw_readme(slug, branch='HEAD'):  # `branch` kept for back-compat
    """Fetch README via the persistent cache. Returns text or None."""
    if _readme_cache is None:
        # Standalone use (e.g. someone imports this module). Lazily build
        # a cache so behavior matches the legacy direct-fetch path.
        return _readme_cache_oneshot(slug)
    return _readme_cache.get(slug)

def _readme_cache_oneshot(slug: str) -> str | None:
    cache = ReadmeCache()
    text = cache.get(slug)
    cache.flush()
    return text

# ── Full README scoring ─────────────────────────────────────────
def score_full_readme(content):
    """Full scoring from complete README content."""
    text = unquote(content)
    score = 0
    signals = []
    rooms = extract_rooms(text)
    users = list(set(USER_PATTERN.findall(text)))

    if rooms:
        score += 2
        signals.append(f'matrix.to room links: {len(rooms)}')
    elif users:
        score += 1
        signals.append(f'matrix.to user links: {len(users)}')

    if re.search(r'shields\.io/matrix|matrix-badge|badge.*matrix', text, re.I):
        score += 1
        signals.append('Matrix badge found')

    if re.search(r'join\s+(us\s+)?(on|in)\s+matrix|our\s+matrix|matrix\s+room|matrix\s+channel|matrix\s+space', text, re.I):
        score += 1
        signals.append('Matrix mentioned as channel')

    custom_hs = [r.split(':')[1] for r in rooms if ':' in r and 'matrix.org' not in r and 'gitter.im' not in r]
    if custom_hs:
        score += 2
        signals.append(f'Custom homeserver: {custom_hs[0]}')

    if len(rooms) > 2:
        score += 1
        signals.append('Multiple rooms (3+)')

    lines = text.split('\n')
    m_pos = next((i for i, l in enumerate(lines) if re.search(r'matrix', l, re.I)), 9999)
    d_pos = next((i for i, l in enumerate(lines) if re.search(r'discord', l, re.I)), 9999)
    t_pos = next((i for i, l in enumerate(lines) if re.search(r'telegram', l, re.I)), 9999)
    s_pos = next((i for i, l in enumerate(lines) if re.search(r'slack', l, re.I)), 9999)
    if m_pos < min(d_pos, t_pos, s_pos) and m_pos < 9999:
        score += 1
        signals.append('Matrix listed before other platforms')

    if re.search(r'(bridge|bridged|bridging).{0,30}(matrix|element|mautrix)', text, re.I):
        score += 1
        signals.append('Bridge mentioned')

    if re.search(r'element\.(io|im)|app\.element', text, re.I):
        score += 1
        signals.append('Element client mentioned')

    # ── Other chat networks ───────────────────────────────────────
    if re.search(r'discord\.(gg|com)/invite|discord\s+server', text, re.I):
        signals.append('Discord present')
    if re.search(r't\.me/|telegram\.me/', text, re.I):
        signals.append('Telegram present')
    if re.search(r'slack\.com|join\s.*slack', text, re.I):
        signals.append('Slack present')
    if re.search(r'chat\.whatsapp\.com|wa\.me/', text, re.I):
        signals.append('WhatsApp present')
    if re.search(r'signal\.group', text, re.I):
        signals.append('Signal present')
    irc_m = re.search(r'(libera\.chat|oftc\.net|irc\.freenode)', text, re.I)
    if irc_m:
        irc_chan = re.search(r'(#\S+)\s+on\s+(libera\.chat|oftc\.net|irc\.freenode\S*)', text, re.I)
        if irc_chan:
            signals.append(f'IRC: {irc_chan.group(1)} on {irc_chan.group(2)}')
        else:
            signals.append(f'IRC: {irc_m.group(1)}')
    if re.search(r'zulipchat\.com', text, re.I):
        signals.append('Zulip present')
    if re.search(r'mattermost', text, re.I):
        signals.append('Mattermost present')
    if re.search(r'rocket\.chat', text, re.I):
        signals.append('Rocket.Chat present')
    if re.search(r'gitter\.im', text, re.I):
        signals.append('Gitter present')

    # ── Microblogging / Fediverse ─────────────────────────────────
    mastodon_user = re.search(r'(@\w+@[\w.-]+\.\w+)', text)
    if mastodon_user:
        signals.append(f'Mastodon: {mastodon_user.group(1)}')
    elif re.search(r'mastodon\.(social|online)', text, re.I):
        signals.append('Mastodon present')
    if re.search(r'lemmy', text, re.I):
        signals.append('Lemmy present')
    if re.search(r'peertube', text, re.I):
        signals.append('PeerTube present')
    if re.search(r'activitypub|fediverse', text, re.I):
        signals.append('Fediverse/ActivityPub present')

    # ── Bridge detection ──────────────────────────────────────────
    bridge_m = re.search(r'mautrix-(telegram|discord|signal|whatsapp|slack|facebook|instagram|googlechat|twitter)', text, re.I)
    if bridge_m:
        signals.append(f'Bridge: mautrix-{bridge_m.group(1).lower()}')
    if re.search(r'matrix-appservice-irc', text, re.I):
        signals.append('Bridge: matrix-appservice-irc')
    bridged_m = re.search(r'bridged\s+(?:to|from|with|via)\s+(\w+)', text, re.I)
    if bridged_m:
        signals.append(f'Bridged to {bridged_m.group(1)}')

    # ── Fork detection ────────────────────────────────────────────
    fork_m = re.search(r'(?:fork\s+of|forked\s+from|based\s+on)\s+\[?([^\]\n,]+)', text, re.I)
    if fork_m:
        parent = fork_m.group(1).strip().strip('[]()').split('(')[0].strip()
        if parent:
            signals.append(f'Fork of: {parent}')

    valid_rooms = [r for r in rooms if re.match(r'^#[a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', r)]
    return min(score, 10), signals, valid_rooms

# ── Frontmatter helpers ─────────────────────────────────────────
def parse_frontmatter(text):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', text, re.DOTALL)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    fm = {}
    current_key = None
    current_list = None
    for line in raw.split('\n'):
        list_m = re.match(r'^\s+-\s+"?([^"]*)"?\s*$', line)
        if list_m and current_key is not None and current_list is not None:
            current_list.append(list_m.group(1))
            continue
        kv_m = re.match(r'^(\w[\w\-_]*):\s*(.*)', line)
        if kv_m:
            current_key = kv_m.group(1).strip()
            val = kv_m.group(2).strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            current_list = None
            if val.startswith('[') and val.endswith(']'):
                items = [x.strip().strip('"').strip("'") for x in val[1:-1].split(',')]
                fm[current_key] = [x for x in items if x]
            elif val in ('', '[]'):
                current_list = []
                fm[current_key] = current_list
            elif val.lower() == 'true': fm[current_key] = True
            elif val.lower() == 'false': fm[current_key] = False
            elif val.lower() in ('null', '~'): fm[current_key] = None
            else:
                try: fm[current_key] = int(val)
                except ValueError: fm[current_key] = val
    return fm, body.strip()

def write_frontmatter(fm, body):
    lines = ['---']
    for k, v in fm.items():
        if isinstance(v, list):
            if not v: lines.append(f'{k}: []')
            elif all(isinstance(x, str) and ',' not in x and len(x) < 60 for x in v if x is not None):
                lines.append(f'{k}: [{", ".join(str(x) for x in v if x is not None)}]')
            else:
                lines.append(f'{k}:')
                for item in v: lines.append(f'  - "{item}"')
        elif isinstance(v, bool): lines.append(f'{k}: {"true" if v else "false"}')
        elif v is None: lines.append(f'{k}: null')
        elif isinstance(v, int): lines.append(f'{k}: {v}')
        else:
            s = str(v)
            if any(c in s for c in ':"\'#{}[]') or s != s.strip():
                lines.append(f'{k}: "{s}"')
            else: lines.append(f'{k}: {s}')
    lines.append('---')
    if body: lines.append(''); lines.append(body)
    return '\n'.join(lines) + '\n'

# ── Main ────────────────────────────────────────────────────────
def _print_summary(reports, dry_run: bool):
    """Print a structured before/after report for each processed project.
    Goes to stdout (the running log goes to stderr) so it's easy to
    capture or redirect separately."""
    if not reports:
        print('No projects processed.')
        return

    for r in reports:
        fpath = r['fpath']
        before, after = r['fm_before'], r['fm_after']
        print()
        print('=' * 72)
        print(f'  {fpath.stem}  ({fpath})')
        print('=' * 72)
        print(f'  repo:        {after.get("repo", "?")}')
        print(f'  sg matches:  {r["sg_lines"]} line(s)'
              + ('  [used full README]' if r['used_full'] else ''))
        print(f'  score:       {r["score"]}/10')

        if r['rooms']:
            print(f'  rooms ({len(r["rooms"])}):')
            for room in r['rooms']:
                print(f'    - {room}')
        else:
            print(f'  rooms:       (none)')

        if r['signals']:
            print(f'  signals:')
            for s in r['signals']:
                print(f'    · {s}')

        # Diff the fields we actually mutate.
        watched = ('exodus_score', 'matrix_rooms', 'last_scanned')
        diffs = []
        for k in watched:
            b, a = before.get(k), after.get(k)
            if b != a:
                diffs.append((k, b, a))
        if diffs:
            print(f'  changes:')
            for k, b, a in diffs:
                if isinstance(b, list) or isinstance(a, list):
                    bn = len(b) if isinstance(b, list) else 0
                    an = len(a) if isinstance(a, list) else 0
                    print(f'    {k}: {bn} → {an} item(s)')
                else:
                    print(f'    {k}: {b!r} → {a!r}')
        else:
            print(f'  changes:     (none)')

        if dry_run:
            print(f'  [dry-run] no file written')
    print()


def _github_slug_from_repo_url(url: str) -> str | None:
    url = url.strip().rstrip('/')
    gm = re.search(r'github\.com/([^/]+/[^/\s#?.]+)', url)
    if not gm:
        return None
    return gm.group(1).removesuffix('.git')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--full', action='store_true', help='Also fetch full READMEs via raw.githubusercontent.com')
    parser.add_argument('--project', help='Only process this slug')
    parser.add_argument('--summary', action='store_true',
                        help='Print a structured before/after report. Auto-enabled when --project is set.')
    args = parser.parse_args()

    # Single-project mode implies you want to see what happened.
    summary = args.summary or bool(args.project)

    # Open the persistent README cache for the duration of the run.
    # All fetch_raw_readme() calls below route through it.
    global _readme_cache
    _readme_cache = ReadmeCache()

    # Build slug→project file index
    md_files = {f.stem: f for f in sorted(PROJECTS_DIR.glob('*.md'))}

    # Index by repo URL
    slug_to_file = {}
    for fname, fpath in md_files.items():
        content = fpath.read_text()
        m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
        if m:
            github_slug = _github_slug_from_repo_url(m.group(1))
            if github_slug:
                slug_to_file[github_slug.lower()] = fpath

    # Phase 1: Sourcegraph search — scoped if --project, otherwise bulk
    if args.project:
        target_fpath = md_files.get(args.project)
        if not target_fpath:
            log(f'No project file matches slug "{args.project}"', 'ERROR')
            sys.exit(1)
        target_repo = re.search(r'^repo:\s*"?([^"\n]+)',
                                target_fpath.read_text(), re.MULTILINE)
        target_github = _github_slug_from_repo_url(target_repo.group(1)) if target_repo else None
        if not target_github:
            log(f'{args.project}: not a github.com repo, cannot scope Sourcegraph search', 'ERROR')
            sys.exit(1)

        owner, name = target_github.split('/', 1)
        # Two backslashes in source: json.dumps doubles them to four on the wire,
        # the JSON parser unescapes to two in the GraphQL inner string, and the
        # GraphQL string parser collapses `\\` to one literal backslash for the
        # regex. Anything less and Sourcegraph returns "invalid char escape".
        repo_filter = rf'repo:^github\\.com/{re.escape(owner)}/{re.escape(name)}$'
        log(f'Phase 1: Sourcegraph scoped search for {target_github}...')
        sg_results = {}
        for query in [f'matrix.to {repo_filter}',
                      f'img.shields.io/matrix {repo_filter}',
                      f'app.element.io {repo_filter}']:
            results = sourcegraph_search(query)
            for slug, lines in results.items():
                sg_results.setdefault(slug, []).extend(lines)
            time.sleep(1)

        log(f'Found {sum(len(v) for v in sg_results.values())} matching lines '
            f'in {len(sg_results)} repo(s)')
    else:
        log('Phase 1: Sourcegraph bulk search...')
        sg_results = {}
        for query in ['matrix.to file:README', 'img.shields.io/matrix file:README']:
            results = sourcegraph_search(query)
            for slug, lines in results.items():
                sg_results.setdefault(slug, []).extend(lines)
            time.sleep(1)
        log(f'Total: {len(sg_results)} repos with Matrix signals')

    # Phase 2: Enrich project files
    log(f'Phase 2: Enriching {len(slug_to_file)} project files...')
    stats = {'enriched': 0, 'skipped': 0, 'full_fetched': 0}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # Per-project before/after capture for the summary report.
    project_reports = []

    for slug_lower, fpath in slug_to_file.items():
        if args.project and fpath.stem != args.project:
            continue

        content = fpath.read_text()
        fm, body = parse_frontmatter(content)
        fm_before = dict(fm)  # snapshot for summary diff

        # Find Sourcegraph data for this repo (case-insensitive match)
        sg_lines = None
        for sg_slug, lines in sg_results.items():
            if sg_slug.lower() == slug_lower:
                sg_lines = lines
                break

        score, signals, rooms = 0, [], []
        used_full = False

        if sg_lines:
            # Score from Sourcegraph match lines
            score, signals, rooms = score_from_lines(sg_lines)

            # Full README fetch for deeper scoring?
            if args.full and score > 0:
                # Find the original-case slug
                orig_slug = next((s for s in sg_results if s.lower() == slug_lower), slug_lower)
                readme = fetch_raw_readme(orig_slug)
                if readme:
                    score, signals, rooms = score_full_readme(readme)
                    stats['full_fetched'] += 1
                    used_full = True
                # No sleep — fetches are mostly 304s through the cache.

            # Update frontmatter
            changed = False
            room_urls = [f'https://matrix.to/#/{r}' for r in rooms]
            old_rooms = fm.get('matrix_rooms', [])
            if room_urls and set(room_urls) != set(old_rooms):
                fm['matrix_rooms'] = room_urls
                changed = True

            if fm.get('exodus_score') is None and score > 0:
                fm['exodus_score'] = score
                changed = True

            fm['last_scanned'] = now
            changed = True

            if changed:
                stats['enriched'] += 1
                if not args.dry_run:
                    new_content = write_frontmatter(fm, body)
                    fpath.write_text(new_content)
                else:
                    log(f'  Would update {fpath.stem} (score {score}, rooms {len(rooms)})')
        else:
            stats['skipped'] += 1

        if summary:
            project_reports.append({
                'fpath': fpath,
                'fm_before': fm_before,
                'fm_after': dict(fm),
                'score': score,
                'signals': signals,
                'rooms': rooms,
                'sg_lines': len(sg_lines) if sg_lines else 0,
                'used_full': used_full,
            })

    # Persist the README cache index. The bytes were written incrementally
    # by ReadmeCache.get(); only the index needs flushing here.
    _readme_cache.flush()

    if summary:
        _print_summary(project_reports, dry_run=args.dry_run)

    log('')
    log(f'Done. Enriched: {stats["enriched"]}, Skipped: {stats["skipped"]}, Full READMEs: {stats["full_fetched"]}')
    log(_readme_cache.report())

    # Rebuild JSON
    if not args.dry_run and stats['enriched'] > 0:
        import subprocess
        log('Rebuilding projects.json...')
        subprocess.run(['bash', 'scripts/build-projects.sh'], capture_output=True, text=True)
        log('Done.')

if __name__ == '__main__':
    main()
