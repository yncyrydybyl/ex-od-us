# Exodus — Helping Projects Move to Matrix

**A project by [datanauten.de](https://datanauten.de)**

## Why

Most open-source projects run their community communication on platforms they don't control — Discord, Slack, Telegram, WhatsApp. These platforms are convenient, but they come with real costs:

- **No data ownership.** Your community's history, knowledge, and relationships live on someone else's servers under someone else's terms of service.
- **Vendor lock-in.** Moving away gets harder the longer you stay. Members resist switching. History is lost or hard to export.
- **Centralization risk.** A policy change, an acquisition, or a shutdown can scatter your community overnight.
- **No federation.** Your community is an island. You can't connect rooms across organizations or let people use their own server.
- **Surveillance and ads.** Most proprietary platforms monetize user data. Some scan messages. None give you the choice to opt out.

[Matrix](https://matrix.org) is the open, federated alternative. It gives communities:

- **Ownership.** Run your own homeserver, or use a trusted one. Your data stays where you put it.
- **Federation.** Connect rooms across homeservers. Collaborate across organizations without everyone joining the same silo.
- **End-to-end encryption.** Real privacy, not a marketing checkbox.
- **Bridges.** Transition gradually — bridge to Discord, Telegram, Slack, IRC while your community moves over.
- **Longevity.** An open protocol can't be acquired, shut down, or enshittified.

## What Exodus Does

Exodus tracks open-source projects and their communication infrastructure. For each project, we answer:

- Where is the community today? (Discord? Telegram? Matrix? All of them?)
- How far along is the move to Matrix?
- What's working? What's blocking?

Every project gets an **Exodus Score (0–10)** measuring how present it is on Matrix:

| Score | Meaning |
|---|---|
| 0 | No Matrix presence |
| 1–2 | Matrix room exists but is dead or unofficial |
| 3–4 | Active on Matrix but it's secondary |
| 5–6 | Matrix is co-primary with another platform |
| 7–8 | Matrix is the primary platform |
| 9–10 | Fully Matrix-native, own homeserver, strong federation |

The score is based on concrete signals: matrix.to links in the README, Matrix badges, custom homeservers, number of rooms, bridge status, matrixrooms.info listing, and where Matrix appears relative to other platforms.

## How It Works

The architecture is deliberately minimal:

1. **GitHub Issues are the database.** Each project is an issue with structured fields (filled via an issue form with dropdowns).
2. **GitHub Labels are the schema.** Categories and metadata are labels — no parsing needed.
3. **A single HTML file is the website.** `docs/index.html` fetches issues from the GitHub API and renders them as cards. Zero dependencies. Zero build step.
4. **A scanner runs every 6 hours.** It fetches tracked projects' READMEs, scores their Matrix presence, and comments on the issue with findings.

No backend. No database. No framework. One HTML file, two shell scripts, one GitHub Action.

## How to Help

### Add a project

Know a project that should be tracked? [Open an issue](https://github.com/yncyrydybyl/ex-od-us/issues/new/choose) and fill in the form. You'll rate its current Matrix presence and list its communication channels.

### Improve a score

The best way to improve a project's Exodus Score is to actually help them move:

- **Set up a Matrix room** for a project that doesn't have one
- **Add a Matrix badge** to their README
- **Set up a bridge** so existing Discord/Telegram users can participate via Matrix
- **Document the migration** so others can follow
- **Run a homeserver** for a project that's outgrowing matrix.org

See the [How-To guides](https://github.com/yncyrydybyl/ex-od-us/issues/26) for step-by-step instructions.

### Update outdated info

If a project's score or channel list is wrong, comment on its issue or edit it directly.

## How-To Guides

We're building practical guides for the common steps in a Matrix migration:

- Create a project room and Space
- Set up a project homeserver
- Get moderation tools in place (Mjolnir, Draupnir)
- Get listed on matrix.org and matrixrooms.info
- Set up or use bridges (Discord, Telegram, Slack, IRC)
- Improve developer and user experience with bots and widgets

These are tracked in [issue #26](https://github.com/yncyrydybyl/ex-od-us/issues/26).

## The Scanner

`scripts/scan-readmes.sh` automatically evaluates tracked projects by reading their GitHub READMEs. It checks for:

- matrix.to room links (and how many)
- Matrix badges (shields.io, official)
- Custom homeservers (not just matrix.org)
- Whether Matrix is listed before other platforms
- Bridge mentions
- Element client references
- Listing on matrixrooms.info

Results are posted as comments on each project's issue, with a score bar and list of detected signals.

## Finding New Projects

`find-matrix-repos.sh` searches GitHub for repos with Matrix presence in their READMEs, sorted by popularity:

```bash
# Top 50 most-starred repos with Matrix rooms
./find-matrix-repos.sh --limit 50 --sort stars --format table

# Active Rust projects
./find-matrix-repos.sh --language Rust --min-stars 100 --sort activity
```

## Live Site

**https://yncyrydybyl.github.io/ex-od-us/**

Cards are colored by platform (GitHub, GitLab, Codeberg). Click any card for full details including all communication channels, Matrix rooms, and scanner reports.

## Technical Details

| Component | What |
|---|---|
| Website | Single HTML file, ~400 lines, zero dependencies |
| Data | GitHub Issues via REST API |
| Hosting | GitHub Pages from `/docs` |
| Scanner | Bash + jq + GitHub API, runs via GitHub Actions every 6h |
| Finder | `gh search code` + `gh api` for repo metadata |
| Rate limits | 60 req/hr unauthenticated (1 call per page load) |

### Scaling path

If traffic grows beyond the unauthenticated API limit:

1. **Static JSON cache** — a GitHub Action fetches issues to `data/projects.json` on every issue change. Zero API calls per visitor.
2. **Authenticated requests** — 5,000 req/hr with a token.
3. **Conditional requests** — ETags avoid counting unchanged responses.

## File Structure

```
ex-od-us/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── project.yml          # Issue form with Exodus Score
│   │   └── config.yml           # Template chooser
│   └── workflows/
│       └── scan-readmes.yml     # Scheduled README scanner
├── docs/
│   └── index.html               # The entire website
├── scripts/
│   ├── scan-readmes.sh          # README scanner + Matrix scorer
│   └── notify-changes.sh        # Posts scan results as issue comments
├── data/
│   └── readme-cache.json        # Scanner SHA/score cache
├── find-matrix-repos.sh         # Search for repos with Matrix presence
└── README.md
```

---

*Exodus is about giving communities a choice. Not everyone needs to leave Discord today. But everyone deserves to know that a federated, self-hosted, encrypted alternative exists — and that moving is possible.*
