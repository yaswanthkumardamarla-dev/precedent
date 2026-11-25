# Precedent

Decision memory for pull requests: extracts engineering decisions from PR review threads and flags new PRs that contradict them.

It runs as a free public demo. Visitors see a read-only demo repository without signing in; anyone can **Sign in with GitHub**, install the Precedent GitHub App on their own public repositories, and see only those.

## How it works

1. **Extract.** When someone comments on a PR (or the PR is closed), Precedent reads the review discussion and asks Gemini which comments state a lasting rule, such as *"All new endpoints must have type hints."* Each decision is stored with a link to its source comment and an embedding, in Postgres with pgvector.
2. **Check.** When a PR is opened or updated, Precedent embeds each changed file, finds the closest past decisions, and asks Gemini whether the change goes against any of them. If it does, Precedent comments on the PR. It edits that same comment on later runs instead of posting new ones.
3. **Review.** The dashboard lists decisions and flagged PRs. Decisions start as **proposed**. **Accept** a decision to keep it when its PR is re-extracted, or **retire** it so it is no longer flagged.

### Who sees what

- **Visitors (not signed in)** see the repositories in `DEMO_REPOS`, read-only.
- **Signed-in people** see the repositories they can reach through Precedent's installations, as GitHub reports them for their account. Only people with write access to a repository can accept or retire its decisions.
- The dashboard's server forwards the person's GitHub token, and the backend asks GitHub itself, so the browser can't claim access it doesn't have.

### Free-demo rules

- **Public repositories only.** Pull requests in private repositories are skipped, and nothing from their webhooks is stored. PR code is sent to Gemini's free tier, which may use it to improve Google's products. That's acceptable for public code, but not for private code.
- **Daily limits** (per 24 hours): `REPO_DAILY_JOB_LIMIT` checks per repository (20), `OWNER_DAILY_JOB_LIMIT` per account (40), and `GLOBAL_DAILY_JOB_LIMIT` overall (300). Jobs over a limit are recorded as `limited` and shown on the Activity page.
- **Leaving deletes your data.** Removing Precedent from a repository, or uninstalling it, deletes that repository's decisions, conflicts and webhook records. Webhook records are also pruned after 30 days.

```
GitHub ──webhook──▶ FastAPI (backend/) ──▶ Gemini (extract / check / embed)
                         │
                         ▼
                 Postgres + pgvector ◀── Next.js dashboard (frontend/)
```

## Requirements

- Docker (for the database)
- Python 3.11+
- Node.js 20+
- A [Gemini API key](https://aistudio.google.com/apikey)
- A GitHub App you own (see below)

## Setup

### 1. Database

```sh
docker compose up -d
```

The tables are created in step 3 by `python -m app.migrate`, which applies `backend/schema.sql`. It is safe to re-run, and the hosted backend runs it on every deploy.

### 2. GitHub App

Create an app under **GitHub → Settings → Developer settings → GitHub Apps**:

- **Webhook URL:** a channel from [smee.io](https://smee.io) for local development, or your server's `/webhooks/github` URL when hosted.
- **Webhook secret:** any random string. It goes in `GITHUB_WEBHOOK_SECRET`.
- **Repository permissions:** Pull requests: *Read & write*, Issues: *Read & write* (to comment on PRs), Metadata: *Read*.
- **Subscribe to events:** Pull request, Pull request review, Pull request review comment, Issue comment. Installation events arrive automatically, and Precedent uses them to delete data when it's removed.
- **Where can this GitHub App be installed?** *Any account*, so anyone can try it.
- **Callback URL** (for Sign in with GitHub): `<dashboard URL>/auth/callback`. Add `http://localhost:3000/auth/callback` too, for local development.
- **Setup URL** (where GitHub sends people after installing): `<dashboard URL>/?installed=1`, with **Redirect on update** ticked.

Then generate a private key and save it as `backend/github-app.pem`, and generate a **client secret** for the dashboard's `GITHUB_CLIENT_SECRET`.

### 3. Backend

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # then fill in the values; API_TOKEN can be any long random string
python -m app.migrate
uvicorn app.main:app --reload
```

`GET http://127.0.0.1:8000/health` should return `{"status": "ok", "pgvector": "..."}`.

To forward GitHub webhooks to your machine, run this in a second terminal:

```sh
npx smee-client -u <SMEE_URL> -t http://127.0.0.1:8000/webhooks/github
```

### 4. Dashboard

```sh
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` first:

```sh
BACKEND_URL=http://127.0.0.1:8000
BACKEND_API_TOKEN=<the same value as API_TOKEN in backend/.env>
GITHUB_CLIENT_ID=<the GitHub App's Client ID>
GITHUB_CLIENT_SECRET=<a client secret generated in the GitHub App's settings>
SESSION_SECRET=<any random string of 32+ characters; it seals the sign-in cookie>
```

Open http://localhost:3000. Without signing in you see the demo repositories. A sign-in lasts as long as GitHub's token: 8 hours.

## Running extraction and checks by hand

The webhook runs these automatically. From `backend/`, you can also run them on any PR:

```sh
python -m app.extract OWNER/REPO PR_NUMBER          # extract decisions from a PR's discussion
python -m app.check   OWNER/REPO PR_NUMBER          # check a PR against past decisions
python -m app.check   OWNER/REPO PR_NUMBER --post   # ...and comment on the PR
```

Add `--show` to either command to print exactly what is sent to the model.

## API

| Method | Path | What it does |
| --- | --- | --- |
| `POST` | `/webhooks/github` | GitHub webhook receiver (signature-verified) |
| `GET` | `/health` | Database and pgvector check |
| `GET` | `/api/me?refresh=` | The viewer, their repositories, the install link and the limits |
| `GET` | `/api/summary` | Counts for the dashboard |
| `GET` | `/api/decisions?status=&q=` | Decisions, newest first, each with `can_edit` |
| `PATCH` | `/api/decisions/{id}` | Set status: `{"status": "accepted" \| "retired" \| "proposed"}`. Needs write access |
| `GET` | `/api/conflicts` | Conflicts, with the decision each one cites |
| `GET` | `/api/events?limit=` | Recent webhook deliveries and job results |

`/api/*` requires `Authorization: Bearer <API_TOKEN>`, and refuses every request if `API_TOKEN` is not set. Only the dashboard's server calls it; browsers never see the token. Each answer covers the viewer in `X-GitHub-Token` (the signed-in person's GitHub user token), or the demo repositories when that header is absent.

## Tests

```sh
docker compose exec db psql -U precedent -c "CREATE DATABASE precedent_test"   # once
cd backend && pip install -r requirements-dev.txt && python -m pytest -q tests
cd frontend && npm run lint && npm run build
```

The database tests use the separate `precedent_test` database (`TEST_DATABASE_URL`), never your real one, and are skipped when it isn't reachable. CI runs them against its own Postgres.

GitHub Actions runs both on every push to `main` and on every pull request.

## Deploying for free (Neon + Render + Vercel)

| Part | Where | Why there |
| --- | --- | --- |
| Database | [Neon](https://neon.tech) | Free Postgres with pgvector that doesn't expire |
| Backend | [Render](https://render.com), via [`render.yaml`](render.yaml) | A normal long-running server, which the webhook jobs and missed-webhook recovery need |
| Dashboard | [Vercel](https://vercel.com) | Made for Next.js, and free projects don't sleep |

None of them needs a credit card. Set them up in this order:

1. **Database (Neon):** sign up and create a project. Copy its connection string (it starts with `postgresql://` and ends with `sslmode=require`). pgvector is built in, and the tables are created when the backend first starts.
2. **Backend (Render):** choose **New → Blueprint**, then pick this repository. Fill in what it asks for: `DATABASE_URL` (the Neon string), `GITHUB_WEBHOOK_SECRET`, `GITHUB_CLIENT_ID`, and `GEMINI_API_KEY`. Then open the service's **Environment → Secret Files**, add a file named `github-app.pem`, and paste the full contents of the `.pem` file. When the service starts, its log shows `[startup] GitHub App key: OK` if the key loaded. When it's deployed, note two things on the service's page: its URL (for example `https://precedent-backend.onrender.com`), and under **Environment**, the generated `API_TOKEN`. Opening `<URL>/health` should show `"status": "ok"`.
3. **Dashboard (Vercel):** choose **Add New → Project** and import this repository. Set **Root Directory** to `frontend`; Vercel detects Next.js by itself. Under **Environment Variables**, add:
   - `BACKEND_URL`: the backend URL from step 2, with no trailing slash
   - `BACKEND_API_TOKEN`: the `API_TOKEN` value from step 2
   - `GITHUB_CLIENT_ID`: the GitHub App's Client ID
   - `GITHUB_CLIENT_SECRET`: a client secret generated in the GitHub App's settings
   - `SESSION_SECRET`: any random string of 32+ characters

   Then deploy. If you change these variables later, redeploy so they take effect.
4. **GitHub App:** in its settings, set the **Webhook URL** to `<backend URL>/webhooks/github` and stop smee. Then set the **Callback URL**, **Setup URL** and **Any account** as described in [Setup](#2-github-app).

What "free" costs you:

- **The backend sleeps after 15 idle minutes.** A webhook that arrives while it sleeps times out at GitHub. GitHub never retries on its own, so once the backend is awake it asks GitHub to resend any webhooks it missed (`app/redeliver.py`, every 5 minutes). Nothing is lost, but a PR comment may arrive a minute or two late. The same pass also re-runs jobs that failed, for example because Gemini was briefly unavailable, or that were cut off by a restart. Each job gets up to 3 attempts within 6 hours.
- **The first dashboard load after a quiet stretch can take up to a minute,** because the dashboard waits for the backend to wake. The dashboard itself doesn't sleep.
- To remove both delays, move the backend to Render's always-on Starter plan ($7/month).

To check it: open a PR in a watched repo. Within a minute or two it shows up under **Activity** on the dashboard, and the PR gets Precedent's comment if it breaks a decision.

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `DATABASE_URL` | yes | |
| `GITHUB_WEBHOOK_SECRET` | yes | |
| `GITHUB_CLIENT_ID` | yes | The App's Client ID, used to sign in to GitHub as the App |
| `GITHUB_PRIVATE_KEY_PATH` | | `github-app.pem` (relative to `backend/`) |
| `GEMINI_API_KEY` | yes | |
| `GEMINI_MODEL` | | `gemini-3.5-flash-lite` |
| `EMBEDDING_MODEL` | | `gemini-embedding-001` |
| `API_TOKEN` | yes | Shared with the dashboard as `BACKEND_API_TOKEN` |
| `REDELIVERY_SWEEP_SECONDS` | | `300`; how often to ask GitHub to resend missed webhooks. `0` turns it off |
| `BACKEND_URL` (frontend) | | `http://127.0.0.1:8000` |
| `BACKEND_API_TOKEN` (frontend) | yes | |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` (frontend) | yes | For Sign in with GitHub |
| `SESSION_SECRET` (frontend) | yes | 32+ random characters; changing it signs everyone out |
| `DEMO_REPOS` | | Comma-separated `OWNER/REPO` list shown to visitors |
| `REPO_DAILY_JOB_LIMIT`, `OWNER_DAILY_JOB_LIMIT`, `GLOBAL_DAILY_JOB_LIMIT` | | `20`, `40`, `300` |
