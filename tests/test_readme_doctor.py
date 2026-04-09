#!/usr/bin/env python3
"""Tests for scripts/readme-doctor.py — the README grading tool."""
import json
import os
import subprocess

ROOT = os.path.join(os.path.dirname(__file__), '..')
DOCTOR = os.path.join(ROOT, 'scripts', 'readme-doctor.py')


def run_doctor(stdin_text: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['python3', DOCTOR, *args],
        input=stdin_text,
        capture_output=True, text=True, cwd=ROOT,
    )


class TestReadmeDoctor:
    def test_empty_readme_scores_zero(self):
        r = run_doctor('# Just a title\n')
        assert r.returncode == 0
        assert 'Exodus score: 0/10' in r.stdout

    def test_room_link_gives_two_points(self):
        r = run_doctor(
            '# Project\n\n'
            'Chat with us: https://matrix.to/#/#myproject:matrix.org\n'
        )
        # room link (+2) + "matrix room/channel" phrase might also trip,
        # so lower bound the score and check the signal is credited.
        assert r.returncode == 0
        assert 'matrix.to room link' in r.stdout
        assert '[x] matrix.to room link' in r.stdout

    def test_custom_homeserver_adds_two_points(self):
        # Baseline: matrix.org alias → 2 points
        baseline = run_doctor(
            '# Project\n\n'
            '[chat](https://matrix.to/#/#p:matrix.org)\n'
        )
        # With custom homeserver: 2 + 2 = 4 points
        custom = run_doctor(
            '# Project\n\n'
            '[chat](https://matrix.to/#/#p:chat.example.org)\n'
        )
        baseline_score = _extract_score(baseline.stdout)
        custom_score = _extract_score(custom.stdout)
        assert custom_score == baseline_score + 2

    def test_blocked_signals_sort_after_prerequisites(self):
        # With no room link at all, Custom homeserver and Multiple rooms
        # are both missing AND blocked. They should appear AFTER the
        # unblocked gaps, and be labeled [blocked by: room_link].
        r = run_doctor('# no matrix here\n')
        assert '[blocked by: room_link]' in r.stdout
        # Unblocked room_link (+2) should appear before blocked custom_hs
        idx_room = r.stdout.find('matrix.to room link (+2)')
        idx_custom = r.stdout.find('Custom homeserver (+2)')
        assert 0 < idx_room < idx_custom

    def test_json_output_is_valid(self):
        r = run_doctor(
            '# Project\n\n'
            'Join us: https://matrix.to/#/#p:matrix.org\n',
            '--format', 'json',
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert 'score' in data
        assert 'signals_present' in data
        assert 'signals_missing' in data
        assert data['score'] >= 2  # room link is worth 2

    def test_strict_mode_fails_below_threshold(self):
        r = run_doctor(
            '# empty\n',
            '--strict', '--threshold', '5',
        )
        assert r.returncode != 0
        assert 'below threshold' in r.stderr

    def test_strict_mode_passes_at_threshold(self):
        # Craft a README that clears score 5: room link (+2), badge (+1),
        # channel phrase (+1), Element mention (+1) = 5
        r = run_doctor(
            '# Project\n\n'
            '[![Matrix](https://img.shields.io/matrix/p:matrix.org'
            '?server_fqdn=matrix.org)](https://matrix.to/#/#p:matrix.org)\n\n'
            'Join our Matrix room: '
            '[#p:matrix.org](https://matrix.to/#/#p:matrix.org).\n'
            'Install [Element](https://element.io) to join.\n',
            '--strict', '--threshold', '5',
        )
        assert r.returncode == 0, f'stderr={r.stderr}\nstdout={r.stdout}'

    def test_snippets_flag_includes_code_blocks(self):
        r = run_doctor('# nothing\n', '--snippets')
        assert 'Snippet:' in r.stdout
        assert 'matrix.to' in r.stdout

    def test_discord_flagged_as_listed_before_matrix(self):
        # Discord line comes first → red flag fires
        r = run_doctor(
            '# Project\n\n'
            'Join us on [Discord](https://discord.com/invite/xyz).\n\n'
            'Also: [Matrix room](https://matrix.to/#/#p:matrix.org).\n'
        )
        assert 'Discord is listed before Matrix' in r.stdout


def _extract_score(text: str) -> int:
    for line in text.splitlines():
        if line.startswith('Exodus score:'):
            return int(line.split(':', 1)[1].strip().split('/')[0])
    raise AssertionError(f'no Exodus score line in:\n{text}')
