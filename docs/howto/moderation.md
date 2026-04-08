# Howto: Set up moderation tools

> Status: **stub** — structure ready, prose TODO. PRs welcome.

## Scope

By the end of this guide you have:

- A clear **role hierarchy** in the room (admin, moderator, member).
- A **mod policy room** so moderators can coordinate without it being
  visible in the main channel.
- **Mjolnir** or **Draupnir** running and watching the room for
  policy-list-based bans, redactions, and abuse reports.
- An **abuse reporting flow**: where reports go, who acks them, and
  how the reporter is notified.
- A **community policy** document linked from the room topic.

Should take 1-2 hours from a fresh room.

## Prereqs

- A room you control (see [room-or-space](room-or-space.md)).
- A homeserver that lets you run a bot account, or a bot account on
  matrix.org. ([homeserver guide](homeserver.md))
- One co-moderator. Solo moderation burns out fast.

## Decide first: Mjolnir or Draupnir?

Both are policy-list-driven moderation bots maintained by Matrix
Foundation people.

- **Mjolnir** is the original, written in TypeScript. Heavier but more
  battle-tested.
- **Draupnir** is a recent fork with the same protocol and most of the
  same commands. Smaller, faster, more actively developed.

For a new project, **Draupnir** is the current default. If you already
run Mjolnir, there's no rush to migrate.

## Steps

1. _TODO: create dedicated bot accounts._
   - One for the moderation bot.
   - Optionally a separate one for any "echo to maintainers" bot.
2. _TODO: create the policy room._
   - This is where bans/redactions get logged. Invite-only, mods only.
3. _TODO: install Draupnir (Docker/binary/source)._
   - Link to canonical install docs.
4. _TODO: configure the bot to manage your community room._
   - Give it `admin` power level (PL 100) in the room.
   - Point it at the policy room.
5. _TODO: subscribe to community ban lists._
   - `#community-moderation-effort-ban-list:neko.dev` is a sensible
     default. Don't subscribe blindly — review what each list contains.
6. _TODO: write a one-page community policy._
   - Link from the room topic.
   - Cover: scope (on-topic vs off-topic), prohibited content,
     reporting flow, appeals.
7. _TODO: appoint at least 2 moderators with the right power level._
   - Avoid making the bot the only path to moderation. A bot you can't
     reach in an emergency is worse than no bot.

## Gotchas

- The bot's bot-level needs to be **higher** than the worst person it
  might need to ban. PL 100 (admin) is the safe choice.
- Removing your bot account's PL by accident locks you out of moderation
  permanently in some clients.
- Ban lists are someone else's policy. Subscribing transfers some of
  your moderation decisions to that list's maintainer. Pick lists you
  trust.
- E2EE rooms can't be moderated by message-content rules (the bot can't
  see content). Most projects keep their public room unencrypted for
  this reason — see [room-or-space](room-or-space.md).

## Further reading

- [Draupnir docs](https://the-draupnir-project.github.io/draupnir-documentation/)
- [Mjolnir docs](https://github.com/matrix-org/mjolnir)
- [Matrix Code of Conduct (template)](https://matrix.org/code-of-conduct/)
- [Community moderation effort ban list](https://matrix.to/#/#community-moderation-effort-ban-list:neko.dev)
