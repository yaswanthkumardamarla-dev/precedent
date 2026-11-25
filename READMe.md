# Precedent

Decision memory for pull requests: extracts engineering decisions from PR review threads and flags new PRs that contradict them.

## How it works

1. **Extract.** When someone comments on a PR (or the PR is closed), Precedent reads the review discussion and asks Gemini which comments state a lasting rule, such as *"All new endpoints must have type hints."* Each decision is stored with a link to its source comment and an embedding, in Postgres with pgvector.
2. **Check.** When a PR is opened or updated, Precedent embeds each changed file, finds the closest past decisions, and asks Gemini whether the change goes against any of them. If it does, Precedent comments on the PR. It edits that same comment on later runs instead of posting new ones.
3. **Review.** The dashboard lists decisions and flagged PRs. Decisions start as **proposed**. **Accept** a decision to keep it when its PR is re-extracted, or **retire** it so it is no longer flagged.

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
- **Subscribe to events:** Pull request, Pull request review, Pull request review comment, Issue comment.

Then generate a private key, save it as `backend/github-app.pem`, and install the app on the repos you want watched.

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
DASHBOARD_PASSWORD=<optional locally; required in production>
```

Open http://localhost:3000. If `DASHBOARD_PASSWORD` is set, you are sent to a sign-in page first. Signing in lasts 30 days, and changing the password signs everyone out.

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
| `GET` | `/api/summary` | Counts for the dashboard |
| `GET` | `/api/decisions?repo=&status=&q=` | Decisions, newest first |
| `PATCH` | `/api/decisions/{id}` | Set status: `{"status": "accepted" \| "retired" \| "proposed"}` |
| `GET` | `/api/conflicts?repo=` | Conflicts, with the decision each one cites |
| `GET` | `/api/events?limit=` | Recent webhook deliveries and job results |

`/api/*` requires `Authorization: Bearer <API_TOKEN>`, and refuses every request if `API_TOKEN` is not set. Only the dashboard's server calls it, and browsers never see the token. The dashboard itself is protected by `DASHBOARD_PASSWORD`. In production it stays locked if that is not set.

## Tests

```sh
cd backend && pip install -r requirements-dev.txt && python -m pytest -q tests
cd frontend && npm run lint && npm run build
```

GitHub Actions runs both on every push to `main` and on every pull request.

## Deploying for free (Render + Neon)

Everything runs on free plans: the database on [Neon](https://neon.tech), and the backend and dashboard on [Render](https://render.com) using [`render.yaml`](render.yaml). Neither needs a credit card.

1. **Database:** sign up at neon.tech and create a project. Copy its connection string (it starts with `postgresql://` and ends with `sslmode=require`). pgvector is built in, and the tables are created when the backend first starts.
2. **Render:** choose **New → Blueprint**, then pick this repository. Fill in what it asks for: `DATABASE_URL` (the Neon string), `GITHUB_WEBHOOK_SECRET`, `GITHUB_APP_ID`, `GITHUB_CLIENT_ID`, `GEMINI_API_KEY`, and `GITHUB_PRIVATE_KEY` (paste the full contents of the `.pem` file). `API_TOKEN` and `DASHBOARD_PASSWORD` are generated for you.
3. When it's deployed, check that the backend's URL is `https://precedent-backend.onrender.com`. If Render gave it a different one, update `BACKEND_URL` on the dashboard service to match.
4. In the GitHub App's settings, set the **Webhook URL** to `https://<backend URL>/webhooks/github`, and stop smee.
5. Open the dashboard and sign in. The password is under **precedent-dashboard → Environment → DASHBOARD_PASSWORD**, and you can change it to your own there.

What "free" costs you:

- **Free services sleep after 15 idle minutes.** The first page load after that takes up to a minute.
- **A webhook that arrives while the backend sleeps times out at GitHub.** GitHub never retries on its own, so once the backend is awake it asks GitHub to resend any webhooks it missed (`app/redeliver.py`, every 5 minutes). Nothing is lost, but the PR comment may arrive a minute or two late. To avoid the delay, move the backend to Render's always-on Starter plan ($7/month).
- **Neon's free database holds 0.5 GB,** far more than decisions need.

To check it: open a PR in a watched repo. Within a minute or two it shows up under **Activity** on the dashboard, and the PR gets Precedent's comment if it breaks a decision.

## Configuration

| Variable | Required | Default |
| --- | --- | --- |
| `DATABASE_URL` | yes | |
| `GITHUB_WEBHOOK_SECRET` | yes | |
| `GITHUB_APP_ID`, `GITHUB_CLIENT_ID` | yes | |
| `GITHUB_PRIVATE_KEY_PATH` | | `github-app.pem` (relative to `backend/`) |
| `GITHUB_PRIVATE_KEY` | | Key text, used instead of the file when hosted |
| `GEMINI_API_KEY` | yes | |
| `GEMINI_MODEL` | | `gemini-flash-latest` |
| `EMBEDDING_MODEL` | | `gemini-embedding-001` |
| `API_TOKEN` | yes | Shared with the dashboard as `BACKEND_API_TOKEN` |
| `REDELIVERY_SWEEP_SECONDS` | | `300`; how often to ask GitHub to resend missed webhooks. `0` turns it off |
| `BACKEND_URL` (frontend) | | `http://127.0.0.1:8000` |
| `BACKEND_API_TOKEN` (frontend) | yes | |
| `DASHBOARD_PASSWORD` (frontend) | in production | |
