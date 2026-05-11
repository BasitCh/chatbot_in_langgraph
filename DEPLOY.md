# Deploy to Koyeb (free, always-on)

End-to-end checklist. Plan ~30 min.

---

## 1. Neon Postgres (free, scale-to-zero)

You already have a Neon DB — just run the schema once.

1. Sign in to <https://console.neon.tech>.
2. Select your project → **SQL Editor** → paste the entire contents of `init.sql` → **Run**. You should see "Success".
3. Grab your `DATABASE_URL` from **Dashboard → Connection Details**. Either the *direct* URL or the *pooled* URL (`-pooler` in the host) works — the app strips `-pooler.` automatically and connects in session mode.
   - Format: `postgresql://USER:PASSWORD@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require&channel_binding=require`

> Why session mode (direct), not transaction-mode pooler? LangGraph + Chainlit both want long-lived connections and prepared statements. Transaction-mode pgbouncer breaks prepared statements with `DuplicatePreparedStatementError`. Session mode is faster for a single-instance app anyway.

---

## 2. Backblaze B2 bucket

You already have B2 set up — just confirm:

- `B2_BUCKET` — bucket name (e.g. `chatbotstorage`)
- `B2_ENDPOINT` — full URL with scheme (e.g. `https://s3.us-east-005.backblazeb2.com`)
- `B2_ACCESS_KEY` — keyID from your B2 application key
- `B2_SECRET_KEY` — applicationKey
- Bucket is **Private** (chainlit serves files via signed URLs)

If you haven't yet: <https://www.backblaze.com> → B2 Cloud Storage → Buckets → Create. Then Application Keys → Add a New Application Key → scoped to that bucket, Read+Write.

---

## 3. Google OAuth

1. Go to <https://console.cloud.google.com> → create a project (or pick one).
2. **APIs & Services → OAuth consent screen**:
   - User type: **External**
   - App name: `Basit AI`
   - Support email: your Gmail
   - Scopes: leave default (email, profile, openid)
   - **Publishing status: Testing** (no need to verify; you can add up to 100 test users) **or** click "Publish" for any-Google-user access.
3. **APIs & Services → Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Web application**
   - Authorized redirect URIs: add **both**
     - `http://localhost:8000/auth/oauth/google/callback` (local dev)
     - `https://YOUR-KOYEB-URL/auth/oauth/google/callback` (you'll get this URL in step 5; come back and add it then)
4. Save the **Client ID** and **Client secret** → `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`.

> The app accepts any Google account that signs in. If your OAuth consent screen is in "Testing" mode, only emails you've added as test users can sign in. Click "Publish app" in the consent screen to open it to anyone.

---

## 4. Generate the Chainlit auth secret

Locally:
```bash
chainlit create-secret
```
Copy the output — that's `CHAINLIT_AUTH_SECRET`.

---

## 5. Push the code + deploy on Koyeb

1. Push this repo to GitHub (any name, public or private).
2. Sign up at <https://www.koyeb.com> (Google login works).
3. **Create Service → GitHub** → pick your repo.
4. **Service type:** `Web Service`
5. **Build:** `Dockerfile` (Koyeb auto-detects).
6. **Region:** match your Neon region (e.g. `Singapore sin` if Neon is `ap-southeast-1`, `Frankfurt fra` for `eu-central-1`).
7. **Instance:** `Eco` → `nano` (free tier).
8. **Ports:** `8000` HTTP (default).
9. **Environment variables** — paste every key from `.env.example` (drop the `# ...` comments). Especially:
   - `OPENAI_API_KEY`
   - `TAVILY_API_KEY`
   - `DATABASE_URL`
   - `B2_BUCKET`, `B2_ENDPOINT`, `B2_ACCESS_KEY`, `B2_SECRET_KEY`
   - `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`
   - `CHAINLIT_AUTH_SECRET`
   - `CHAINLIT_URL` — leave blank for now, set after first deploy.
   - `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` (optional)
10. **Deploy.** Koyeb assigns you a URL like `https://chatbot-yourname-xxxxx.koyeb.app`.

---

## 6. Wire the public URL back

1. Set `CHAINLIT_URL=https://chatbot-yourname-xxxxx.koyeb.app` (no trailing slash) in Koyeb env vars → redeploy.
2. Add `https://chatbot-yourname-xxxxx.koyeb.app/auth/oauth/google/callback` to Google OAuth's Authorized redirect URIs (step 3.3).

Visit the URL → "Sign in with Google" → done.

---

## Why this stack feels fast

| Layer | Why it's fast |
|---|---|
| Koyeb Eco instance | No auto-sleep on free tier — no cold starts. |
| Pre-compiled workflow | Graph compiles once at boot, not per session. |
| `min_size=2` warm pool | First message of the day skips TCP+TLS handshake. |
| `prepare_threshold=0` (session mode) | Checkpointer queries are server-side prepared after first run. |
| Indexed thread/step tables | Sidebar loads in <100ms even with hundreds of threads. |
| Streaming (`astream_events v2`) | Tokens render the moment the model emits them. |
| Parallel RAG ingestion | Multi-file uploads index concurrently while the agent runs. |

> **Heads-up on Neon free tier:** the Postgres compute auto-suspends after ~5 min idle and resumes in ~500ms-2s on the next query. The first message after a long idle will feel a hair slower; subsequent messages are instant. This is the only "cold start" in the stack — Koyeb itself stays warm.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `relation "User" does not exist` | You forgot step 1.2. Re-run `init.sql` in the Neon SQL Editor. |
| OAuth shows `redirect_uri_mismatch` | The Koyeb URL isn't in Google's Authorized redirect URIs (step 3.3). |
| `prepared statement "_pg3_…" already exists` | Your DATABASE_URL still has `-pooler.` AND something is bypassing the rewrite. Confirm `core/config.py` is unmodified, or paste the direct URL (without `-pooler.`). |
| Files upload but won't preview | Bucket is Public *or* the App Key doesn't have R/W on this bucket. |
| App boots but threads sidebar empty | Data layer not registered — make sure `OAUTH_GOOGLE_CLIENT_ID` is set (chainlit only enables the data layer when auth is on). |
| Anyone with Google can sign in but you only want yourself | Re-add the email check in `app.py`'s `oauth_callback` (compare `email` against an allowlist, return `None` otherwise). |
