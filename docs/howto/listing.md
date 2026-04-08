# Howto: Get listed on matrix.org and matrixrooms.info

> Status: **stub** — structure ready, prose TODO. PRs welcome.

## Scope

By the end of this guide your room is:

- **Discoverable** in the matrix.org room directory (the public list
  shipped with most clients).
- **Indexed** at [matrixrooms.info](https://matrixrooms.info), the
  community-maintained search engine for Matrix rooms.
- **Linked** from your project's README via a `matrix.to` URL and a
  shields.io badge — the two patterns this site
  ([ex-od-us](https://github.com/yncyrydybyl/ex-od-us)) actually
  scans for. Your project will then show up here automatically on the
  next enrichment run.

This is the cheapest highest-leverage step. 30 minutes, no install.

## Prereqs

- A room with a public alias and topic
  ([room-or-space guide](room-or-space.md)).
- The room set to "Anyone with the link can join".

## Steps

### 1. Add a `matrix.to` link to your README

`https://matrix.to/#/#myproject:matrix.org`

This is the canonical "join my Matrix room" link. It works in every
Matrix client. Put it in:

- The README's "Community" / "Chat" section.
- The project website footer.
- The repo's About sidebar (GitHub: Settings → website field
  accepts matrix URLs in the description, not the URL slot).

### 2. Add a shields.io badge

```markdown
[![Matrix](https://img.shields.io/matrix/myproject:matrix.org?label=%23myproject%3Amatrix.org&logo=matrix)](https://matrix.to/#/#myproject:matrix.org)
```

This badge is the **most common signal** Matrix-related sites scrape
for. Adding it gets your room counted in places like ex-od-us
automatically.

### 3. Publish to the matrix.org room directory

_TODO: in Element → room settings → "Publish to public room
directory" → choose `matrix.org`._

The room must have a public alias and join rules of "anyone".

### 4. Submit to matrixrooms.info

_TODO: matrixrooms.info crawls public room directories on a schedule.
Just being in the matrix.org directory is usually enough — but if you
want to be sure, [submit your room here](https://matrixrooms.info/)._

### 5. Optional: list with topic-specific aggregators

- **Awesome lists**: many languages and topics have an
  `awesome-<topic>` repo on GitHub with a "Community" section. PR
  yourself in.
- **Federated discovery**: if you joined any cross-project space
  (`#matrix:matrix.org`, language-specific spaces), announce your
  room there with a one-line message. Don't spam.

## Gotchas

- The matrix.org room directory only lists rooms that opt in. Just
  having a public alias isn't enough.
- The shields.io badge URL must use the **room alias**, not the room
  ID (the `!opaque:server` form). Aliases display nicely; room IDs
  don't.
- ex-od-us scans both `matrix.to/#/#alias` and shields badges. As of
  PR #7215 it also picks up `matrix.to/#/!ROOMID:server` if that's
  what your README uses, but the alias form is still preferred.
- The matrix.org directory has light moderation. If your project is
  abuse-adjacent (e.g. anything that touches scraping, ad-tech,
  cracking), expect questions.

## Further reading

- [matrix.org room directory](https://matrix.to/#/#matrix:matrix.org)
- [matrixrooms.info](https://matrixrooms.info)
- [shields.io Matrix badge docs](https://shields.io/badges/matrix)
- [ex-od-us scanner README](https://github.com/yncyrydybyl/ex-od-us)
