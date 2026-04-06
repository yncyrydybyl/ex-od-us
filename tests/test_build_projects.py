#!/usr/bin/env python3
"""Tests for build-projects.sh (the embedded Python parser)."""
import json, os, subprocess, tempfile, shutil
import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'scripts')
PROJECTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'projects')


def run_build(projects_dir, output_file):
    """Run build-projects.sh with custom dirs."""
    # The build script is bash wrapping python — we extract and run the python directly
    env = os.environ.copy()
    result = subprocess.run(
        ['bash', os.path.join(SCRIPTS_DIR, 'build-projects.sh')],
        capture_output=True, text=True,
        cwd=os.path.dirname(projects_dir),
    )
    return result


class TestFrontmatterParser:
    """Test the YAML frontmatter parser used by build-projects.sh."""

    def _parse(self, content):
        """Parse frontmatter using the same logic as build-projects.sh."""
        # Import the parser from build script by running it on a temp dir
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, 'projects'))
            os.makedirs(os.path.join(tmpdir, 'data'))
            with open(os.path.join(tmpdir, 'projects', 'test.md'), 'w') as f:
                f.write(content)
            shutil.copy(os.path.join(SCRIPTS_DIR, 'build-projects.sh'), tmpdir)
            result = subprocess.run(
                ['bash', 'build-projects.sh'],
                capture_output=True, text=True, cwd=tmpdir
            )
            with open(os.path.join(tmpdir, 'data', 'projects.json')) as f:
                data = json.load(f)
            return data['projects'][0] if data['projects'] else None
        finally:
            shutil.rmtree(tmpdir)

    def test_basic_fields(self):
        p = self._parse('---\nname: "Test Project"\ndescription: "A test"\nplatform: github\n---\n')
        assert p['name'] == 'Test Project'
        assert p['description'] == 'A test'
        assert p['platform'] == 'github'

    def test_inline_list(self):
        p = self._parse('---\nname: "Test"\ncategories: [Dev, Infra, Security]\n---\n')
        assert p['categories'] == ['Dev', 'Infra', 'Security']

    def test_multiline_list(self):
        p = self._parse('---\nname: "Test"\nmatrix_rooms:\n  - "https://matrix.to/#/#room:server.org"\n  - "https://matrix.to/#/#dev:server.org"\n---\n')
        assert len(p['channels']['matrix_rooms']) == 2
        assert 'matrix.to/#/#room:server.org' in p['channels']['matrix_rooms'][0]

    def test_integer_field(self):
        p = self._parse('---\nname: "Test"\nexodus_score: 7\n---\n')
        assert p['exodus_score'] == 7

    def test_boolean_field(self):
        p = self._parse('---\nname: "Test"\nverified: true\n---\n')
        assert p['verified'] is True

    def test_null_field(self):
        p = self._parse('---\nname: "Test"\nexodus_score: null\n---\n')
        assert p['exodus_score'] is None

    def test_empty_list(self):
        p = self._parse('---\nname: "Test"\ncategories: []\n---\n')
        assert p['categories'] == []

    def test_body_becomes_notes(self):
        p = self._parse('---\nname: "Test"\n---\n\nThis is the body text.\n')
        assert 'body text' in p['notes']

    def test_quoted_values(self):
        p = self._parse('---\nname: "Test: with colon"\nrepo: "https://github.com/org/repo"\n---\n')
        assert p['name'] == 'Test: with colon'
        assert p['repo'] == 'https://github.com/org/repo'

    def test_platform_autodetect_github(self):
        p = self._parse('---\nname: "Test"\nplatform: none\nrepo: "https://github.com/org/repo"\n---\n')
        assert p['platform'] == 'github'

    def test_platform_autodetect_gitlab(self):
        p = self._parse('---\nname: "Test"\nplatform: none\nrepo: "https://gitlab.com/org/repo"\n---\n')
        assert p['platform'] == 'gitlab'

    def test_platform_autodetect_codeberg(self):
        p = self._parse('---\nname: "Test"\nplatform: none\nrepo: "https://codeberg.org/org/repo"\n---\n')
        assert p['platform'] == 'codeberg'

    def test_avatar_autodetect(self):
        p = self._parse('---\nname: "Test"\nrepo: "https://github.com/myorg/repo"\n---\n')
        assert 'myorg' in p['avatar_url']

    def test_issues_list(self):
        p = self._parse('---\nname: "Test"\nissues: [42]\n---\n')
        assert p['issues'] == [42]

    def test_issues_empty(self):
        p = self._parse('---\nname: "Test"\nissues: []\n---\n')
        assert p['issues'] == []


class TestBuildOutput:
    """Test the full build output."""

    def test_builds_real_projects(self):
        """Smoke test: build the actual projects directory."""
        result = subprocess.run(
            ['bash', os.path.join(SCRIPTS_DIR, 'build-projects.sh')],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), '..')
        )
        assert result.returncode == 0
        assert 'DeprecationWarning' not in result.stderr
        assert 'Built' in result.stderr

        with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'projects.json')) as f:
            data = json.load(f)
        assert data['count'] > 0
        assert len(data['projects']) == data['count']
        assert 'generated' in data

    def test_no_duplicate_slugs(self):
        """Every project should have a unique slug."""
        with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'projects.json')) as f:
            data = json.load(f)
        slugs = [p['slug'] for p in data['projects']]
        assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {[s for s in slugs if slugs.count(s) > 1]}"

    def test_all_projects_have_name(self):
        with open(os.path.join(os.path.dirname(__file__), '..', 'data', 'projects.json')) as f:
            data = json.load(f)
        for p in data['projects']:
            assert p['name'], f"Project {p['slug']} has no name"
