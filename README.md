# Exodus Project Tracker

A lightweight public project tracker powered by **GitHub Issues** and **GitHub Pages**.
No backend, no database, no build step. Issues are the CMS; labels are the schema; one HTML file is the entire website.

**Live site:** https://yncyrydybyl.github.io/ex-od-us/
**Add a project:** [Open an issue](https://github.com/yncyrydybyl/ex-od-us/issues/new/choose)

---

## Spike Goal

Validate whether GitHub Issues can serve as a structured content source for a public card-based website on GitHub Pages, using the absolute minimum custom code.

**Answer: Yes.** The working prototype is ~200 lines of JavaScript, zero dependencies, zero build steps.

---

## Prior Art Research

### GitHub Issues as CMS

Several projects use GitHub Issues as a content backend:

| Project / Pattern | What It Does | Reusable? |
|---|---|---|
| **github-issue-cms** pattern | Uses issue body + labels as blog content | Partially — blog-oriented, not card-oriented |
| **Gitment / Gitalk / utterances** | GitHub Issues for blog comments | No — comment-focused, not content-focused |
| **GitHub Projects (beta)** | Kanban/table views of issues | Partially — but not a public website |
| **Static blog generators** (e.g. gatsby-source-github) | Pull issue content at build time | Avoid — adds build step and complexity |
| **gh-pages + REST API** pattern | Client-side fetch of issues | **Yes — this is what we use** |

### Key Finding: Issue Forms

GitHub Issue Forms (YAML-based, not classic Markdown templates) produce **machine-readable issue bodies** with a stable format:

```
### Field Label

Selected Value

### Another Field

Another Value
```

This means dropdown selections (Category, Color, Status) appear as parseable `### Header` / value pairs. However, we chose **labels** over body parsing as the primary data source because:

1. Labels are returned as structured data in the API response — no parsing needed
2. Labels can be filtered server-side via API query parameters
3. Labels are visible in the GitHub UI for at-a-glance categorization
4. Body parsing is fragile if users edit the issue text

### What We Reuse

- **GitHub Issue Forms** — structured input with dropdowns, no custom form UI needed
- **GitHub Labels** — structured metadata, API-filterable, no parsing needed
- **GitHub REST API** — standard issue listing, paginated, well-documented
- **GitHub Pages** — zero-config static hosting from the `/docs` directory
- **CSS Grid** — native browser layout, no library needed
- **URLSearchParams** — native browser API for filter state in URL

### What We Avoid

- **Build steps** — no SSG, no bundler, no npm
- **Frameworks** — no React, Vue, Svelte
- **Body parsing for primary data** — labels are more reliable
- **Authentication** — unauthenticated API is sufficient for public repos
- **External dependencies** — zero JavaScript libraries
- **Backend services** — purely client-side
- **GraphQL** — REST is simpler for this use case

### Why This Is Sustainable

- **One file** to maintain (index.html)
- **Zero dependencies** to update
- **No build to break** — edit HTML, push, done
- **GitHub handles** hosting, auth, forms, labels, API, and rate limiting
- **Issue Forms** enforce data quality at input time

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐
│  User fills out      │────▶│  GitHub Issue created │
│  Issue Form          │     │  with labels          │
│  (dropdowns for      │     │  (project, Category,  │
│   category, color)   │     │   color:X)            │
└─────────────────────┘     └──────────┬───────────┘
                                       │
                                       ▼
┌─────────────────────┐     ┌──────────────────────┐
│  Static site on      │◀───│  GitHub REST API      │
│  GitHub Pages        │     │  GET /repos/:r/issues │
│  (docs/index.html)   │     │  ?labels=project      │
└─────────────────────┘     └──────────────────────┘
```

### Data Flow

1. User opens an issue using the form template
2. Form pre-applies the `project` label; user selects Category and Color from dropdowns
3. On form submission, we manually apply category and color labels (or they're set by the issue creator)
4. The static site fetches `GET /repos/{owner}/{repo}/issues?labels=project&state=open`
5. For each issue, labels are read to extract category and color
6. Issue body is parsed for supplemental fields (summary, description, links, Matrix room, status, notes)
7. Cards are rendered with color accent, category badge, and metadata

### Parsing Strategy

**Primary data source: Labels**

- Category: a label matching one of the 20 category names (e.g., `Governance`, `Development`)
- Color: a label in the format `color:red`, `color:blue`, etc.
- Entry type: the `project` label filters project issues from other issue types

**Secondary data source: Issue body**

The issue form produces a structured body with `### Header` sections. We parse this for:
- Project Name (used as card title, falls back to issue title)
- Short Summary
- Description
- External Links
- Matrix Room
- Status
- Notes

This is a best-effort parse — if someone edits the body and breaks the format, the card still renders using the issue title and labels.

---

## Issue Form Design

Located at `.github/ISSUE_TEMPLATE/project.yml`. Uses GitHub Issue Forms (not classic Markdown templates).

**Fields:**

| Field | Type | Required | Purpose |
|---|---|---|---|
| Project Name | input | yes | Card title |
| Short Summary | input | yes | Card subtitle |
| Description | textarea | no | Detailed info |
| Category | dropdown (20 options) | yes | Card grouping |
| Color | dropdown (10 options) | yes | Card accent color |
| External Links | textarea | no | Related URLs |
| Matrix Room | input | no | matrix.to link |
| Status | dropdown (6 options) | yes | Project stage |
| Notes | textarea | no | Additional context |

---

## Categories (20)

Governance, Development, Documentation, Community, Design, Infrastructure, Operations, Security, Messaging, Bridging, Matrix, Discord, Slack, Telegram, Migration, Onboarding, Integrations, Events, Funding, Research

## Colors (10)

| Name | Hex | Usage |
|---|---|---|
| red | `#f85149` | Card accent bar |
| orange | `#f0883e` | Card accent bar |
| yellow | `#d29922` | Card accent bar |
| lime | `#7ee787` | Card accent bar |
| green | `#3fb950` | Card accent bar |
| teal | `#2ea043` | Card accent bar |
| blue | `#58a6ff` | Card accent bar |
| indigo | `#6e40c9` | Card accent bar |
| purple | `#bc8cff` | Card accent bar |
| pink | `#f778ba` | Card accent bar |

---

## How to Create a New Project

1. Go to [Issues → New Issue](https://github.com/yncyrydybyl/ex-od-us/issues/new/choose)
2. Select "Project Entry"
3. Fill in the form fields
4. Submit
5. Add the appropriate category label and `color:X` label to the issue
6. The card appears on the website within seconds (on next page load)

**Note:** The issue form guides data entry, but labels must be manually applied (or could be automated with a GitHub Action in the future).

---

## Deployment

- **Hosting:** GitHub Pages, serving from the `/docs` directory on the `main` branch
- **API:** GitHub REST API v3, unauthenticated
- **Rate limits:** 60 requests/hour per IP for unauthenticated requests. Each page load makes 1 request (issues are fetched in a single paginated call). This is sufficient for a low-to-medium traffic site.
- **No build step:** Edit `docs/index.html`, push to `main`, site updates immediately

### Scaling Considerations

If traffic exceeds the unauthenticated rate limit:

1. **Cache with a GitHub Action:** Run a scheduled action that fetches issues and writes a JSON file to the repo. The static site reads the JSON file instead of calling the API. Zero API calls per page view.
2. **Add a GitHub token:** Authenticated requests get 5,000/hour.
3. **Use conditional requests:** `If-None-Match` / `ETag` headers to avoid counting cached responses against the limit.

---

## Limitations

- **Label management is manual:** Users must add category and color labels after submitting the form. A GitHub Action could automate this by parsing the form body on issue creation.
- **Rate limiting:** 60 req/hour unauthenticated. Fine for a prototype; solvable with caching for production.
- **No offline support:** Requires network to fetch issues.
- **Single-page:** No individual project pages (each card links to its GitHub issue).
- **Search is client-side:** Works fine for hundreds of issues; may need server-side filtering for thousands.

---

## What Could Be Automated

With a small GitHub Action (~20 lines), we could:

1. **Auto-apply labels** by parsing the issue form body for Category and Color selections
2. **Generate a static JSON cache** on a schedule, eliminating API rate limit concerns
3. **Validate issue form submissions** and comment if required fields are missing

This is intentionally left out of the spike to keep the prototype minimal.

---

## Final Evaluation

### 1. What prior art exists?

GitHub Issues as CMS is a well-established pattern for blogs and comments. Issue Forms (structured YAML) are newer and less explored for this purpose. The combination of Issue Forms + Labels + client-side rendering is relatively novel but assembles entirely from GitHub-native features.

### 2. Which pieces were reused?

Everything except ~200 lines of JavaScript:
- GitHub Issue Forms (structured input)
- GitHub Labels (structured metadata)
- GitHub REST API (data access)
- GitHub Pages (hosting)
- Native CSS Grid (layout)
- Native fetch API (data loading)
- Native URLSearchParams (URL state)

### 3. What was the smallest viable implementation?

One HTML file (`docs/index.html`) containing inline CSS and JavaScript. Zero dependencies. Zero build steps. The issue form template (`.github/ISSUE_TEMPLATE/project.yml`) is the only other essential file.

### 4. Is this architecture good enough for a larger public tracker?

Yes, with one addition: a GitHub Action to auto-apply labels and optionally cache issue data to a JSON file. The core architecture (issues as content, labels as schema, static rendering) scales well to hundreds of projects.

### 5. Where would complexity likely grow?

- **Label automation** — parsing form bodies to auto-apply labels
- **Richer cards** — images, progress bars, contributor avatars
- **Multi-page navigation** — if hundreds of projects need pagination
- **Real-time updates** — WebSocket or polling for live updates
- **Access control** — if some projects should be private
- **Analytics** — tracking which projects get the most views

None of these require abandoning the core architecture.

---

## File Structure

```
ex-od-us/
├── .github/
│   └── ISSUE_TEMPLATE/
│       ├── project.yml          # Issue form definition
│       └── config.yml           # Template chooser config
├── docs/
│   └── index.html               # Entire static website (single file)
├── 01-exodus-transform.svg      # Project branding assets
├── 02-exodus-mirror.svg
├── 03-exodus-modular.svg
├── 04-exodus-flow.svg
├── 05-exodus-domain.svg
├── 06-exodus-badge-sheet.svg
├── project-exodus-svg-pack.zip
├── find-matrix-repos.sh         # Sourcegraph search utility
└── README.md                    # This file
```
