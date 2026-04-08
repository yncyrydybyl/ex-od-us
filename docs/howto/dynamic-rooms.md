# Howto: Dynamic Matrix rooms for GitHub projects (Hookshot)

> This is a **read-before-you-enable** reference. The behaviors below
> were verified by reading
> [`matrix-hookshot/src/Connections/GithubIssue.ts`](https://github.com/matrix-org/matrix-hookshot/blob/main/src/Connections/GithubIssue.ts)
> directly, not just the user-facing docs. Line numbers in this doc
> refer to that file as of the version inspected.

## Two different things wear the word "dynamic"

When the Hookshot docs say "dynamic rooms" they actually mean two
distinct features. Pick the right one.

### 1. Auto-instantiated rooms via alias

A user joins `#github_owner_repo:your-server.org` and the bridge
**creates the room on the fly**. No admin setup, no per-repo state.
The aliases the bridge can mint:

```
#github_$owner:server                       → user/org space
#github_$owner_$repo:server                 → repo room
#github_$owner_$repo_$issuenumber:server    → issue room
#github_disc_$owner_$repo:server            → repo discussions
```

Source:
[`matrix-hookshot/docs/usage/dynamic_rooms.md`](https://github.com/matrix-org/matrix-hookshot/blob/main/docs/usage/dynamic_rooms.md).

This is a **bridge feature**, not something a GitHub project does.
Anyone running a Hookshot instance with this enabled can spin up a
room pointing at your repo without you doing anything.

> **Privacy warning** (from the Hookshot docs): aliases are queryable
> over federation and don't authenticate the requester. If your repo
> is private, do not enable this on a public bridge — it leaks the
> existence of private repos.

### 2. Statically-configured GitHub repo connections

The more common pattern. A maintainer creates a normal Matrix room,
invites the bridge bot, runs `!hookshot github repo <url>`, and the
room receives webhook notifications for issues, PRs, releases, and
optionally workflows / pushes.

That's covered well in the official docs and is the right default for
"a chat room for my project". The rest of this document is about
**issue rooms** specifically — the per-issue flavor of #1 — because
that's the one whose behavior surprises people.

## What an issue room actually does

An issue room is a Matrix room dedicated to a single GitHub issue,
created either via the `#github_owner_repo_42:server` alias trick or
when a parent repo room has `showIssueRoomLink: true` and a new issue
arrives.

It is **bidirectional, with caveats.**

### GitHub → Matrix (read path)

Implemented in `onIssueCommentCreated` → `onCommentCreated`
(`GithubIssue.ts:236-309`) and `syncIssueState` (`:311-425`).

When the room is first created, or when someone runs `!sync`:

1. **The issue body is posted as the first message**, attributed to a
   Matrix puppet of the issue author. The body is rendered both as
   plain text and as HTML. (`:333-351`)
2. **Every existing comment is backfilled** by replaying through the
   same `onCommentCreated` path. The bridge calls `listComments` and
   walks the result. (`:359-382`)
3. **Issue state changes are mirrored**: when the issue closes, a
   system notice is posted into the room and the room topic is
   updated. (`:384-417`)

While the room is live:

4. **New GitHub comments stream in** as messages from puppet users
   carrying the GitHub author's `login` and `avatar_url`. Every GitHub
   commenter who has ever touched the issue gets their own Matrix
   puppet account on your homeserver, named `@_github_<login>:server`.
   (`:271-298`)
5. **Issue title edits update the room name** via an `m.room.name`
   state event. (`onIssueEdited`, `:461-478`)
6. **`!sync`** triggers a full `syncIssueState` re-pull. Anyone in the
   room can run it; there is no auth check on this command. (`:507-510`)

The bot dedupes its own echoes via
`commentProcessor.hasCommentBeenProcessed` (`:260-269`) so a Matrix
message that round-trips through GitHub doesn't appear twice in the
room. There's a hardcoded 500ms delay before processing inbound
GitHub comments specifically to give that dedupe a chance to win the
race (`:259`).

### Matrix → GitHub (write path)

Implemented in `onMessageEvent` → `onMatrixIssueComment`
(`:506-514` → `:427-459`).

**Every regular message in the room becomes a GitHub comment on the
issue.** Verbatim. There is no command prefix, no opt-in, no
"are-you-sure". If a user types "hi" in an issue room, "hi" appears as
a comment on the GitHub issue.

The catch: the user must have **OAuth-authenticated their Matrix
account with the bridge** beforehand (`:431-442`). If they haven't:

- The message is **not posted to GitHub**.
- The bot **reacts** to their Matrix message with the emoji `⚠️ Not
  bridged`. That's the only feedback. No DM, no error message in the
  room. (`:433-440`)

## The four code-derived gotchas

These are the things the docs gloss over and that have bitten projects
in the wild.

### 1. No "are you sure", no command prefix, no preview

Casual chat in an issue room becomes public GitHub comments under the
speaker's GitHub account, **with full notification fanout to everyone
subscribed to the issue**. There is no `!comment` or `!post` prefix.
Every line is a comment.

Mitigation: tell people. Pin a room rule. The friendly version is "if
you wouldn't say it on GitHub, don't say it here." There is no
software lever for this short of patching Hookshot.

### 2. Authenticated and unauthenticated users mix silently

Inside the room, you cannot tell who is bridged unless you watch for
the `⚠️ Not bridged` reaction. Two people having "the same
conversation" visible in Matrix may appear very differently on GitHub
— one fully echoed, the other invisible. Newcomers will not understand
why their messages "aren't getting answers" on the GitHub side.

Mitigation: in the room topic, link to the bridge's auth instructions.
Encourage everyone to OAuth-link before posting.

### 3. Puppet accounts grow unboundedly

Every GitHub user who has ever commented on the issue gets a Matrix
puppet on your homeserver. For a long-running design issue with
hundreds of commenters, that's hundreds of puppet accounts, all of
them members of that one room. They show up in member lists, count
toward room membership, and exist forever.

This is fine for low-traffic issues. It is *not* fine if you enable
issue rooms for every issue on a busy repo via `showIssueRoomLink:
true` — you can end up with thousands of puppets across hundreds of
rooms, on a homeserver you maintain.

Mitigation: enable issue rooms **per-issue, opt-in**, not as a
default. The repo room (`!hookshot github repo`) doesn't have this
problem because it doesn't replay every commenter.

### 4. Persistence is in Matrix room state, not a database

Hookshot's selling point — "no external database required" — is true:
state like `comments_processed` lives in the Matrix room itself
(`:303-308`, `:419-424`). The cost is that **if you lose the room
state, the bridge replays the whole comment history from scratch**.
Comment 0 onwards. The `comments_processed === -1` check at `:321`
is the "haven't started yet" sentinel.

Practical implication: if you ever migrate or recreate the room (e.g.
the `migrateToNewRoom` path at `:494-504`), expect a full backfill
spam in the new room.

### Bonus: what's missing from issue rooms

- **No PR diff support.** The repo connection has a `prDiff` option,
  but `GithubIssue.ts` doesn't implement it. Issue rooms get the
  issue body and comments only, even for issues that are pull
  requests. The eight-year-old comment at `:354` shows the original
  author wondering whether to add it: `// ...was this intended as a
  request for code?`
- **No reactions bridging.** Comments are bridged. Reactions on
  GitHub comments are not.
- **No edits bridging.** Editing a GitHub comment doesn't update the
  Matrix message; the only event that updates room state is the
  issue title edit (which renames the room).

## Decide: enable, partial, or skip

| Use case | Recommendation |
|---|---|
| One small project room for everything | **Skip issue rooms.** Use `!hookshot github repo` only. |
| A few long-running design issues you want to discuss live | **Enable per-issue, opt-in.** Pin a topic explaining the comment-posting behavior. |
| Every issue on a busy repo | **Don't.** The puppet count and room sprawl will hurt. |
| Private repo | **Don't enable the alias-based dynamic room feature** at all on a public-federated bridge. |
| Public repo, lots of drive-by Matrix users | **Skip issue rooms.** The auth-asymmetry is silently confusing. |

## What a GitHub project itself can / should do

If a *bridge operator* sets up Hookshot pointing at your repo, the
GitHub side needs almost nothing:

1. **A webhook**, or installation of the operator's GitHub App, on the
   repo. One-time, repo Settings → Webhooks. Without this the room
   only sees commands going Matrix → GitHub, not events going GitHub
   → Matrix.
2. **Decide which events the room cares about** before turning it on.
   `issue.*`, `pull_request.*`, `release.*` are sensible defaults.
   `push` and `workflow.run.*` should be filtered (release branch
   only) or they will drown the room.
3. **Filter Dependabot/Renovate** via `excludingLabels` so the room
   doesn't become a dependency-bump firehose.
4. **Use `hotlinkIssues: { prefix: "#" }`** so when someone types
   `#42` in chat, the bot expands it to a link. Cheap, high-value.
5. **Install the GitHub App on an organization, not a personal
   account**, so the bridge keeps working when maintainership rotates.

## See also

- [Bots and widgets howto](bots-and-widgets.md) — opinionated list of
  bots that earn their keep, including the standard Hookshot setup.
- [`matrix-hookshot/docs/usage/dynamic_rooms.md`](https://github.com/matrix-org/matrix-hookshot/blob/main/docs/usage/dynamic_rooms.md)
- [`matrix-hookshot/docs/usage/room_configuration/github_repo.md`](https://github.com/matrix-org/matrix-hookshot/blob/main/docs/usage/room_configuration/github_repo.md)
- [`matrix-hookshot/src/Connections/GithubIssue.ts`](https://github.com/matrix-org/matrix-hookshot/blob/main/src/Connections/GithubIssue.ts)
  — the source of truth for the behaviors documented above.
