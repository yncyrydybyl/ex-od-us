# Howto: Create a project room or space

## Scope

By the end of this guide you have:

- A Matrix **room** for general community chat (or a **space** if you
  expect more than one room from day one).
- A short, memorable **alias** like `#myproject:matrix.org` (or your
  homeserver of choice) so people can join via a single URL.
- A **room avatar**, **topic**, and **join rules** appropriate for an
  open-source project — usually "anyone with the link, history visible
  to members".
- A `matrix.to` link you can paste into your README's badge or "Chat"
  button.

Should take 15 minutes from a fresh Element account.

## Prereqs

- A Matrix account on any homeserver (matrix.org is fine to start;
  see [the homeserver guide](homeserver.md) if you want your own).
- Decided on a project name + a one-line description.

## Decide first: room or space?

- **Room** if your community will fit in a single chat for the
  foreseeable future. Easier to manage; easier for newcomers to join
  one place and see everything.
- **Space** if you already need separate channels (`#dev`, `#users`,
  `#announcements`, `#offtopic`). A space is a container that holds
  rooms; people join the space and discover its rooms inside.

Default to a single room. Promote to a space later if traffic justifies
it. Splitting too early fragments a small community.

## Steps

1. **Open the create dialog.** In Element, click the `+` button next to
   "Rooms" in the left sidebar and pick *New room*. For a space, click
   the `+` at the top of the spaces column on the far left and pick
   *Create a new space*. Other clients have the same affordances under
   similar names; the room-vs-space choice is the one that matters.

2. **Pick an alias.** The alias is the permanent URL for your room
   (`#name:homeserver`). Use the lowercase project name with no
   `project-` or `chat-` prefix, on whichever homeserver you'll list it
   from — e.g. `#element-web:matrix.org`. If the bare name is taken,
   prefer a short scoped form (`#element-web-dev:matrix.org`) over a
   noisy one. Avoid dashes-vs-underscores churn later by picking one
   convention now.

3. **Set the room avatar.** Upload the project logo. Square, at least
   256×256, PNG with a transparent background if the logo has one.
   Element crops to a circle in most places, so anything that relies on
   square corners will look wrong — test it before committing.

4. **Write the topic.** One sentence describing the project plus a link
   to the README or homepage. The topic is what clients show in join
   previews and room directories, so it's the first thing a newcomer
   reads before deciding whether to join. Example:
   *"Element Web — a Matrix client for the web. https://element.io"*.

5. **Configure join rules.** Open *Room settings → Security & Privacy*.
   For an open-source community room, set *Who can access this room?*
   to **Anyone who knows the link can join** (also called "public") and
   *Who can read history?* to **Members only, since they joined**.
   Avoid *Invite only* unless you actually have a reason — it turns
   every newcomer into a support ticket for the mods.

6. **Do not enable end-to-end encryption** on a public community room.
   E2EE in Matrix is per-room and irreversible: once on, you cannot
   turn it off. It breaks server-side search, most bots, bridges, and
   history visibility for people who join later. Only enable E2EE on a
   *separate* private maintainers' room where you actually need it.

7. **Leave guest access off** unless you have a specific reason to
   allow it. Guest access lets non-Matrix users peek at the room
   without signing up; in practice very few projects use it, bridges
   and bots don't care about it, and it opens a small abuse surface.
   Skip it and move on.

8. **If you created a space, give it a child room immediately.** An
   empty space is confusing — new members join and see nothing. Create
   at least one room inside it (conventionally `#general` or `#chat`)
   and mark it as a *suggested* child so clients surface it on first
   join. You can add `#dev`, `#announcements`, etc. later as traffic
   justifies them.

## Gotchas

- Aliases are bound to the homeserver you create them on. If you
  later move to your own homeserver, the old alias stays at the old
  one — plan for one canonical alias from day one.
- "Public" doesn't mean "discoverable". Even with public join rules,
  no one will find your room unless you list it
  (see [the listing guide](listing.md)) or link it from your README.
- E2EE breaks bots. Many projects regret turning it on for the
  community room.

## Further reading

- [Matrix.org: Creating rooms](https://matrix.org/docs/communities/)
- [Element FAQ on spaces vs. rooms](https://element.io/help#spaces)
- [matrix-spec: Room aliases](https://spec.matrix.org/latest/#room-aliases)
