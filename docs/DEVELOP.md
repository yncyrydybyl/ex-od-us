# Development Guide

How Exodus works, how to contribute, and how all the pieces fit together.

## Architecture

```
projects/*.md          ← Source of truth: one file per project (YAML frontmatter)
  ↓
scripts/build-projects.sh  ← Parses all .md files → data/projects.json + projects-slim.json
  ↓
src/index.html          ← Single-file static site (loads projects-slim.json)
  ↓
GitHub Pages            ← deploy.yml builds JSON + copies src/index.html → _site/
```

### Data flow

1. **Discovery**: `find-matrix-repos.sh` searches Sourcegraph for repos with `matrix.to` in their README
2. **Import**: `scripts/import-from-finder.py` or `scripts/import-from-slugs.py` creates `projects/*.md` files
3. **Enrichment**: `scripts/enrich-via-sourcegraph.py` queries Sourcegraph for Matrix signals, then optionally fetches each repo's README via the persistent ETag-conditional cache (`scripts/readme_cache.py`) for deeper scoring
4. **Build**: `scripts/build-projects.sh` generates `data/projects.json` (full) and `data/projects-slim.json` (79% smaller, for the site)
5. **Deploy**: `.github/workflows/deploy.yml` builds JSON and deploys to GitHub Pages
6. **Issue sync**: `scripts/sync-issues.py` creates/updates GitHub issues from project files

## File structure

```
ex-od-us/
├── src/
│   └── index.html               # The entire website (single file)
├── projects/                    # One .md file per tracked project
│   ├── bspwm.md
│   ├── dendrite.md
│   └── ...                      # ~2200 project files
├── scripts/
│   ├── build-projects.sh           # .md files → projects.json
│   ├── enrich-via-sourcegraph.py   # Score Matrix presence via Sourcegraph + cached READMEs
│   ├── readme_cache.py             # Persistent ETag-conditional README cache
│   ├── reconcile-issues.py         # One-shot duplicate-issue cleanup
│   ├── exclusions.py / exclude.py  # Mark repos as not-Matrix-protocol
│   ├── import-from-finder.py       # Create .md from finder JSON output
│   ├── import-from-slugs.py        # Create .md from discovered-slugs.txt
│   ├── discover-codeberg.py        # Discover Matrix-related repos on Codeberg
│   ├── discover-via-topics.sh      # Discover via GitHub topic search
│   ├── sync-issues.py              # Create/update GitHub issues
│   ├── snapshot-scores.py          # Save score distribution snapshot
│   └── refresh-all.sh              # Run the full pipeline
├── data/
│   ├── discovered-slugs.txt        # All 2200+ repo slugs from Sourcegraph
│   ├── excluded-repos.txt          # Manually excluded repos (not Matrix protocol)
│   ├── readme-cache.json           # ETag/sha index for the README cache
│   ├── readmes/                    # Full README bytes (gitignored, restored in CI)
│   └── score-history.jsonl         # Score snapshots over time
├── tests/
│   ├── test_build_projects.py      # Frontmatter parser tests
│   └── test_e2e.py                 # Full pipeline + site integrity tests
├── docs/
│   └── DEVELOP.md               # This file
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── project.yml          # Issue form for adding projects
│   │   └── config.yml           # Template chooser config
│   └── workflows/
│       ├── deploy.yml           # Build JSON + deploy to Pages
│       ├── enrich-projects.yml  # Scheduled enrichment (every 6h)
│       └── sync-project-issues.yml  # Create issues for new projects
├── find-matrix-repos.sh         # Discover repos via Sourcegraph
├── DESIGN.md                    # Design system (colors, fonts, spacing)
└── README.md                    # User-facing README
```

## How to...

### Add a project manually

Create `projects/my-project.md`:

```yaml
---
name: "My Project"
description: "What this project does"
repo: "https://github.com/org/repo"
platform: github
categories: [Development]
status: "Active"
issues: []
updated: "2026-01-01T00:00:00Z"
---

Description goes here.
```

Then run:
```bash
bash scripts/build-projects.sh     # rebuild JSON
python3 scripts/sync-issues.py     # create GitHub issue
```

### Discover new projects

```bash
# Search Sourcegraph for repos with matrix.to in README
bash find-matrix-repos.sh --limit 200 --min-stars 10 --output /tmp/found.json

# Import as project files (skips existing)
python3 scripts/import-from-finder.py /tmp/found.json

# Or import from the saved slug list
python3 scripts/import-from-slugs.py --limit 100 --min-stars 5
```

### Enrich projects with live data

```bash
# Score all projects via Sourcegraph snippets (fast, no GitHub API)
python3 scripts/enrich-via-sourcegraph.py

# Also fetch full READMEs for deeper scoring (uses ETag cache)
python3 scripts/enrich-via-sourcegraph.py --full

# Score one specific project
python3 scripts/enrich-via-sourcegraph.py --full --project bspwm

# Dry run (shows what would change)
python3 scripts/enrich-via-sourcegraph.py --dry-run
```

### Run the full pipeline

```bash
bash scripts/refresh-all.sh              # normal pipeline
bash scripts/refresh-all.sh --full       # also do deep README scan
bash scripts/refresh-all.sh --dry-run    # preview only
```

This runs: enrich → build → sync issues. Auto-commits with a detailed log.

### Run tests

```bash
python3 -m pytest tests/ -v
```

76 tests covering: frontmatter parsing, Matrix scoring, room validation, slug extraction, build output, data integrity, HTML structure.

### Deploy

Deployment is automatic via GitHub Actions. On every push to `main` that touches `projects/`, `src/`, or `scripts/build-projects.sh`:

1. `deploy.yml` runs `build-projects.sh`
2. Copies `src/index.html` + `data/projects-slim.json` to `_site/`
3. Deploys to GitHub Pages

For local preview:
```bash
bash scripts/build-projects.sh
cd src && python3 -m http.server 8080
# Copy data/projects-slim.json to src/ for local testing
```

## Exodus Score (0-10)

The enricher scores Matrix presence by scanning the project's README:

| Signal | Points |
|---|---|
| matrix.to room links exist | +2 |
| Matrix badge (shields.io) | +1 |
| Matrix mentioned as channel | +1 |
| Custom homeserver (not matrix.org) | +2 |
| Multiple rooms (3+) | +1 |
| Matrix listed before Discord/Telegram | +1 |
| Bridge mentioned | +1 |
| Element client mentioned | +1 |
| Listed on matrixrooms.info | +1 |
| **Max** | **10** |

## Project file format

```yaml
---
name: "Project Name"              # required
description: "One-line summary"   # optional
repo: "https://github.com/o/r"   # GitHub/GitLab/Codeberg URL
platform: github                  # github|gitlab|codeberg|other|none
categories: [Dev, Security]       # free-form tags
exodus_score: 5                   # 0-10, set by enricher
status: "Active"                  # Active|Archived|Dead
matrix_rooms:                     # extracted by enricher
  - "https://matrix.to/#/#room:server.org"
discord: "https://discord.gg/..."
telegram: "https://t.me/..."
issues: [42]                      # linked GitHub issue numbers
verified: true                    # liveness check result
verified_note: "repo alive, room alive"
last_scanned: "2026-04-06T..."    # last enrichment timestamp
updated: "2026-04-06T..."         # last modified
---

Free-form body text (becomes notes in JSON).
```

## Design system

See [DESIGN.md](../DESIGN.md) for colors, fonts, spacing, and component specs. The site uses CSS custom properties derived from the brand SVG assets.

## Rate limits

- **Sourcegraph** (discovery): no auth needed, generous limits
- **GitHub API** (enrichment): 5000 req/hr authenticated via `gh`. Each project = 1 API call. Use `--skip-matrixrooms` to avoid matrixrooms.info checks.
- **GitHub Pages** (deploy): automatic, no limits
- **GitHub Issues** (sync): 1 API call per issue create/update
