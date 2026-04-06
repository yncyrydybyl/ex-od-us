# Design System — Exodus Project Tracker

## Product Context
- **What this is:** A public tracker for open-source projects migrating to Matrix
- **Who it's for:** Open-source community members, project maintainers, Matrix advocates
- **Space/industry:** Open-source tooling, community infrastructure, decentralized communication
- **Project type:** Data dashboard / public directory
- **By:** datanauten.de

## Aesthetic Direction
- **Direction:** Industrial-Utilitarian with activist edge
- **Decoration level:** Minimal — data density and clarity over decoration
- **Mood:** Mission control for a community migration. Serious about the cause, clear about the data, alive with the rotating header pulse. Not a SaaS product, not a portfolio. A tool with purpose.
- **Reference:** The EX→US brand mark (01-exodus-transform.svg) sets the tone. Blue connection paths, green destination, dark ground.

## Brand Mark
- **Identity:** "EX → US" — the transformation from proprietary platforms to Matrix
- **Mark:** "EX" in light text, connection paths in blue, "US" in green
- **SVG assets:** 01-06 in repo root
- **Usage:** The mark can be rendered inline as text (EX in --text, US in --accent-green) when SVG is impractical

## Typography
- **Display/Hero:** Inter 800 — matches the brand SVGs, heavy and clear
- **Body:** Inter 400/500 — same family, clean reading at small sizes
- **UI/Labels:** Inter 600
- **Data/Tables:** JetBrains Mono — scores, timestamps, room aliases, anything machine-readable
- **Code:** JetBrains Mono
- **Loading:** Google Fonts `Inter:wght@400;500;600;800` + `JetBrains+Mono:wght@400;600`
- **Scale:** 12px (caption) / 13px (small) / 14px (body) / 16px (large body) / 20px (h3) / 24px (h2) / 32px (h1) / 48px (hero)

## Color
- **Approach:** Restrained — green and blue carry all the meaning, everything else is neutral
- **Derived from:** Brand SVG assets (01-exodus-transform.svg, 06-exodus-badge-sheet.svg)

### Palette

| Token | Hex | Usage |
|---|---|---|
| `--bg` | `#0b0f14` | Page background |
| `--surface` | `#131920` | Cards, panels, modal |
| `--surface-hover` | `#1a2230` | Card hover, active states |
| `--border` | `#243040` | Card borders, dividers |
| `--border-subtle` | `#1a2230` | Inner dividers (footer line) |
| `--text` | `#e8edf2` | Primary text, headings |
| `--text-muted` | `#8a97a8` | Secondary text, timestamps, descriptions |
| `--text-faint` | `#4a5568` | Rank numbers, very low emphasis |
| `--accent-green` | `#8bf0c7` | Matrix / positive / "US" brand color |
| `--accent-green-solid` | `#16a34a` | CTA buttons, Matrix badges, high score |
| `--accent-green-hover` | `#2ea043` | Button hover |
| `--accent-blue` | `#7aa2ff` | Links, connections, interactive elements |
| `--accent-blue-solid` | `#2563eb` | Active states, focus rings |
| `--score-low` | `#f85149` | Exodus score 0-3 (red) |
| `--score-mid` | `#d29922` | Exodus score 4-6 (amber) |
| `--score-high` | `#8bf0c7` | Exodus score 7-10 (brand green) |

### Platform Colors (for exodus bar left icon)
| Platform | Hex |
|---|---|
| Discord | `#5865F2` |
| Telegram | `#26A5E4` |
| Slack | `#4A154B` |
| WhatsApp | `#25D366` |
| Signal | `#3A76F0` |
| IRC | `#8a97a8` (muted) |
| XMPP | `#8a97a8` (muted) |

### Platform Accent (card top bar)
| Platform | Hex |
|---|---|
| GitHub | `#e8edf2` (light) |
| GitLab | `#fc6d26` (orange) |
| Codeberg | `#2185d0` (blue) |
| Other | `#8a97a8` (muted) |
| None | `#243040` (border) |

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — data-rich but not cramped
- **Scale:** 2xs(2px) xs(4px) sm(8px) md(16px) lg(24px) xl(32px) 2xl(48px) 3xl(64px)
- **Card padding:** 14px 16px (0.875rem 1rem)
- **Grid gap:** 16px (1rem)
- **Section gap:** 24px (1.5rem)

## Layout
- **Approach:** Grid-disciplined
- **Grid:** auto-fill, minmax(320px, 1fr)
- **Max content width:** 1200px
- **Border radius:** sm(4px) for badges/inputs, md(6px) for avatars, lg(8px) for cards, xl(12px) for modals

## Motion
- **Approach:** Intentional — the slot-machine header is the signature animation
- **Card entrance:** fade-in + slight translateY on scroll (IntersectionObserver)
- **Exodus bar fill:** 1s ease-out on scroll into view
- **Hero rotation:** 5s interval, slot-machine bounce (cubic-bezier 0.34, 1.56, 0.64, 1)
- **Hover:** 0.15s border-color transition on cards
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(100ms) short(150ms) medium(300ms) long(600ms)

## Components

### Matrix Badge (card top-right)
Shields-style badge: `[M icon] enter room` / `enter space` / `chat user` / `no room`
- Active: green label (#16a34a), dark icon bg (#0b0f14)
- Empty: muted label (#243040), muted icon (#4a5568)

### Exodus Bar (card bottom)
`[Platform icon] ████░░░░░░ [M] 6/10`
- Track: --border (#243040)
- Fill: linear-gradient(90deg, --score-low, --score-mid, --score-high)
- Platform icon in its brand color, hidden at score 9+
- Green M on the right

### CTA Button
- Background: --accent-green-solid
- Text: white
- Hover: --accent-green-hover
- Border-radius: 6px
- Padding: 0.45rem 1rem

## Anti-patterns (do not use)
- GitHub's default blue (#58a6ff) — use brand blue (#7aa2ff) instead
- GitHub's card bg (#161b22) — use brand surface (#131920) instead
- Purple gradients, decorative blobs, 3-column icon grids
- Centered-everything layout
- Generic hero sections

## Decisions Log
| Date | Decision | Rationale |
|---|---|---|
| 2026-04-06 | Initial design system | Derived from existing SVG brand assets. Industrial-utilitarian direction matches the mission-driven product. |
| 2026-04-06 | Inter as primary font | Already used in all 6 brand SVGs. Consistency over novelty. |
| 2026-04-06 | Brand colors over GitHub defaults | The SVGs define a specific palette (#0b0f14, #7aa2ff, #8bf0c7). The site should use the brand, not GitHub's theme. |
