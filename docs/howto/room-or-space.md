# Howto: Create a project room or space

> Status: **stub** — structure ready, prose TODO. PRs welcome.

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

1. _TODO: open Element → "+" → Create new room (or Create new space)._
2. _TODO: pick an alias. Conventions: lowercase project name, no
   prefix, on whichever homeserver you'll list it from. e.g.
   `#element-web:matrix.org`._
3. _TODO: set the room avatar — usually the project logo, square,
   at least 256×256._
4. _TODO: set the topic to one sentence + a link to the project
   README. The topic shows up in clients' join previews and is the
   first thing newcomers see._
5. _TODO: configure join rules. For an open project: "Anyone who knows
   the link can join", history visible to members. Avoid invite-only
   unless you have a reason._
6. _TODO: enable end-to-end encryption? **No** for a public community
   room — it makes search, bots, and bridges harder. **Yes** for a
   private maintainers' room._
7. _TODO: enable "Allow guests to join" only if you want non-Matrix
   users to lurk. Most projects don't bother._
8. _TODO: if you created a space, add at least one initial child room
   (`#general` or `#chat`) so the space isn't empty on first join._

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
