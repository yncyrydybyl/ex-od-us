"""
matrix_links.py — Extract structured Matrix links from README content.

Returns a sorted list of link records:
  {
    target: "#room:server.org",   # canonical Matrix entity
    kind: "room",                  # room | space | user
    url: "https://...",            # the actual URL found
    via: "matrix.to",              # routing: matrix.to | element-web | matrix-uri | client:host | text
    source: "badge",               # context: badge | anchor | code | text
    homeserver: "server.org",      # extracted from target
    quality: 10,                   # 0-10 sort key (higher = better)
  }
"""
import re
from urllib.parse import unquote

# Matrix entity patterns
ROOM_ID_RE = r'#[a-zA-Z0-9._=-]{1,200}:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
USER_ID_RE = r'@[a-zA-Z0-9._=-]{1,200}:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
SPACE_ID_RE = r'\+[a-zA-Z0-9._=-]{1,200}:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# URL patterns: capture (host, path, target)
# Group 1 = host (matrix.to, app.element.io, chat.opensuse.org, etc.)
# Group 2 = the matrix entity ID
LINK_RE = re.compile(
    r'https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
    r'/(?:#/)?(?:room/)?(' + ROOM_ID_RE + '|' + USER_ID_RE + '|' + SPACE_ID_RE + ')',
    re.IGNORECASE
)

# matrix: URI scheme
URI_RE = re.compile(
    r'matrix:(?:r|roomid|u|user|space)/([a-zA-Z0-9._=-]+:[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE
)

# Plain text room IDs (no URL wrapper)
PLAIN_ROOM_RE = re.compile(r'(?:^|[`"\s(\[>])(' + ROOM_ID_RE + r')\b')
PLAIN_USER_RE = re.compile(r'(?:^|[`"\s(\[>])(' + USER_ID_RE + r')\b')
PLAIN_SPACE_RE = re.compile(r'(?:^|[`"\s(\[>])(' + SPACE_ID_RE + r')\b')

# Source detection patterns
BADGE_HOSTS = ('shields.io', 'badge.fury.io', 'img.shields.io', 'badgen.net')


def classify_kind(target):
    if target.startswith('#'): return 'room'
    if target.startswith('@'): return 'user'
    if target.startswith('+'): return 'space'
    return 'unknown'


def classify_via(host):
    """Classify a link host into a 'via' category."""
    h = host.lower()
    if h == 'matrix.to':
        return 'matrix.to'
    if h == 'app.element.io':
        return 'element-web'
    if h == 'element.io':
        return 'element-io'
    if h == 'app.cinny.in':
        return 'cinny'
    if h.startswith('chat.') or h.startswith('matrix.') or h.startswith('element.'):
        return f'client:{h}'
    return f'client:{h}'


def is_in_badge(text, match_start):
    """Check if a link match is inside a shields.io badge image."""
    # Look backwards for shields.io domain in the surrounding context
    window = text[max(0, match_start - 200):match_start]
    return any(host in window for host in BADGE_HOSTS) or 'badge' in window.lower()[-50:]


def is_in_anchor(text, match_start, match_end):
    """Check if a link match is wrapped in a markdown link [..](url) or HTML <a>."""
    # Look backwards for [..]( and forwards for )
    before = text[max(0, match_start - 5):match_start]
    return '](' in before or '<a ' in text[max(0, match_start - 50):match_start]


def is_in_code(text, match_start):
    """Check if a match is inside backticks or fenced code."""
    line_start = text.rfind('\n', 0, match_start) + 1
    line = text[line_start:match_start]
    # Backticks before, not closed
    return line.count('`') % 2 == 1


def quality_score(via, source, kind):
    """Compute a 0-10 quality score for sorting."""
    score = 0
    # Routing intent
    if via == 'matrix.to':
        score += 4
    elif via.startswith('client:'):
        score += 5  # custom homeserver = highest intent
    elif via == 'element-web':
        score += 3
    elif via == 'element-io':
        score += 1
    elif via == 'matrix-uri':
        score += 4
    elif via == 'plain-text':
        score += 1
    # Source prominence
    if source == 'badge':
        score += 5
    elif source == 'anchor':
        score += 3
    elif source == 'code':
        score += 2
    elif source == 'text':
        score += 1
    # Spaces are slightly higher signal than rooms
    if kind == 'space':
        score += 1
    return min(score, 10)


def extract_matrix_links(content):
    """Extract structured Matrix links from README content."""
    text = unquote(content)
    found = {}  # dedupe by target

    # Pass 1: URL-based links (matrix.to, element-web, custom hosts)
    for m in LINK_RE.finditer(text):
        host = m.group(1)
        target = m.group(2)
        url = m.group(0)

        kind = classify_kind(target)
        if kind == 'unknown':
            continue
        via = classify_via(host)

        # Determine source
        if is_in_badge(text, m.start()):
            source = 'badge'
        elif is_in_anchor(text, m.start(), m.end()):
            source = 'anchor'
        elif is_in_code(text, m.start()):
            source = 'code'
        else:
            source = 'text'

        homeserver = target.split(':', 1)[1] if ':' in target else ''
        key = target.lower()

        record = {
            'target': target,
            'kind': kind,
            'url': url,
            'via': via,
            'source': source,
            'homeserver': homeserver,
            'quality': quality_score(via, source, kind),
        }
        # Keep highest-quality version of duplicates
        if key not in found or record['quality'] > found[key]['quality']:
            found[key] = record

    # Pass 2: matrix: URI scheme
    for m in URI_RE.finditer(text):
        target_part = m.group(1)
        # matrix:r/room:server → #room:server
        # matrix:u/user:server → @user:server
        prefix = '#' if 'r' in m.group(0)[:10] and 'u' not in m.group(0)[:10].lower() else '@'
        if 'space' in m.group(0)[:15].lower(): prefix = '+'
        target = prefix + target_part
        kind = classify_kind(target)
        if kind == 'unknown': continue
        homeserver = target.split(':', 1)[1] if ':' in target else ''
        key = target.lower()
        if key in found: continue
        found[key] = {
            'target': target,
            'kind': kind,
            'url': m.group(0),
            'via': 'matrix-uri',
            'source': 'anchor',
            'homeserver': homeserver,
            'quality': quality_score('matrix-uri', 'anchor', kind),
        }

    # Pass 3: plain text room/user/space IDs (only if not already found)
    for pattern, kind in [(PLAIN_ROOM_RE, 'room'), (PLAIN_USER_RE, 'user'), (PLAIN_SPACE_RE, 'space')]:
        for m in pattern.finditer(text):
            target = m.group(1)
            key = target.lower()
            if key in found: continue
            homeserver = target.split(':', 1)[1] if ':' in target else ''
            source = 'code' if is_in_code(text, m.start()) else 'text'
            found[key] = {
                'target': target,
                'kind': kind,
                'url': f'https://matrix.to/#/{target}',  # synthesize a matrix.to URL
                'via': 'plain-text',
                'source': source,
                'homeserver': homeserver,
                'quality': quality_score('plain-text', source, kind),
            }

    # Sort by quality desc, then by kind (rooms before users), then alpha
    return sorted(found.values(), key=lambda r: (-r['quality'], r['kind'], r['target'].lower()))
