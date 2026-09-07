# Deployment (VPS, Docker, GitHub Actions)

How `codejudge_mcp` + `codejudge_ai` get from a git push to running on your
VPS behind aaPanel. Code: [`Dockerfile`](../Dockerfile),
[`docker-compose.prod.yml`](../docker-compose.prod.yml),
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml),
[`.github/workflows/cd.yml`](../.github/workflows/cd.yml). Scope is this repo
only — `CodeJudge` (the Go judge) and `CodeJudge-UI` deploy separately, by
their own repos.

## The pieces

- **One `Dockerfile`, two entrypoints.** `codejudge_mcp` and `codejudge_ai`
  are the same Python distribution already (`pyproject.toml`), so one image
  serves both — `docker-compose.prod.yml` runs it twice with a different
  `command:`.
- **`docker-compose.prod.yml`** — two services: `mcp` (no host port at all —
  only `ai` can reach it, over the compose network) and `ai` (bound to
  `127.0.0.1:8000`, for aaPanel's Nginx to reverse-proxy to). No `db`
  service — see "The shared Postgres instance" below.
- **`ci.yml`** — runs on every push/PR: install + an import/wiring smoke
  check (same style used by hand throughout development). No secrets needed.
- **`cd.yml`** — `workflow_dispatch` only, **not** automatic on push. Builds
  the image, pushes it to Docker Hub, then SSHes into the VPS to pull it and
  restart the stack.
- **aaPanel** owns the reverse proxy and TLS (Let's Encrypt) — nothing in
  this repo does that; it's a few clicks in aaPanel's own UI, covered below.

## How the environment reaches the containers

Worth being precise about, since it's easy to get lost in: `docker compose`
automatically loads a file literally named `.env` sitting **next to the
compose file**, and uses it to fill in every `${VAR}` in the YAML. Nothing in
`docker-compose.prod.yml` says "read `.env`" — that's just how the CLI always
behaves. What the file *does* say is which vars each service wants, e.g.
`GEMINI_API_KEY: ${GEMINI_API_KEY}`.

The full round-trip:

```
1. ONCE, by you, locally:
   write a real prod .env (see "The prod .env" below)
   base64-encode it, paste the blob into the GitHub secret PROD_DOTENV_B64

2. EVERY TIME cd.yml runs:
   decodes PROD_DOTENV_B64 -> a plain .env file, in the CI runner
   scp's it to the VPS as ~/codejudge-ai/.env.prod, then `mv`s it to .env
   (same directory as docker-compose.prod.yml)

3. ON THE VPS:
   `docker compose -f docker-compose.prod.yml pull && up -d`
   runs FROM ~/codejudge-ai/, where that real .env now sits
   compose resolves every ${VAR} against it -> becomes the containers' real env
```

**Deliberate choice: explicit `environment:` entries, not `env_file: [.env]`.**
`CodeJudge`'s own compose file uses `env_file: [.env]`, which dumps every key
from `.env` straight into the container. Ours instead names each var
individually (`GEMINI_API_KEY: ${GEMINI_API_KEY}`, etc.) — more typing, but
you can see exactly what `mcp` and `ai` each actually consume just by reading
the compose file, without cross-referencing a separate `.env`. Kept this way
on purpose; not switching to match `CodeJudge`'s convention.

## One-time setup

### 1. GitHub repository secrets (Settings → Secrets and variables → Actions → **Secrets**)

| Secret | What |
|---|---|
| `DOCKERHUB_USERNAME` | Your Docker Hub username |
| `DOCKERHUB_TOKEN` | A Docker Hub **access token** (not your account password) |
| `VPS_HOST` | The VPS's IP or hostname |
| `VPS_USER` | SSH user on the VPS |
| `VPS_SSH_KEY` | Private key matching a public key already authorized on the VPS (`~/.ssh/authorized_keys`) |
| `VPS_PORT` | SSH port (usually `22`) |
| `PROD_DOTENV_B64` | Base64 of the prod `.env` file — see below |

### 2. GitHub repository variable (Settings → Secrets and variables → Actions → **Variables**)

| Variable | What |
|---|---|
| `CODEJUDGE_AI_IMAGE` | Docker Hub image path, e.g. `yourusername/codejudge-ai` |

**This must also appear as a key inside the prod `.env`** (see below), with
the *same* value — `cd.yml` pushes to `vars.CODEJUDGE_AI_IMAGE`, but it's
`docker-compose.prod.yml` running on the VPS that decides what to *pull*, and
it reads that name from `.env`, not from GitHub. If it's missing from `.env`,
compose falls back to a bare `codejudge-ai` repo name and `pull` fails —
this is the single most likely first-deploy mistake.

### 3. The shared Postgres instance

Per the earlier decision: `ai`'s session storage lives on the **same**
Postgres instance `CodeJudge` uses, in its own database — not a dedicated
container, not `CodeJudge`'s own database or credentials.

1. Create a database and a dedicated user for it:
   ```sql
   CREATE DATABASE codejudge_ai_sessions;
   CREATE USER codejudge_ai WITH PASSWORD '<a real password>';
   GRANT ALL PRIVILEGES ON DATABASE codejudge_ai_sessions TO codejudge_ai;
   ```
   (Via aaPanel's database manager if it handles Postgres, or `psql` directly
   — whichever you already use for `CodeJudge`'s own database.)
2. **Make sure Postgres actually accepts connections from Docker containers**
   — the most common first-deploy failure. A default install only listens on
   `localhost`, which a container is not. You need:
   - `listen_addresses` in `postgresql.conf` to include the address
     containers connect from (or `*`, relying on the VPS firewall to keep
     Postgres itself unreachable from the public internet — it should not be
     open on the VPS's public IP regardless).
   - A `pg_hba.conf` entry allowing that address/subnet with password auth
     for the `codejudge_ai` user/database. If connecting via
     `host.docker.internal` (what `docker-compose.prod.yml` sets up), find
     the actual bridge subnet with `docker network inspect
     codejudge-ai_default` after first bringing the stack up, and allow that.
   - Restart Postgres after either change.
3. The resulting DSN goes in `.env` as `CODEJUDGE_AI_SESSION_DB_URL` (format
   below).

### 4. aaPanel: reverse proxy + SSL

All clicks, nothing scriptable from here:

1. Add a **Site** for the domain/subdomain you want (e.g. `ai.yourdomain.com`).
2. On that site, set up **Reverse Proxy** → target `127.0.0.1:8000` (where
   `ai` publishes, per `docker-compose.prod.yml`).
3. **SSL** tab → issue a free Let's Encrypt certificate (DNS must already
   point at the VPS) → force HTTPS.

`mcp` needs no aaPanel entry at all — it's never reachable outside the
compose network.

## The prod `.env`

This is the file you write once, then base64-encode into `PROD_DOTENV_B64`:

```
GEMINI_API_KEY=
CODEJUDGE_BASE_URL=
CODEJUDGE_AI_SESSION_DB_URL=postgresql+asyncpg://codejudge_ai:<password>@host.docker.internal:5432/codejudge_ai_sessions
CODEJUDGE_AI_GUARDRAIL=heuristic
CODEJUDGE_AI_AUTHOR_MODEL=
CODEJUDGE_AI_ADVERSARIAL_MODEL=
CODEJUDGE_AI_IMAGE=yourusername/codejudge-ai
IMAGE_TAG=latest
```

- `GEMINI_API_KEY` — required, real secret.
- `CODEJUDGE_BASE_URL` — wherever `CodeJudge` ends up. **If it's on the same
  VPS, this must be `http://host.docker.internal:8888`, not
  `http://localhost:8888`** — `localhost` inside the `mcp` container is the
  container itself, not the VPS host. (CodeJudge runs in its own separate
  compose project, so it isn't on this stack's network either; the
  `extra_hosts` entry on `mcp` is what makes the host reachable.) If
  CodeJudge isn't deployed yet, any placeholder is fine — `codejudge_mcp`
  degrades to an `"error"` field per tool call, not a crash.
- `CODEJUDGE_AI_SESSION_DB_URL` — from step 3 above. If `host.docker.internal`
  doesn't end up being how Postgres is reached, use whatever address does.
- `CODEJUDGE_AI_GUARDRAIL` / `*_AUTHOR_MODEL` / `*_ADVERSARIAL_MODEL` —
  optional overrides, same meaning as local dev (`.env.example`).
- `CODEJUDGE_AI_IMAGE` / `IMAGE_TAG` — must match the GitHub variable in
  step 1.

Encode it:

```bash
base64 -w0 .env.prod   # paste the output into the PROD_DOTENV_B64 secret
```

## Deploying

Actions tab → `CD` workflow → **Run workflow** (`workflow_dispatch`). Builds,
pushes, and restarts the VPS stack in one run. Not automatic on push —
deliberate, so a deploy is always something you chose to trigger.

## The RAG store is a manual step, not part of the pipeline

`sync_docs`/`ingest` need the sibling `CodeJudge` repo's docs and a live
Gemini call — neither belongs in CI or the image build. Do this locally,
whenever the docs meaningfully change (not every deploy):

```bash
python -m codejudge_ai.scripts.sync_docs
python -m codejudge_ai.scripts.ingest
scp -r codejudge_ai/rag/store/* <user>@<vps>:~/codejudge-ai/rag_store/
ssh <user>@<vps> 'cd ~/codejudge-ai && docker compose -f docker-compose.prod.yml restart ai'
```

(`~/codejudge-ai/rag_store/` must exist on the VPS, next to
`docker-compose.prod.yml` — it's the bind mount target.) Skipping this just
means Q&A answers with no retrieved context, not a crash.

## First-run checklist

- [ ] `docker compose -f docker-compose.prod.yml ps` on the VPS shows both
      `mcp` and `ai` running.
- [ ] `curl http://127.0.0.1:8000/healthz` on the VPS responds.
- [ ] `https://<your domain>/healthz` responds through aaPanel's proxy + TLS.
- [ ] A doc-grounded question gets a real answer (proves the RAG store step
      above actually ran).
- [ ] A live-lookup question ("what problems exist?") either answers with
      real data or degrades cleanly with an error, depending on whether
      `CodeJudge` is reachable yet — both are correct behavior.

## Known limitations

- **Manual deploys only** (`workflow_dispatch`) — no auto-deploy on push.
  Deliberate for now; add `on: push` to `cd.yml` later if that changes.
- **The Postgres reachability step (setup §3) is the most likely first-deploy
  failure** — a default install simply won't accept the container's
  connection until `listen_addresses`/`pg_hba.conf` are adjusted.
- **`CODEJUDGE_AI_IMAGE` must match in two places** (the GitHub variable and
  the prod `.env`) — nothing currently checks they agree.
- **No automated CD for the RAG store** — see above; it's a real, accepted
  gap, not an oversight.

Related: [RUNNING.md](RUNNING.md) (the local 3-process topology this
Dockerizes), [ARCHITECTURE.md](ARCHITECTURE.md).
