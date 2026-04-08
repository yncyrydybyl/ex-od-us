# Howto: Set up or use bridges

> Status: **stub** — structure ready, prose TODO. PRs welcome.

## Scope

By the end of this guide you have:

- A clear sense of which bridges your project actually needs (vs.
  which ones look cool but you'll regret).
- A working bridge from at least one of: Discord, IRC, Telegram,
  Slack, GitHub.
- An understanding of **portal vs. plumbed vs. puppeted** bridge modes
  and which one your community wants.
- A maintenance plan — bridges break more often than rooms do.

This is the guide most likely to age badly. The bridge ecosystem moves
fast.

## Prereqs

- A community room ([room-or-space](room-or-space.md)).
- A homeserver you control if you want to run the bridge yourself
  ([homeserver](homeserver.md)). You can use a hosted bridge instead;
  see below.
- Admin / API access to whatever you're bridging *to* (e.g. Discord
  bot token, IRC oper, Telegram bot, Slack workspace).

## Decide first: which bridges, which mode?

### Which bridges

Most projects only need **one or two**. Pick based on where your
existing community is, not where you wish they were.

- **Discord** — by far the most common ask for new projects. Bridge
  to Matrix and let users pick their client.
- **IRC** — long-tail open-source projects often have an existing
  Libera/OFTC channel. Bridging is non-disruptive and brings them
  along.
- **Telegram** — common for crypto/Linux/regional communities.
- **Slack** — usually only worth it if you have a paying customer
  community on Slack you can't move.
- **GitHub** (notification bridge, not chat) — useful for "issues
  posted to channel" but not the same kind of bridge.

### Which mode

- **Portal**: every channel on the other side becomes a Matrix room
  automatically. Easiest to set up. Best for "I want to mirror an
  entire Discord server in Matrix".
- **Plumbed**: you manually link a *specific* Matrix room to a
  *specific* room on the other side. More control, less surprise.
  Best for "I want my one #general bridged to my one #general".
- **Puppeted (double-puppeting)**: each Matrix user appears as
  themselves on the other side, not as a generic bot. Highest fidelity
  but requires per-user setup. Best for established communities that
  don't want a wall of `[matrix] alice: hello` lines.

For a new project, **plumbed + double-puppeted** is the right default.
Portal mode is tempting but creates a maintenance nightmare across
hundreds of bridged rooms you didn't ask for.

## Steps (Discord example)

1. _TODO: pick `mautrix-discord` (current default) over the older
   `matrix-appservice-discord`._
2. _TODO: create a Discord application + bot token._
3. _TODO: install the bridge (Docker / source / hosted)._
4. _TODO: register the appservice with your homeserver._
5. _TODO: provision the bridge — open a DM with the bridge bot from
   your Matrix account, run `login-token`._
6. _TODO: link your Discord guild + channels to specific Matrix
   rooms (plumbed mode)._
7. _TODO: enable double-puppeting per the bridge's docs._
8. _TODO: smoke-test: send a message both ways, verify formatting,
   replies, edits, attachments, mentions._

(IRC, Telegram, Slack: same shape, different bridge package. Link to
each bridge's canonical install doc.)

## Hosted bridges (you don't have to run them yourself)

- [t2bot.io](https://t2bot.io) — runs hosted bridges for several
  platforms. Free, community-maintained.
- [beeper.com](https://beeper.com) — commercial multi-platform bridge
  hub. Fine for personal use, less common for project communities.
- Some bridges (notably mautrix-*) are easy enough that running your
  own is the better long-term answer.

## Gotchas

- Bridges break more often than the rest of your stack. Subscribe to
  the bridge's release notes / room.
- E2EE in the bridged Matrix room kills most bridges. Either accept
  unencrypted on the public side, or accept the encryption-aware
  bridge mode (newer bridges support this; older ones don't).
- Edits, reactions, replies, threads — none of these were in IRC's
  vocabulary. Bridge them through and they look like noise on the IRC
  side. Configure carefully.
- Renaming or deleting the bridge bot's account orphans every bridged
  room. Treat the bot account as production infrastructure.

## Further reading

- [mautrix bridges (Discord, Telegram, Signal, WhatsApp, ...)](https://docs.mau.fi/bridges/)
- [matrix-appservice-irc](https://github.com/matrix-org/matrix-appservice-irc)
- [Bridging best practices (matrix.org blog)](https://matrix.org/blog/categories/bridging/)
- [t2bot.io hosted bridges](https://t2bot.io/)
