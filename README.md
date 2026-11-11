# Comm2 Reviewer

Static Astro reviewer site (18 parts, per-part + whole-course exams) plus a
stateless FastAPI AI grader. Single user, no auth beyond the deploy gate.

## Content sync (vault → site)

Reviewer sources live outside the repo:

```sh
# default VAULT, overridable per run
node scripts/sync-content.mjs --check   # validate only (~143 items, CHECK OK)
VAULT_REVIEWERS=/path/to/Reviewers node scripts/sync-content.mjs --check

node scripts/sync-content.mjs           # writes src/content/parts, src/data/exams, public/pdfs
```

## Web

```sh
pnpm dev      # astro dev (background); status: pnpm astro dev status
pnpm astro build
```

Bake the grader endpoint at build time:

```sh
PUBLIC_GRADER_URL=http://localhost:8000/grade pnpm astro build
```

## Grader (stateless, no DB, no history)

```sh
cp grader/.env.example grader/.env   # fill GRADER_API_KEY + GRADER_MODEL, never commit
cd grader && uvicorn app:app --host 0.0.0.0 --port 8000
curl -s localhost:8000/health        # {"ok": true}
python3 grader/test_grader.py        # rubric sums, caps, validator, prompt, fixture grade
```

| Env | Default | Notes |
|---|---|---|
| `GRADER_BASE_URL` | `https://opencode.ai/inference/go/openai/v1` | Go gateway; fallback `https://api.deepseek.com` |
| `GRADER_API_KEY` | (required) | Never committed (`.gitignore` covers `.env`) |
| `GRADER_MODEL` | `deepseek-v4.1-flash` | Exact pinned inference id, echoed per grade with `model_date` (live-catalog id; `deepseek-v4-flash` 400s upstream). Needs a console-minted personal key — workspace-scoped keys 401 at completions even when `/models` 200s. Fallback: `GRADER_BASE_URL=https://api.deepseek.com` + DeepSeek direct key (~P0.05/grade) |
| `GRADER_CUTOFF` | `2025-06-30` | Law-as-of date in the examiner prompt |
| `PUBLIC_GRADER_URL` | `http://localhost:8000/grade` | Build-time; exam pages POST `{id,stem,answer,profile,authorities}` here |

## Coolify deploy

Two services from this repo:

- **comm2-web** (`Dockerfile.web`): static `dist/` on nginx. Put Traefik
  BasicAuth on this service (single user gate).
- **comm2-grader** (`grader/Dockerfile`): uvicorn on 8000, `GET /health`.
  Set `GRADER_BASE_URL` / `GRADER_API_KEY` / `GRADER_MODEL` / `GRADER_CUTOFF`
  envs here. No volumes, no DB.

Point the web build at the grader's full endpoint URL (path included), e.g.
`PUBLIC_GRADER_URL=http://comm2-grader:8000/grade` as the web service's
build arg. (Exam pages also normalize a bare host by appending `/grade`.)

Password rotation (web BasicAuth via htpasswd):

```sh
htpasswd -nbB user 'new-password'   # paste the line into the Traefik
                                    # BasicAuth middleware value, redeploy web
```
