# Howto: Set up a project homeserver

> Status: **stub** — structure ready, prose TODO. PRs welcome.

## Scope

By the end of this guide you have:

- A Matrix homeserver (Synapse, Dendrite, or Conduit) running on a
  domain you control, e.g. `matrix.myproject.org`.
- A working **server discovery** setup (`.well-known/matrix/server` and
  `.well-known/matrix/client`) so users can sign in with
  `@alice:myproject.org`.
- TLS via Let's Encrypt or your existing reverse proxy.
- Federation working — you can join `#matrix:matrix.org` from your
  server and the messages flow.
- A clear **registration policy**: open, invite-only, or closed to new
  signups (most projects start invite-only).

This is the longest guide here. Budget a half-day if you've never
operated a federated service before.

## Prereqs

- A domain you control (DNS access).
- A small Linux VPS (Synapse on 2 vCPU / 4 GB RAM is comfortable for
  the first hundred users).
- Comfort with: nginx/caddy/traefik, Docker (optional), Let's Encrypt,
  PostgreSQL.
- A real email address for the homeserver admin (used for password
  reset and abuse reports).

## Decide first: which homeserver?

| | Synapse | Dendrite | Conduit |
|---|---|---|---|
| Maturity | most mature, feature-complete | newer, fast-moving | smallest, simplest |
| Language | Python | Go | Rust |
| Memory footprint | medium | low | very low |
| Best for | "I want every feature" | "I want active development" | "I want one binary, no Postgres" |

For a single-project community room, **Conduit** or **Dendrite** are
usually the right call. **Synapse** is the safe default if you're not
sure.

## Steps

1. _TODO: DNS setup._
   - `A` record for `matrix.myproject.org` pointing at your VPS.
   - `.well-known` files served from `myproject.org` so the matrix-id
     `@alice:myproject.org` resolves correctly.
2. _TODO: install your chosen homeserver._
   - Link to the canonical install docs for each (Synapse, Dendrite,
     Conduit).
   - Brief on PostgreSQL setup for Synapse/Dendrite.
3. _TODO: configure the server name._
   - The most common mistake: setting `server_name` to
     `matrix.myproject.org` when you want users to be
     `@alice:myproject.org`. The server name is the public id; the
     hostname is where the server lives.
4. _TODO: TLS via reverse proxy (Caddy/nginx + Let's Encrypt)._
5. _TODO: enable federation._
   - Open ports 8448 *or* set up SRV record for port redirection.
   - Test with `https://federationtester.matrix.org/`.
6. _TODO: set the registration policy._
   - Most projects start with `enable_registration: false` and create
     accounts manually for maintainers via `register_new_matrix_user`.
   - Open registration is rarely a good idea — spam follows fast.
7. _TODO: create the first admin account._
8. _TODO: join `#matrix:matrix.org` from your new account to verify
   federation works end-to-end._

## Gotchas

- The server_name is permanent. Renaming it later is essentially
  impossible without losing identity.
- Without `.well-known`, federation works but client logins won't be
  pretty.
- Synapse without PostgreSQL gets sad above ~50 active users. Don't
  start on SQLite if you expect growth.
- Federation needs a public IP. If you're behind CGNAT, you'll need a
  proxy with a public IP that forwards `8448` and `443/.well-known/`.
- Let's Encrypt rate-limits aggressively — get the cert path working
  on a staging endpoint first.

## Further reading

- [Synapse install guide](https://element-hq.github.io/synapse/latest/setup/installation.html)
- [Dendrite install guide](https://matrix-org.github.io/dendrite/installation)
- [Conduit install guide](https://docs.conduit.rs/)
- [Federation tester](https://federationtester.matrix.org/)
- [.well-known explainer](https://matrix.org/docs/older/server-discovery/)
