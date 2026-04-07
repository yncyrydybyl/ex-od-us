#!/usr/bin/env python3
"""
exclude.py — Atomic "this isn't actually a Matrix project" operation.

Single-command flow that:
  1. Appends an entry to data/excluded-repos.txt with a reason.
  2. Deletes projects/<slug>.md if it exists.
  3. Closes the matching GitHub issue (if any) with an explanation comment,
     adds the `excluded` label, removes `project` label, closes "not planned".

Idempotent: if the entry is already in the list, the file is already gone,
or the issue is already closed, those steps are skipped silently.

Usage:
  python3 scripts/exclude.py <repo-url-or-slug> "<reason>"
  python3 scripts/exclude.py jfsiii/XCSSMatrix "CSS matrix transform polyfill"
  python3 scripts/exclude.py --dry-run jfsiii/XCSSMatrix "..."
  python3 scripts/exclude.py --no-issue jfsiii/XCSSMatrix "..."   # skip GH

Requires: gh CLI authenticated against the repo (unless --no-issue).
"""
import os, sys, re, json, subprocess, argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from exclusions import load_excluded_repos, is_excluded, _normalize

REPO = os.environ.get('GITHUB_REPOSITORY', 'yncyrydybyl/ex-od-us')
PROJECTS_DIR = Path('projects')
EXCLUDED_FILE = Path('data/excluded-repos.txt')


def gh(*args, check=False):
    result = subprocess.run(['gh'] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip()
        if check:
            raise RuntimeError(f"gh {' '.join(args)} failed: {msg}")
        print(f"  gh error: {msg}", file=sys.stderr)
        return None
    return result.stdout.strip()


def find_project_file(repo_norm: str) -> Path | None:
    """Find the .md file whose `repo:` matches the normalized form."""
    for fpath in PROJECTS_DIR.glob('*.md'):
        content = fpath.read_text()
        m = re.search(r'^repo:\s*"?([^"\n]+)', content, re.MULTILINE)
        if not m:
            continue
        if _normalize(m.group(1).strip()) == repo_norm:
            return fpath
    return None


def project_name_from_file(fpath: Path) -> str | None:
    content = fpath.read_text()
    m = re.search(r'^name:\s*"?([^"\n]+?)"?\s*$', content, re.MULTILINE)
    return m.group(1).strip() if m else fpath.stem


def project_issue_from_file(fpath: Path) -> int | None:
    content = fpath.read_text()
    m = re.search(r'^issues:\s*\[\s*(\d+)', content, re.MULTILINE)
    return int(m.group(1)) if m else None


def append_to_exclusion_list(repo_norm: str, reason: str, dry: bool) -> bool:
    """Append entry to data/excluded-repos.txt. Returns True if appended."""
    existing = load_excluded_repos(EXCLUDED_FILE)
    if repo_norm in existing:
        print(f"  already in {EXCLUDED_FILE}, skipping", file=sys.stderr)
        return False
    line = f"{repo_norm}    # {reason}\n"
    if dry:
        print(f"  [dry] would append: {line.rstrip()}")
    else:
        with open(EXCLUDED_FILE, 'a') as f:
            f.write(line)
        print(f"  appended: {line.rstrip()}")
    return True


def delete_project_file(fpath: Path | None, dry: bool) -> bool:
    if fpath is None:
        print("  no project file found, skipping delete", file=sys.stderr)
        return False
    if dry:
        print(f"  [dry] would delete: {fpath}")
    else:
        fpath.unlink()
        print(f"  deleted: {fpath}")
    return True


def ensure_excluded_label(dry: bool):
    if dry:
        print("  [dry] would ensure `excluded` label exists")
        return
    gh('label', 'create', 'excluded',
       '--repo', REPO,
       '--color', '6e7681',
       '--description', 'Not actually a Matrix-protocol project',
       '--force')


def close_issue(issue_num: int, repo_norm: str, reason: str, dry: bool) -> bool:
    """Comment, label, then close the issue. Returns True if closed."""
    if dry:
        print(f"  [dry] would label/comment/close #{issue_num}")
        return True
    body = (f"Closing as not a Matrix-protocol project.\n\n"
            f"**Reason:** {reason}\n\n"
            f"Recorded in `data/excluded-repos.txt` so future discovery "
            f"runs will not re-create this entry. To reverse, remove the "
            f"line from that file.")
    ensure_excluded_label(dry=False)
    gh('issue', 'comment', str(issue_num), '--repo', REPO, '--body', body)
    gh('issue', 'edit', str(issue_num), '--repo', REPO,
       '--add-label', 'excluded', '--remove-label', 'project')
    gh('issue', 'close', str(issue_num), '--repo', REPO, '--reason', 'not planned')
    print(f"  closed #{issue_num} (excluded label, project label removed)")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('repo', help='Repo URL or slug (e.g. jfsiii/XCSSMatrix)')
    ap.add_argument('reason', help='Why this is being excluded (one line)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-issue', action='store_true', help='Skip GH issue mutation')
    args = ap.parse_args()

    repo_norm = _normalize(args.repo)
    if not repo_norm:
        sys.exit(f"Could not parse repo: {args.repo!r}")

    print(f"Excluding {repo_norm}")
    print(f"Reason: {args.reason}")
    print()

    # 1. Append to list
    print("1. Exclusion list")
    append_to_exclusion_list(repo_norm, args.reason, args.dry_run)

    # 2. Find and delete project file
    print()
    print("2. Project file")
    fpath = find_project_file(repo_norm)
    issue_num = project_issue_from_file(fpath) if fpath else None
    delete_project_file(fpath, args.dry_run)

    # 3. Close issue
    print()
    print("3. GitHub issue")
    if args.no_issue:
        print("  --no-issue, skipping")
    elif issue_num is None:
        print("  no issue number recorded in project file, skipping")
    else:
        close_issue(issue_num, repo_norm, args.reason, args.dry_run)

    print()
    if args.dry_run:
        print("Dry run complete. Re-run without --dry-run to apply.")
    else:
        print("Done. Commit data/excluded-repos.txt and the deleted .md.")


if __name__ == '__main__':
    main()
