#!/usr/bin/env python3
"""Tests for enrich-projects.py — scoring, validation, liveness."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Import functions from enrich-projects.py
import importlib.util
spec = importlib.util.spec_from_file_location(
    "enrich", os.path.join(os.path.dirname(__file__), '..', 'scripts', 'enrich-projects.py'))
enrich = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enrich)

import pytest


class TestScoreReadme:
    """Test Matrix presence scoring."""

    def test_empty_readme(self):
        score, signals, rooms = enrich.score_readme('')
        assert score == 0
        assert signals == []
        assert rooms == []

    def test_single_matrix_room(self):
        readme = 'Join us on [Matrix](https://matrix.to/#/#project:matrix.org)'
        score, signals, rooms = enrich.score_readme(readme)
        assert score >= 2
        assert len(rooms) == 1
        assert rooms[0] == '#project:matrix.org'

    def test_matrix_badge(self):
        readme = '![Matrix](https://img.shields.io/matrix/room:matrix.org)'
        score, signals, rooms = enrich.score_readme(readme)
        assert any('badge' in s.lower() for s in signals)

    def test_custom_homeserver(self):
        readme = 'Chat: https://matrix.to/#/#dev:custom.server.org'
        score, signals, rooms = enrich.score_readme(readme)
        assert any('Custom homeserver' in s for s in signals)
        assert score >= 4  # room link (2) + custom hs (2)

    def test_multiple_rooms(self):
        readme = """
        https://matrix.to/#/#general:matrix.org
        https://matrix.to/#/#dev:matrix.org
        https://matrix.to/#/#support:matrix.org
        """
        score, signals, rooms = enrich.score_readme(readme)
        assert len(rooms) == 3
        assert any('Multiple' in s for s in signals)

    def test_matrix_before_discord(self):
        readme = """
        ## Chat
        Join our Matrix room: https://matrix.to/#/#project:matrix.org
        Or Discord: https://discord.gg/invite
        """
        score, signals, rooms = enrich.score_readme(readme)
        assert any('listed before' in s.lower() for s in signals)

    def test_discord_before_matrix(self):
        readme = """
        ## Chat
        Join Discord: https://discord.gg/invite
        Or Matrix: https://matrix.to/#/#project:matrix.org
        """
        score, signals, rooms = enrich.score_readme(readme)
        assert not any('listed before' in s.lower() for s in signals)

    def test_bridge_mention(self):
        readme = 'This room is bridged to Matrix via mautrix-discord'
        score, signals, rooms = enrich.score_readme(readme)
        assert any('Bridge' in s for s in signals)

    def test_element_mention(self):
        readme = 'Use Element.io to join'
        score, signals, rooms = enrich.score_readme(readme)
        assert any('Element' in s for s in signals)

    def test_score_capped_at_10(self):
        readme = """
        https://matrix.to/#/#a:custom.org
        https://matrix.to/#/#b:custom.org
        https://matrix.to/#/#c:custom.org
        https://matrix.to/#/#d:custom.org
        ![Matrix](https://img.shields.io/matrix/room:matrix.org)
        Join us on Matrix! Our Matrix room is the best.
        Bridged to Matrix via mautrix.
        Use app.element.io to connect.
        """
        score, signals, rooms = enrich.score_readme(readme)
        assert score <= 10

    def test_detects_discord(self):
        readme = 'Join our Discord server: https://discord.gg/abc'
        _, signals, _ = enrich.score_readme(readme)
        assert any('Discord' in s for s in signals)

    def test_detects_telegram(self):
        readme = 'Telegram: https://t.me/mygroup'
        _, signals, _ = enrich.score_readme(readme)
        assert any('Telegram' in s for s in signals)

    def test_detects_irc(self):
        readme = '#project on irc.libera.chat'
        _, signals, _ = enrich.score_readme(readme)
        assert any('IRC' in s for s in signals)

    def test_user_link_detection(self):
        readme = '[![chat](https://img.shields.io/badge/chat-via%20Matrix-000)](https://matrix.to/#/@user:matrix.org)'
        score, signals, rooms = enrich.score_readme(readme)
        # User links should be detected too
        assert any('user' in s.lower() for s in signals) or any('badge' in s.lower() for s in signals)


class TestValidateRoom:
    """Test room ID validation."""

    def test_valid_room(self):
        assert enrich.validate_room('#project:matrix.org') is True

    def test_valid_room_custom_server(self):
        assert enrich.validate_room('#dev:custom.server.org') is True

    def test_invalid_no_hash(self):
        assert enrich.validate_room('project:matrix.org') is False

    def test_invalid_no_server(self):
        assert enrich.validate_room('#project') is False

    def test_invalid_no_tld(self):
        assert enrich.validate_room('#project:localhost') is False

    def test_valid_with_dots(self):
        assert enrich.validate_room('#my.room:matrix.org') is True

    def test_valid_with_dashes(self):
        assert enrich.validate_room('#my-room:matrix.org') is True

    def test_rejects_garbage(self):
        assert enrich.validate_room('#synapse-dev:matrix.org>`_,') is False


class TestFrontmatterRoundtrip:
    """Test parse → write → parse roundtrip."""

    def test_simple_roundtrip(self):
        original = '---\nname: "Test"\ndescription: "A test project"\nplatform: github\ncategories: [Dev, Infra]\nexodus_score: 7\nverified: true\n---\n\nBody text here.\n'
        fm, body = enrich.parse_frontmatter(original)
        output = enrich.write_frontmatter(fm, body)
        fm2, body2 = enrich.parse_frontmatter(output)
        assert fm2['name'] == fm['name']
        assert fm2['exodus_score'] == fm['exodus_score']
        assert fm2['verified'] == fm['verified']
        assert body2 == body

    def test_list_roundtrip(self):
        original = '---\nname: "Test"\nmatrix_rooms:\n  - "https://matrix.to/#/#a:m.org"\n  - "https://matrix.to/#/#b:m.org"\n---\n'
        fm, body = enrich.parse_frontmatter(original)
        output = enrich.write_frontmatter(fm, body)
        fm2, _ = enrich.parse_frontmatter(output)
        assert fm2['matrix_rooms'] == fm['matrix_rooms']

    def test_special_chars_in_values(self):
        original = '---\nname: "Test: with colon"\nrepo: "https://github.com/org/repo"\n---\n'
        fm, body = enrich.parse_frontmatter(original)
        output = enrich.write_frontmatter(fm, body)
        fm2, _ = enrich.parse_frontmatter(output)
        assert fm2['name'] == 'Test: with colon'
        assert fm2['repo'] == 'https://github.com/org/repo'


class TestRepoSlug:
    """Test GitHub slug extraction."""

    def test_https_url(self):
        assert enrich.repo_slug('https://github.com/org/repo') == 'org/repo'

    def test_https_with_git_suffix(self):
        assert enrich.repo_slug('https://github.com/org/repo.git') == 'org/repo'

    def test_ssh_url(self):
        assert enrich.repo_slug('git@github.com:org/repo.git') == 'org/repo'

    def test_trailing_slash(self):
        assert enrich.repo_slug('https://github.com/org/repo/') == 'org/repo'

    def test_non_github(self):
        assert enrich.repo_slug('https://gitlab.com/org/repo') is None

    def test_no_url(self):
        assert enrich.repo_slug('') is None

    def test_removesuffix_not_rstrip(self):
        """Regression: rstrip('.git') strips chars, removesuffix strips substring."""
        assert enrich.repo_slug('https://github.com/activist-org/activist') == 'activist-org/activist'
        assert enrich.repo_slug('https://github.com/org/digit') == 'org/digit'
