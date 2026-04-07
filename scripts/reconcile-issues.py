#!/usr/bin/env python3
"""
reconcile-issues.py — One-shot cleanup for duplicate project issues.

Why this exists
---------------
`sync-issues.py` used to create one GitHub issue per project. Historically,
if the script crashed or its containing workflow step failed before the
follow-up commit step ran, the newly created GH issues were orphaned: the
project file still said `issues: []`, so the next scheduled run created
them all over again. Roughly 300+ duplicate `[Project]:` issues piled up
this way.

What this does
--------------
1. Fetch every `[Project]:`-titled, `project`-labeled issue on GitHub.
2. Group by exact title.
3. For each project file with `issues: []`, look up its title and write
   the *lowest-numbered* matching issue into the frontmatter (canonical).
4. For every other issue with the same title, close it with a comment
   linking the canonical issue.

Defaults to dry-run. Pass `--apply` to actually mutate.

Usage:
  python3 scripts/reconcile-issues.py            # dry run, report only
  python3 scripts/reconcile-issues.py --apply    # write files + close dupes
  python3 scripts/reconcile-issues.py --apply --only-files   # files only
  python3 scripts/reconcile-issues.py --apply --only-close   # close only

Requires: gh CLI authenticated against the repo.
"""
import os, re, sys, json, time, subprocess, argparse
from pathlib import Path

REPO = os.environ.get('GITHUB_REPOSITORY', 'yncyrydybyl/ex-od-us')
PROJECTS_DIR = Path('projects')

# Minimum spacing between *mutating* gh calls. GitHub's anti-abuse limit
# on addComment fires at well under one comment per second across thousands
# of issues; the practical safe rate is roughly one mutation every 2-3s.
# Tweak via env if you're feeling brave.
MIN_MUTATION_DELAY_S = float(os.environ.get('GH_MUTATION_DELAY', '2.5'))

# When the abuse-detection rate limit fires, we back off exponentially.
# Sequence: 30, 60, 120, 240, 480 seconds, then give up.
BACKOFF_STEPS_S = (30, 60, 120, 240, 480)

_last_mutation_time = 0.0


def _is_secondary_rate_limit(stderr_msg: str) -> bool:
    """Detect GitHub secondary (anti-abuse) rate-limit errors. These are
    distinct from the primary 5000/hr limit and can fire on as little as
    a few requests/second to mutating endpoints."""
    msg = stderr_msg.lower()
    return any(s in msg for s in (
        'submitted too quickly',
        'secondary rate limit',
        'abuse detection',
        'you have exceeded a secondary rate limit',
    ))


def gh(*args, check=False, mutating=False):
    """Run a gh command. If `mutating=True`, throttle and auto-retry on
    secondary rate-limit errors with exponential backoff."""
    global _last_mutation_time

    if mutating:
        # Throttle: keep mutation calls at least MIN_MUTATION_DELAY_S apart.
        now = time.monotonic()
        wait = MIN_MUTATION_DELAY_S - (now - _last_mutation_time)
        if wait > 0:
            time.sleep(wait)

        for attempt, backoff in enumerate((0,) + BACKOFF_STEPS_S):
            if backoff:
                print(f"  rate-limited; sleeping {backoff}s before retry {attempt}",
                      file=sys.stderr)
                time.sleep(backoff)
            result = subprocess.run(['gh'] + list(args), capture_output=True, text=True)
            _last_mutation_time = time.monotonic()
            if result.returncode == 0:
                return result.stdout.strip()
            stderr = result.stderr.strip()
            if not _is_secondary_rate_limit(stderr):
                # Not a rate-limit error — fail like the non-mutating path.
                if check:
                    raise RuntimeError(f"gh {' '.join(args)} failed: {stderr}")
                print(f"  gh error: {stderr}", file=sys.stderr)
                return None
        # All backoffs exhausted.
        msg = f"gh {' '.join(args)} still rate-limited after {len(BACKOFF_STEPS_S)} retries"
        if check:
            raise RuntimeError(msg)
        print(f"  gh error: {msg}", file=sys.stderr)
        return None

    # Non-mutating path: simple call, no throttle.
    result = subprocess.run(['gh'] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        msg = result.stderr.strip()
        if check:
            raise RuntimeError(f"gh {' '.join(args)} failed: {msg}")
        print(f"  gh error: {msg}", file=sys.stderr)
        return None
    return result.stdout.strip()


def load_all_project_issues():
    """Return list of {number, title, state} for every `project`-labeled issue.

    Uses `gh api --paginate` because `gh issue list` silently caps at 1000
    items regardless of `--limit`. The repo has ~7k project issues today.
    """
    raw = gh('api', '--paginate',
             f'/repos/{REPO}/issues?state=all&labels=project&per_page=100',
             check=True)
    if not raw:
        return []
    # --paginate concatenates JSON arrays back-to-back as `][`. Normalize.
    raw = raw.replace('][', ',')
    items = json.loads(raw)
    out = []
    for it in items:
        # Skip pull requests — the issues API returns them too.
        if 'pull_request' in it:
            continue
        out.append({
            'number': it['number'],
            'title': it['title'],
            'state': it['state'],
        })
    return out


def read_project_name(fpath: Path) -> str | None:
    """Extract the `name:` value from a project frontmatter, falling back to slug."""
    content = fpath.read_text()
    m = re.search(r'^name:\s*"?([^"\n]+?)"?\s*$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fpath.stem


def project_has_empty_issues(fpath: Path) -> bool:
    content = fpath.read_text()
    return bool(re.search(r'^issues:\s*\[\s*\]\s*$', content, re.MULTILINE))


def write_issue_number(fpath: Path, issue_num: int) -> bool:
    content = fpath.read_text()
    new = re.sub(r'^issues:\s*\[\s*\]\s*$',
                 f'issues: [{issue_num}]',
                 content, count=1, flags=re.MULTILINE)
    if new == content:
        return False
    fpath.write_text(new)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='Actually mutate files and close GH issues. Default is dry-run.')
    ap.add_argument('--only-files', action='store_true',
                    help='Only fix project file issues fields; leave GH issues alone.')
    ap.add_argument('--only-close', action='store_true',
                    help='Only close duplicate GH issues; leave project files alone.')
    ap.add_argument('--no-comment', action='store_true',
                    help='Skip the cross-reference comment when closing duplicates. '
                         'Roughly halves API call volume and avoids the addComment '
                         'rate limit. Use this for large bulk runs; the canonical '
                         'issue number is still set as the close-as-duplicate target.')
    args = ap.parse_args()

    if args.only_files and args.only_close:
        sys.exit("--only-files and --only-close are mutually exclusive")

    dry = not args.apply
    prefix = '[DRY-RUN] ' if dry else ''

    print(f"{prefix}Loading all project-labeled issues from {REPO}...")
    issues = load_all_project_issues()
    print(f"{prefix}Fetched {len(issues)} issues.")

    # Group by title. For each title, the canonical number is the lowest.
    by_title: dict[str, list[dict]] = {}
    for it in issues:
        by_title.setdefault(it['title'], []).append(it)
    for title in by_title:
        by_title[title].sort(key=lambda x: int(x['number']))

    dup_titles = {t: lst for t, lst in by_title.items() if len(lst) > 1}
    print(f"{prefix}Titles with duplicates: {len(dup_titles)}")
    print(f"{prefix}Total surplus issues to close: {sum(len(v) - 1 for v in dup_titles.values())}")

    # Index project files by expected title.
    file_by_title: dict[str, Path] = {}
    for fpath in sorted(PROJECTS_DIR.glob('*.md')):
        name = read_project_name(fpath)
        if name:
            file_by_title[f'[Project]: {name}'] = fpath

    # --- Phase 1: write canonical issue numbers into project files -------
    files_updated = 0
    files_skipped_has_number = 0
    files_skipped_no_match = 0
    if not args.only_close:
        for title, lst in by_title.items():
            fpath = file_by_title.get(title)
            if not fpath:
                files_skipped_no_match += 1
                continue
            if not project_has_empty_issues(fpath):
                files_skipped_has_number += 1
                continue
            canonical = int(lst[0]['number'])
            if dry:
                print(f"  [dry] would set {fpath.name} issues: [{canonical}]")
                files_updated += 1
            else:
                if write_issue_number(fpath, canonical):
                    print(f"  WROTE {fpath.name} issues: [{canonical}]")
                    files_updated += 1

    # --- Phase 2: close duplicate issues on GitHub -----------------------
    dupes_closed = 0
    dupes_skipped_already_closed = 0
    dupes_failed = 0
    if not args.only_files:
        for title, lst in dup_titles.items():
            canonical = int(lst[0]['number'])
            for extra in lst[1:]:
                num = int(extra['number'])
                if extra['state'].lower() == 'closed':
                    dupes_skipped_already_closed += 1
                    continue
                comment = (f"Closing as duplicate of #{canonical}. "
                           f"This issue was created by a sync-workflow race "
                           f"(see fix in sync-issues.py). All future activity "
                           f"should happen on #{canonical}.")
                if dry:
                    suffix = ' (no comment)' if args.no_comment else ''
                    print(f"  [dry] would close #{num} (dup of #{canonical}){suffix} — {title}")
                    dupes_closed += 1
                else:
                    if not args.no_comment:
                        gh('issue', 'comment', str(num), '--repo', REPO,
                           '--body', comment, mutating=True)
                    closed = gh('issue', 'close', str(num), '--repo', REPO,
                                '--reason', 'not planned', mutating=True)
                    if closed is None:
                        dupes_failed += 1
                        print(f"  FAILED to close #{num} (dup of #{canonical})", file=sys.stderr)
                    else:
                        print(f"  CLOSED #{num} (dup of #{canonical})")
                        dupes_closed += 1

    print()
    print(f"{prefix}Summary:")
    print(f"  project files updated:       {files_updated}")
    print(f"  skipped (already has number):{files_skipped_has_number}")
    print(f"  skipped (no matching file):  {files_skipped_no_match}")
    print(f"  duplicates {'closed' if not dry else 'to close'}:        {dupes_closed}")
    print(f"  already closed, left alone:  {dupes_skipped_already_closed}")
    if dupes_failed:
        print(f"  failed (after retries):      {dupes_failed}")

    if dry:
        print()
        print("Re-run with --apply to actually make changes.")


if __name__ == '__main__':
    main()
