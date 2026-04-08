# Howto: Improve DevX and UX with bots and widgets

> Status: **stub** — structure ready, prose TODO. PRs welcome.

## Scope

By the end of this guide your community room has the bots and widgets
that *actually pay rent*: things people use, not things you set up
once and forget.

Specifically:

- A **GitHub/forge bot** posting issue and PR activity (read-only,
  high signal).
- A **CI status bot** for at least your release branch.
- A **welcome bot** that greets first-time joiners with the room
  rules and a link to the project README.
- An **embedded Etherpad / HedgeDoc widget** for drafting docs and
  meeting notes in-room.
- A **video call widget** (Element Call / Jitsi) so the room can hop
  to voice in one click.

This is the most opinionated guide. Most projects over-install bots
and end up with a noisy room.

## Prereqs

- A community room ([room-or-space](room-or-space.md)).
- A homeserver where you can register appservices, or a hosted bot
  account on matrix.org.
- The bot accounts you create here all need a power level high enough
  to send messages but not high enough to ban users. PL 0-50 is fine.

## Decide first: which bots earn their keep?

Honest list, ranked by value-per-noise:

1. **GitHub/forge activity bot** — ★★★★★. Read-only and high signal.
2. **Welcome bot** — ★★★★. Catches "where do I start" questions before
   they hit your maintainers.
3. **CI status bot for releases** — ★★★. CI for *every* branch is too
   noisy. Filter to release/main only.
4. **Etherpad/HedgeDoc widget** — ★★★. Hugely useful when used; often
   forgotten until needed.
5. **Video call widget** — ★★★. Reduces friction for impromptu calls.
6. **Reminder/scheduling bot** — ★★. Useful for community meetings.
7. **Sticker pack bot** — ★. Fun but doesn't move the needle.

Rule of thumb: **start with two**, add a third only when someone asks
for it.

## Steps

### GitHub/forge activity bot

1. _TODO: pick `matrix-hookshot` (the modern default) over older
   GitHub bridges._
2. _TODO: install hookshot or use a hosted instance._
3. _TODO: invite the bot, configure which repos and which event
   types you actually want (issues opened/closed, PRs opened/merged;
   skip `comments` unless you want noise)._
4. _TODO: filter labels — most projects don't want `dependabot` PRs in
   the room._

### Welcome bot

1. _TODO: any of: hookshot's welcome feature, a custom small bot, or
   an autoreply via mjolnir/draupnir's policy actions._
2. _TODO: keep the welcome message short. Two sentences and a link.
   Long welcome messages get ignored._

### CI status bot

1. _TODO: usually the same hookshot install configured with a webhook
   from your CI._
2. _TODO: filter to the release branch only. PR-level CI noise is for
   the PR thread on GitHub, not the chat room._

### Etherpad / HedgeDoc widget

1. _TODO: deploy a HedgeDoc instance (or use a hosted one)._
2. _TODO: in the room → "Add widget" → URL → point at the pad._
3. _TODO: pin the widget so it shows in the right rail by default._

### Video call widget

1. _TODO: easiest path: use Element's built-in "Start a call" if
   you're on Element ≥ 1.11._
2. _TODO: alternative: add a Jitsi widget that creates an ad-hoc
   meeting URL._

## Gotchas

- Bots accumulate. Audit your bot list every six months and remove
  the ones nobody talks about.
- Widgets that point at external URLs break when the external service
  rotates auth or shuts down. Use widgets you control.
- Welcome bots that DM new joiners are creepy and increasingly blocked
  by clients. Greet in the room.
- Hookshot is one bot that does many things. Don't install five bots
  to do what one hookshot can.

## Further reading

- [matrix-hookshot docs](https://matrix-org.github.io/matrix-hookshot/)
- [HedgeDoc](https://hedgedoc.org/)
- [Element Call](https://element.io/blog/element-call-and-the-future-of-real-time-communication/)
- [Widgets in Matrix](https://matrix.org/blog/2019/03/12/widgets-in-element/)
