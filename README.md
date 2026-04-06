# Exodus — Helping Projects Move to Matrix

**https://yncyrydybyl.github.io/ex-od-us/**

Exodus tracks open-source projects and their communication channels. For each project, we measure how far along they are in adopting [Matrix](https://matrix.org) as their community platform.

**A project by [datanauten.de](https://datanauten.de)**

## Want your project tracked?

[Open an issue](https://github.com/yncyrydybyl/ex-od-us/issues/new/choose) and fill in the form. We'll scan your README, score your Matrix presence, and add you to the tracker.

Or just make sure your README has a `matrix.to` link — our scanner will find you automatically.

## What's the Exodus Score?

A 0-10 rating of how present a project is on Matrix:

| Score | What it means |
|---|---|
| **0** | No Matrix presence |
| **1-2** | Matrix room exists but quiet or unofficial |
| **3-4** | Active on Matrix, but it's secondary to Discord/Telegram/Slack |
| **5-6** | Matrix is co-primary with another platform |
| **7-8** | Matrix is the primary platform |
| **9-10** | Fully Matrix-native, own homeserver, strong federation |

The score is calculated automatically from your README: matrix.to links, badges, custom homeservers, bridge mentions, and more.

## How to improve your score

1. **Add a Matrix room** and link it in your README
2. **Add a Matrix badge** — use [shields.io/matrix](https://shields.io/badges/matrix)
3. **List Matrix first** when mentioning community channels
4. **Set up bridges** so Discord/Telegram users can participate via Matrix
5. **Run your own homeserver** (like [chat.opensuse.org](https://chat.opensuse.org))
6. **Get listed** on [matrixrooms.info](https://matrixrooms.info)

## For developers

See [docs/DEVELOP.md](docs/DEVELOP.md) for the full development guide: architecture, scripts, how to add projects, how enrichment works, how to run tests.

## Quick links

- **Live site**: https://yncyrydybyl.github.io/ex-od-us/
- **Add a project**: [Open an issue](https://github.com/yncyrydybyl/ex-od-us/issues/new/choose)
- **Report a bug**: [Issues](https://github.com/yncyrydybyl/ex-od-us/issues)
- **How-to guides**: [Issue #26](https://github.com/yncyrydybyl/ex-od-us/issues/26)

## Stats

- 2,200+ open-source projects tracked
- Scores updated every 6 hours via automated scanning
- Data sourced from Sourcegraph + GitHub API
- Zero-dependency static site (one HTML file, no framework)

## Why Matrix?

Most open-source projects run their community on platforms they don't control — Discord, Slack, Telegram. These are convenient but come with costs: no data ownership, vendor lock-in, no federation, surveillance.

Matrix gives communities ownership, federation, end-to-end encryption, and longevity. An open protocol can't be acquired, shut down, or enshittified.

Exodus exists to make that migration visible and to help projects take the first step.
