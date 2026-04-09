#!/usr/bin/env python3
"""
readme-doctor.py — Grade a README for Matrix presence and suggest fixes.

Takes a README from a local file, a GitHub slug, an existing project file,
or stdin, scores it against the same rubric the Exodus enricher uses, and
tells you — concretely, with copy-paste snippets — what to change to raise
the score.

Usage
-----
    # Local file
    python3 scripts/readme-doctor.py ./README.md

    # GitHub slug (fetched via the ReadmeCache)
    python3 scripts/readme-doctor.py element-hq/element-web

    # Existing tracked project (resolves its repo slug from projects/)
    python3 scripts/readme-doctor.py --project element-web

    # stdin
    cat README.md | python3 scripts/readme-doctor.py

Flags
-----
    --snippets     Include copy-paste markdown snippets for each gap.
    --format FMT   text (default) or json.
    --strict       Exit non-zero if score < --threshold. For CI gates.
    --threshold N  Minimum acceptable score when --strict is set (default 5).

Scoring is delegated to `score_full_readme()` in enrich-via-sourcegraph.py
so this tool cannot drift from the canonical rubric.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'

# ── Load the enricher module dynamically ─────────────────────────
# The enricher lives in a file with a dash in its name, so `import` won't
# work. importlib lets us load it by path, and because the enricher's
# module-level code does nothing but define regexes and functions, this
# is safe — no network, no disk writes happen on import.
def _load_enricher():
    # The enricher uses cwd-relative paths (e.g. Path('projects')), so
    # we must chdir to the repo root before importing it, in case this
    # script was invoked from elsewhere.
    os.chdir(REPO_ROOT)
    spec = importlib.util.spec_from_file_location(
        '_enricher', SCRIPTS_DIR / 'enrich-via-sourcegraph.py'
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_enricher = _load_enricher()
score_full_readme = _enricher.score_full_readme
parse_frontmatter = _enricher.parse_frontmatter

# ── Signal checks ────────────────────────────────────────────────
# One row per scoring signal in enrich-via-sourcegraph.py's
# score_full_readme(). `matches` is a predicate over the `signals`
# list returned by the enricher: it decides whether this signal
# was credited. Keeping the detection keyed off enricher output
# (rather than re-parsing the README) ensures this tool stays in
# sync with the rubric.
@dataclass
class SignalCheck:
    key: str
    label: str
    points: int
    matches: Callable[[list[str]], bool]
    advice: str
    snippet: str = ''
    # A signal is "unlockable" only if its prerequisites are met.
    # e.g. "Custom homeserver" can't be claimed without first having
    # a room link at all. We sort the report so prerequisites come
    # first and dependents are flagged as blocked.
    requires: tuple[str, ...] = field(default_factory=tuple)


def _has(prefix: str) -> Callable[[list[str]], bool]:
    return lambda sigs: any(s.startswith(prefix) for s in sigs)


def _exact(name: str) -> Callable[[list[str]], bool]:
    return lambda sigs: name in sigs


SIGNAL_CHECKS: list[SignalCheck] = [
    SignalCheck(
        key='room_link',
        label='matrix.to room link',
        points=2,
        matches=_has('matrix.to room links:'),
        advice=(
            'Add a matrix.to link to your community room. This is the '
            'single biggest lever — worth 2 points and the primary signal '
            'both humans and scanners look for.'
        ),
        snippet=(
            '[![Matrix](https://img.shields.io/matrix/yourproject:matrix.org'
            '?server_fqdn=matrix.org&label=Matrix&logo=matrix)]'
            '(https://matrix.to/#/#yourproject:matrix.org)\n\n'
            'Chat with us on Matrix: '
            '[#yourproject:matrix.org](https://matrix.to/#/#yourproject:matrix.org)'
        ),
    ),
    SignalCheck(
        key='badge',
        label='Matrix shields.io badge',
        points=1,
        matches=_exact('Matrix badge found'),
        advice=(
            'Add a shields.io Matrix badge at the top of the README. '
            'Badges are the most scannable signal — readers and crawlers '
            'both pick them up instantly.'
        ),
        snippet=(
            '[![Matrix](https://img.shields.io/matrix/yourproject:matrix.org'
            '?server_fqdn=matrix.org&label=Matrix&logo=matrix)]'
            '(https://matrix.to/#/#yourproject:matrix.org)'
        ),
    ),
    SignalCheck(
        key='channel_phrase',
        label='"Matrix room/channel/space" phrase',
        points=1,
        matches=_exact('Matrix mentioned as channel'),
        advice=(
            'Write one sentence naming Matrix as a community channel. '
            'The scanner looks for phrases like "join us on Matrix", '
            '"our Matrix room", "Matrix space", "Matrix channel".'
        ),
        snippet=(
            '## Community\n\n'
            'Join us on Matrix in our [project room]'
            '(https://matrix.to/#/#yourproject:matrix.org).'
        ),
    ),
    SignalCheck(
        key='custom_hs',
        label='Custom homeserver',
        points=2,
        matches=_has('Custom homeserver:'),
        advice=(
            'Host your room on your own homeserver so the alias reads '
            '#yourproject:chat.yourproject.org instead of ...:matrix.org. '
            'This is worth 2 points — see docs/howto/homeserver.md.'
        ),
        snippet=(
            '[#yourproject:chat.yourproject.org]'
            '(https://matrix.to/#/#yourproject:chat.yourproject.org)'
        ),
        requires=('room_link',),
    ),
    SignalCheck(
        key='multi_room',
        label='Multiple rooms (3+)',
        points=1,
        matches=_exact('Multiple rooms (3+)'),
        advice=(
            'Link at least three rooms: general, dev, and announcements '
            'are the usual split. If you want one container per team, '
            'promote to a Matrix space — see docs/howto/room-or-space.md.'
        ),
        snippet=(
            '- [#yourproject:matrix.org](https://matrix.to/#/#yourproject:matrix.org) '
            '— general chat\n'
            '- [#yourproject-dev:matrix.org](https://matrix.to/#/#yourproject-dev:matrix.org) '
            '— development\n'
            '- [#yourproject-announce:matrix.org](https://matrix.to/#/#yourproject-announce:matrix.org) '
            '— announcements'
        ),
        requires=('room_link',),
    ),
    SignalCheck(
        key='matrix_first',
        label='Matrix listed before other platforms',
        points=1,
        matches=_exact('Matrix listed before other platforms'),
        advice=(
            'Reorder your community section so Matrix appears BEFORE '
            'Discord/Slack/Telegram. The scanner credits whichever '
            'platform is mentioned first on the line-by-line scan.'
        ),
    ),
    SignalCheck(
        key='bridge',
        label='Bridge mentioned',
        points=1,
        matches=_exact('Bridge mentioned'),
        advice=(
            'If you bridge Discord/Slack/Telegram/IRC into Matrix, say so. '
            'The scanner looks for "bridged to <platform>" or '
            '"mautrix-<platform>" near the word Matrix.'
        ),
        snippet=(
            'Our Matrix room is bridged to Discord via '
            '[mautrix-discord](https://github.com/mautrix/discord), '
            'so either side works.'
        ),
    ),
    SignalCheck(
        key='element',
        label='Element client mentioned',
        points=1,
        matches=_exact('Element client mentioned'),
        advice=(
            'Mention a Matrix client so newcomers know how to join. '
            '[Element](https://element.io) is the canonical one.'
        ),
        snippet=(
            'New to Matrix? Install [Element](https://element.io) and '
            'join [#yourproject:matrix.org]'
            '(https://matrix.to/#/#yourproject:matrix.org).'
        ),
    ),
]


# ── Other-platform detection (red flags, not scoring signals) ────
OTHER_PLATFORM_PREFIXES = (
    'Discord present', 'Telegram present', 'Slack present',
    'WhatsApp present', 'Signal present', 'Zulip present',
    'Mattermost present', 'Rocket.Chat present', 'Gitter present',
)


def detect_red_flags(readme: str, signals: list[str]) -> list[str]:
    """Things that aren't scoring gaps but are worth flagging."""
    flags = []
    present_others = [s for s in signals
                      if any(s.startswith(p) for p in OTHER_PLATFORM_PREFIXES)]
    for s in present_others:
        flags.append(s)
    if 'Gitter present' in signals:
        flags.append(
            'Gitter is deprecated and Matrix-compatible — migrate the '
            'room to a real Matrix alias.'
        )
    if any(s.startswith('Discord present') for s in signals) \
            and 'Matrix listed before other platforms' not in signals \
            and any(s.startswith('matrix.to room links:') for s in signals):
        flags.append(
            'Discord is listed before Matrix — reorder to gain +1.'
        )
    return flags


# ── Input resolution ─────────────────────────────────────────────
def resolve_input(arg: str | None, project: str | None) -> tuple[str, str]:
    """Return (readme_text, source_description)."""
    if project:
        return _load_from_project_slug(project)

    if arg is None:
        data = sys.stdin.read()
        if not data.strip():
            sys.exit('readme-doctor: no input on stdin and no argument given')
        return data, '<stdin>'

    path = Path(arg)
    if path.exists() and path.is_file():
        return path.read_text(encoding='utf-8', errors='replace'), str(path)

    if re.fullmatch(r'[\w.-]+/[\w.-]+', arg):
        return _fetch_slug(arg), f'github:{arg}'

    candidate = REPO_ROOT / 'projects' / f'{arg}.md'
    if candidate.exists():
        return _load_from_project_slug(arg)

    sys.exit(f'readme-doctor: cannot interpret "{arg}" as file, slug, or project')


def _load_from_project_slug(slug: str) -> tuple[str, str]:
    path = REPO_ROOT / 'projects' / f'{slug}.md'
    if not path.exists():
        sys.exit(f'readme-doctor: no project file projects/{slug}.md')
    fm, _ = parse_frontmatter(path.read_text())
    repo = fm.get('repo', '')
    m = re.search(r'github\.com/([^/]+/[^/\s#?.]+)', repo)
    if not m:
        sys.exit(
            f'readme-doctor: projects/{slug}.md has no github.com repo '
            f'(got "{repo}") — can\'t fetch README'
        )
    gh_slug = m.group(1).removesuffix('.git')
    return _fetch_slug(gh_slug), f'project:{slug} ({gh_slug})'


def _fetch_slug(gh_slug: str) -> str:
    from readme_cache import ReadmeCache
    with ReadmeCache() as cache:
        text = cache.get(gh_slug)
    if text is None:
        sys.exit(f'readme-doctor: could not fetch README for {gh_slug}')
    return text


# ── Report rendering ─────────────────────────────────────────────
def build_report(readme: str) -> dict:
    score, signals, rooms = score_full_readme(readme)
    present, missing = [], []
    for check in SIGNAL_CHECKS:
        bucket = present if check.matches(signals) else missing
        bucket.append(check)

    # A missing signal whose prerequisites are also missing is "blocked":
    # you can't earn it yet. We still show it, but after its prereqs.
    present_keys = {c.key for c in present}
    missing_sorted = sorted(
        missing,
        key=lambda c: (
            # unblocked missing signals first, sorted by points desc
            0 if all(r in present_keys for r in c.requires) else 1,
            -c.points,
        ),
    )

    potential = score + sum(c.points for c in missing
                            if all(r in present_keys or
                                   r in {m.key for m in missing_sorted
                                         if all(rr in present_keys
                                                for rr in m.requires)}
                                   for r in c.requires))
    potential = min(potential, 10)

    red_flags = detect_red_flags(readme, signals)

    return {
        'score': score,
        'potential': potential,
        'rooms': rooms,
        'signals_present': [
            {'key': c.key, 'label': c.label, 'points': c.points}
            for c in present
        ],
        'signals_missing': [
            {
                'key': c.key,
                'label': c.label,
                'points': c.points,
                'blocked_by': [r for r in c.requires
                               if r not in present_keys],
                'advice': c.advice,
                'snippet': c.snippet,
            }
            for c in missing_sorted
        ],
        'red_flags': red_flags,
        'other_signals': [s for s in signals
                          if not any(c.matches([s]) for c in SIGNAL_CHECKS)
                          and not any(s.startswith(p)
                                      for p in OTHER_PLATFORM_PREFIXES)],
    }


def render_text(report: dict, source: str, with_snippets: bool) -> str:
    out = []
    out.append(f'README Doctor — {source}')
    out.append('=' * 60)
    out.append('')
    out.append(f'Exodus score: {report["score"]}/10')
    if report['potential'] > report['score']:
        out.append(
            f'Potential:    {report["potential"]}/10  '
            f'(+{report["potential"] - report["score"]} available)'
        )
    out.append('')

    if report['rooms']:
        out.append('Rooms detected:')
        for r in report['rooms']:
            out.append(f'  - {r}')
        out.append('')

    if report['signals_present']:
        out.append('What you have')
        out.append('-' * 60)
        for s in report['signals_present']:
            out.append(f'  [x] {s["label"]:<40} +{s["points"]}')
        out.append('')

    if report['signals_missing']:
        out.append('What to fix (highest impact first)')
        out.append('-' * 60)
        for i, s in enumerate(report['signals_missing'], 1):
            blocked = ''
            if s['blocked_by']:
                blocked = f'  [blocked by: {", ".join(s["blocked_by"])}]'
            out.append(f'  {i}. {s["label"]} (+{s["points"]}){blocked}')
            for line in _wrap(s['advice'], 56):
                out.append(f'       {line}')
            if with_snippets and s['snippet']:
                out.append('')
                out.append('       Snippet:')
                for line in s['snippet'].split('\n'):
                    out.append(f'         {line}')
            out.append('')

    if report['red_flags']:
        out.append('Also noticed')
        out.append('-' * 60)
        for f in report['red_flags']:
            out.append(f'  - {f}')
        out.append('')

    if report['other_signals']:
        out.append('Other signals (non-scoring)')
        out.append('-' * 60)
        for s in report['other_signals']:
            out.append(f'  - {s}')
        out.append('')

    return '\n'.join(out)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur, n = [], [], 0
    for w in words:
        if n + len(w) + (1 if cur else 0) > width and cur:
            lines.append(' '.join(cur))
            cur, n = [w], len(w)
        else:
            cur.append(w)
            n += len(w) + (1 if len(cur) > 1 else 0)
    if cur:
        lines.append(' '.join(cur))
    return lines


# ── CLI ──────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(
        prog='readme-doctor',
        description='Grade a README for Matrix presence and suggest fixes.',
    )
    p.add_argument('target', nargs='?',
                   help='README path, GitHub slug (owner/repo), or project name')
    p.add_argument('--project', metavar='SLUG',
                   help='Load from projects/SLUG.md and fetch its upstream README')
    p.add_argument('--snippets', action='store_true',
                   help='Include copy-paste markdown snippets for each gap')
    p.add_argument('--format', choices=['text', 'json'], default='text')
    p.add_argument('--strict', action='store_true',
                   help='Exit non-zero if score below threshold (CI gate)')
    p.add_argument('--threshold', type=int, default=5,
                   help='Minimum acceptable score in --strict mode (default 5)')
    args = p.parse_args()

    readme, source = resolve_input(args.target, args.project)
    report = build_report(readme)

    if args.format == 'json':
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report, source, args.snippets))

    if args.strict and report['score'] < args.threshold:
        sys.exit(
            f'readme-doctor: score {report["score"]} below '
            f'threshold {args.threshold}'
        )


if __name__ == '__main__':
    main()
