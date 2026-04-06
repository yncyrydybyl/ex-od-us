#!/usr/bin/env python3
"""End-to-end tests: full pipeline from project files to JSON to site."""
import json, os, subprocess, tempfile, shutil
import pytest

ROOT = os.path.join(os.path.dirname(__file__), '..')
SCRIPTS = os.path.join(ROOT, 'scripts')


class TestFullPipeline:
    """E2E: create project file → build JSON → verify output."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmpdir, 'projects'))
        os.makedirs(os.path.join(self.tmpdir, 'data'))
        shutil.copy(os.path.join(SCRIPTS, 'build-projects.sh'), self.tmpdir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def _write_project(self, slug, content):
        with open(os.path.join(self.tmpdir, 'projects', f'{slug}.md'), 'w') as f:
            f.write(content)

    def _build(self):
        result = subprocess.run(
            ['bash', 'build-projects.sh'],
            capture_output=True, text=True, cwd=self.tmpdir
        )
        assert result.returncode == 0, f"Build failed: {result.stderr}"
        with open(os.path.join(self.tmpdir, 'data', 'projects.json')) as f:
            return json.load(f)

    def test_single_project(self):
        self._write_project('test-project', """---
name: "Test Project"
description: "A test"
repo: "https://github.com/test/project"
platform: github
categories: [Development]
exodus_score: 5
status: "Active"
issues: [1]
updated: "2026-01-01T00:00:00Z"
---

A test project.
""")
        data = self._build()
        assert data['count'] == 1
        p = data['projects'][0]
        assert p['name'] == 'Test Project'
        assert p['slug'] == 'test-project'
        assert p['exodus_score'] == 5
        assert p['platform'] == 'github'
        assert p['issues'] == [1]

    def test_multiple_projects_sorted_by_score(self):
        self._write_project('low', '---\nname: "Low"\nexodus_score: 2\n---\n')
        self._write_project('high', '---\nname: "High"\nexodus_score: 9\n---\n')
        self._write_project('mid', '---\nname: "Mid"\nexodus_score: 5\n---\n')
        data = self._build()
        scores = [p['exodus_score'] for p in data['projects']]
        assert scores == [9, 5, 2]

    def test_null_scores_sorted_last(self):
        self._write_project('scored', '---\nname: "Scored"\nexodus_score: 3\n---\n')
        self._write_project('unscored', '---\nname: "Unscored"\n---\n')
        data = self._build()
        assert data['projects'][0]['name'] == 'Scored'
        assert data['projects'][1]['name'] == 'Unscored'

    def test_channels_parsed(self):
        self._write_project('channels', """---
name: "Channels Test"
discord: "https://discord.gg/test"
telegram: "https://t.me/test"
matrix_rooms:
  - "https://matrix.to/#/#room:matrix.org"
---
""")
        data = self._build()
        ch = data['projects'][0]['channels']
        assert ch['discord'] == 'https://discord.gg/test'
        assert ch['telegram'] == 'https://t.me/test'
        assert len(ch['matrix_rooms']) == 1

    def test_verified_fields(self):
        self._write_project('verified', '---\nname: "V"\nverified: true\nverified_note: "repo alive"\n---\n')
        data = self._build()
        p = data['projects'][0]
        assert p['verified'] is True
        assert p['verified_note'] == 'repo alive'

    def test_no_deprecation_warning(self):
        self._write_project('test', '---\nname: "T"\n---\n')
        result = subprocess.run(
            ['bash', 'build-projects.sh'],
            capture_output=True, text=True, cwd=self.tmpdir
        )
        assert 'DeprecationWarning' not in result.stderr

    def test_platform_autodetect(self):
        self._write_project('gh', '---\nname: "GH"\nplatform: none\nrepo: "https://github.com/a/b"\n---\n')
        self._write_project('gl', '---\nname: "GL"\nplatform: none\nrepo: "https://gitlab.com/a/b"\n---\n')
        self._write_project('cb', '---\nname: "CB"\nplatform: none\nrepo: "https://codeberg.org/a/b"\n---\n')
        data = self._build()
        platforms = {p['name']: p['platform'] for p in data['projects']}
        assert platforms['GH'] == 'github'
        assert platforms['GL'] == 'gitlab'
        assert platforms['CB'] == 'codeberg'


class TestSiteDataIntegrity:
    """E2E: verify the live projects.json is valid and consistent."""

    @pytest.fixture(autouse=True)
    def load_data(self):
        path = os.path.join(ROOT, 'data', 'projects.json')
        if not os.path.exists(path):
            pytest.skip('data/projects.json not built yet')
        with open(path) as f:
            self.data = json.load(f)

    def test_valid_json_structure(self):
        assert 'generated' in self.data
        assert 'count' in self.data
        assert 'projects' in self.data
        assert isinstance(self.data['projects'], list)

    def test_count_matches(self):
        assert self.data['count'] == len(self.data['projects'])

    def test_all_have_required_fields(self):
        required = ['slug', 'name', 'platform', 'categories', 'issues']
        for p in self.data['projects']:
            for field in required:
                assert field in p, f"Project {p.get('slug', '?')} missing {field}"

    def test_no_empty_names(self):
        for p in self.data['projects']:
            assert p['name'].strip(), f"Project {p['slug']} has empty name"

    def test_no_duplicate_slugs(self):
        slugs = [p['slug'] for p in self.data['projects']]
        dupes = [s for s in slugs if slugs.count(s) > 1]
        assert not dupes, f"Duplicate slugs: {set(dupes)}"

    def test_valid_platforms(self):
        valid = {'github', 'gitlab', 'codeberg', 'other', 'none'}
        for p in self.data['projects']:
            assert p['platform'] in valid, f"{p['slug']} has invalid platform: {p['platform']}"

    def test_scores_in_range(self):
        for p in self.data['projects']:
            if p['exodus_score'] is not None:
                assert 0 <= p['exodus_score'] <= 10, f"{p['slug']} score out of range: {p['exodus_score']}"

    def test_issues_are_ints(self):
        for p in self.data['projects']:
            for i in p['issues']:
                assert isinstance(i, int), f"{p['slug']} has non-int issue: {i}"

    def test_no_duplicate_repos(self):
        """No two projects should point to the same repo URL."""
        repos = {}
        for p in self.data['projects']:
            repo = p.get('repo', '').strip().rstrip('/').lower()
            if not repo:
                continue
            assert repo not in repos, f"Duplicate repo {repo}: {repos[repo]} and {p['slug']}"
            repos[repo] = p['slug']


class TestSiteHTML:
    """E2E: verify the static site HTML is valid."""

    @pytest.fixture(autouse=True)
    def load_html(self):
        path = os.path.join(ROOT, 'src', 'index.html')
        with open(path) as f:
            self.html = f.read()

    def test_has_title(self):
        assert '<title>Exodus Project Tracker</title>' in self.html

    def test_loads_projects_json(self):
        assert 'projects-slim.json' in self.html

    def test_has_hero_animation(self):
        assert 'hero-slot' in self.html
        assert 'heroFadeIn' in self.html

    def test_has_exodus_bar(self):
        assert 'exodus-bar' in self.html
        assert 'exodus-bar-fill' in self.html

    def test_has_matrix_badge(self):
        assert 'card-matrix-badge' in self.html
        assert 'enter room' in self.html

    def test_has_modal(self):
        assert 'modal-overlay' in self.html
        assert 'openModal' in self.html

    def test_uses_css_variables(self):
        assert '--bg:' in self.html
        assert '--surface:' in self.html
        assert '--green:' in self.html
        assert '--blue:' in self.html

    def test_loads_fonts(self):
        assert 'fonts.googleapis.com' in self.html
        assert 'Inter' in self.html
        assert 'JetBrains+Mono' in self.html

    def test_has_datanauten_branding(self):
        assert 'datanauten.de' in self.html

    def test_no_hardcoded_github_colors(self):
        """Brand colors should replace GitHub defaults."""
        # These are GitHub's defaults that should NOT appear
        assert 'color: #58a6ff' not in self.html  # should be var(--blue)
        assert 'background: #161b22' not in self.html  # should be var(--surface)
        assert 'color: #c9d1d9' not in self.html  # should be var(--text-muted)
