# Positron - Pode Abrir (podeabrir.com)

**Ephemeral, end-to-end encrypted document sharing.** People keep sensitive documents (medical
exams, contracts, statements, certificates) encrypted on their own device and let someone else
**read** chosen documents for a short time, then it is over. Three ways to share, all with the
same rules (time limit, open limit, PIN, end at any moment, visible history):

- **In person** (`/ler/`): the reader's screen shows a QR; the owner scans it with the phone.
- **Remote link** (`/s/<id>#key`): view once ("like a snap"), or for a few hours/days, optional PIN.
- **Personal address** (`podeabrir.com/@nome`): the reader asks; the owner approves on the phone
  after comparing a 6-digit code.

The server stores only ciphertext, wrapped keys and **sealed titles**. Documents are decrypted
**only in the browsers the owner authorizes**; recipients cannot download, see a watermark and a
countdown. See [ephemeral access](docs/ephemeral_access_2026-11-25.md) and the
[crypto assessment](docs/crypto_assessment_2026-11-25.md).

## Brand

Brand kit in `frontend/assets/` (see its `LEIA-ME.md`): Grafite `#2C2923`, Marfim `#FCEEDB`.
The header uses the wordmark SVG, the footer and landing page the symbol, and the landing's
"Quem pode ler seu documento?" section the diagrams in `frontend/assets/pode-abrir-diagrama/`
(desktop and mobile SVG via `<picture>`); favicons, app icons,
the Open Graph image (`og:image`, link previews) and the web wordmark are copied into
`frontend/public/` by `npm run brand` (runs automatically before `dev` and `build`). Emails carry
their own copy of the wordmark (`exams/email_assets/logo.png`, embedded inline as `cid:`), so the
logo shows whatever server sent the message and without loading remote images. Contact:
contato@podeabrir.com (landing page, footer, emails).

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Django 5.2 (JSON API), PostgreSQL (psycopg 3), WhiteNoise, Gunicorn |
| Frontend | TypeScript, React 19, React Router 7, Vite 8, PDF.js 6, lucide-react icons |
| Crypto | WebCrypto: PBKDF2 + HKDF, AES-256-GCM, ECDH P-256, SHA-256 (browser); TOTP (pyotp) + Fernet, Web Push RFC 8291 via http_ece + py-vapid (server) |
| Tests | Django test runner (API), Vitest (crypto, with Python cross-check vectors) |

Vite + React was chosen over Next.js on purpose: decryption happens only in the client, so a
static, CSP-locked bundle with no server rendering is simpler and easier to pin and verify.
In production Django serves both the API and the built SPA from one container.

## Repository layout

```
positron/
├── VERSION                # platform version (shown under the login card)
├── start_server.py        # unified launcher (backend + frontend)
├── scripts/e2e_database.py  # create/drop the disposable positron_e2e database
├── scripts/generate_azure_app_settings.py  # .env -> Azure Web App settings JSON
├── scripts/deploy/        # container entrypoint (roles) and healthcheck
├── manage.py
├── requirements.txt       # pinned Python deps
├── Dockerfile             # node build stage + python 3.11 runtime
├── .env / .env.example    # all server parameters (never commit .env)
├── exams/                 # Django app (API)
│   ├── settings.py        # env-driven configuration
│   ├── urls.py            # /api/* routes + SPA fallback
│   ├── responses.py       # {data, error} envelope + error codes
│   ├── security.py        # middleware (CSP, size limit), auth helpers, rate limit, audit log
│   ├── account.py         # session, login, logout, vault password check, health
│   ├── enrollment.py      # invitations by email (bootstrap + staff), sign-up + TOTP
│   ├── admin_area.py      # admin area API: invitations, access requests, admin role
│   ├── password_reset.py  # email reset with recovery code (E2EE preserved) or fresh vault
│   ├── outbox.py, mailer.py, email_templates.py  # SMTP outbox (ported from agenda_ai)
│   ├── library.py         # documents: list (paginated), upload, ciphertext (sealed metadata)
│   ├── grants.py          # owner: list, approve (in person / @), links, extend, end
│   ├── reader.py          # reader screen: in-person QR and @handle requests (no account)
│   ├── links.py           # remote link recipients: preview, PIN, open, content
│   ├── policy.py          # grant states, lifetime presets, hash-chained history
│   ├── profile.py         # @handle, push subscriptions, history endpoint
│   ├── push.py            # Web Push (RFC 8291 + VAPID)
│   ├── crypto_format.py   # validation of keys/envelopes produced by the browser
│   ├── models.py, forms.py, qr.py, spa.py, uploads.py
│   ├── management/commands/  # bootstrap_invite, generate_vapid, send_emails, prune_access, flush_access
│   └── tests.py
├── frontend/              # React + TypeScript SPA (Vite)
│   ├── src/lib/           # crypto.ts (+ tests), api.ts, session, vault, documents, push
│   ├── src/components/    # Layout, PdfReader, ReaderView, DocumentPicker, DurationSelect,
│   │                      # Countdown, RecoveryCode, RequireOwner, Alert
│   ├── src/pages/         # Landing, Login, Enroll, ForgotPassword, ResetPassword, Library,
│   │                      # Upload, DocumentViewer, Approve, ShareLink, Grants, Account,
│   │                      # Invitations, Reader (/ler, /@nome), LinkReader (/s/<id>)
│   ├── assets/            # brand kit (source of truth): wordmark, symbol, favicons, social image
│   ├── public/            # sw.js (push + offline page only), offline.html, manifest; brand files from assets/
│   │                      # by scripts/copy-brand-assets.mjs before every dev/build
│   └── scripts/copy-pdf-assets.mjs  # PDF.js fonts/cmaps/wasm served from our origin
└── docs/                  # dated technical records
```

## Quick start (local)

Requirements: conda, Node.js 22.12+ with npm, Docker (the shared PostgreSQL container
`agenda_ai_local_pg`, port 55432).

```bash
# 1. Python environment (Python 3.11)
conda create -n positron python=3.11
conda activate positron
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env
python manage.py bootstrap_invite     # prints VAULT_NAMESPACE, DJANGO_SECRET_KEY,
                                      # TOTP_ENCRYPTION_KEY, BOOTSTRAP_INVITE_DIGEST
                                      # and the installation code for the first account
# paste the four values into .env, fill PG_LOCAL_PASSWORD and the EMAIL_* block,
# keep the installation code private

# 3. Run everything (installs frontend deps on first run, applies migrations)
python start_server.py
```

Open `http://localhost:5190/cadastro/`, expand "Primeira conta desta instalação", enter the
installation code and your email. Open the invitation link you receive, choose a password,
**save the recovery code**, and set up an authenticator app (any TOTP app). The first
account is staff and invites others by email.

| Mode | Command | URL |
|---|---|---|
| Development (hot reload) | `python start_server.py` | App `http://localhost:5190`, API `http://localhost:8030/api/` |
| Production-like (built SPA served by Django, real CSP) | `python start_server.py --build` | `http://localhost:8030` |

`start_server.py` also runs the email worker (`manage.py send_emails`). It re-launches itself with the `positron` conda interpreter if started from
another Python, refuses to start if a port is busy (it never kills other projects' servers),
and stops every child process on Ctrl+C.

WebCrypto requires a secure context: `localhost` works, but testing the phone flow on a real
device needs HTTPS (use the Azure deployment or an HTTPS tunnel).

## How it works

1. **Email accounts, invite only.** The email is the identity. Invitations are emailed and
   bound to that address (valid `INVITATION_HOURS`); the first account requests its own with
   the installation code. Sign-up and login require a TOTP code. At sign-up the browser shows
   a **recovery code** once.
2. **Upload.** The browser checks the file is a PDF (up to `PDF_MAX_MB`), encrypts it with a
   fresh AES-256-GCM key, seals the title and issuer with that same key, wraps the key with the
   vault key and uploads only ciphertext (the date stays readable for ordering). The library
   decrypts titles locally; search and column sorting happen in the browser. Files can be dragged
   onto the upload zone or anywhere on the library. Rows support multi-select with bulk actions
   (link, in-person, delete) and per-row actions (open, share, download, delete with confirmation);
   uploads and deletions appear immediately (optimistic, rolled back on failure). Only the owner
   can download; recipients never can.
3. **Share.** In person (QR on `/ler/`), by link (`/compartilhar/`) or through `/@nome`. The
   owner's browser re-seals only the chosen data keys for that grant (ECDH for readers, a random
   link key carried in the URL fragment for links). Lifetimes are presets capped at 7 days.
4. **Read.** Recipients need no account. Their browser decrypts locally; the reader shows a
   countdown, burns a watermark into the page ("divulgação proibida", LGPD notice and a `Ref.`
   that traces back to the grant in the owner's list), has no download and blocks printing. The server checks the grant
   on every request (expiry, opens, PIN lockout, revocation).
5. **Control.** "Compartilhamentos" lists pending requests, active grants (Estender / Encerrar,
   optimistic with rollback) and the hash-chained "Quem viu" history, verified in the browser.
   The installable app can push "pedido de leitura" and "link aberto" notifications.
6. **Forgot password.** An emailed link plus the TOTP code plus the recovery code resets the
   password and keeps every document (the browser re-seals the vault key; the server never sees
   it). Without the recovery code the user can still regain the account with an empty vault;
   old documents are deleted after explicit confirmation. Details:
   [docs/auth_email_recovery_2026-11-25.md](docs/auth_email_recovery_2026-11-25.md).

Copies, screenshots and files already rendered by the recipient are outside the reach of
revocation.

## Configuration (.env)

All server parameters live in `.env` (template: `.env.example`). `exams/settings.py` loads it
with python-dotenv; real environment variables always win (App Service, CI, Docker).

| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` (HTTP, local PostgreSQL container) or `production` (HTTPS, TLS to PostgreSQL, `__Host-` cookies) |
| `APP_ORIGIN` | Public origin users open, no trailing slash. Dev: the Vite server `http://localhost:5190` |
| `BACKEND_HOST`, `BACKEND_PORT`, `FRONTEND_PORT` | Ports used by `start_server.py` and the Vite proxy |
| `VAULT_NAMESPACE` | Public salt for every password-derived key. **Never change it on an existing install** |
| `DJANGO_SECRET_KEY` | Django signing key (50+ chars in production) |
| `TOTP_ENCRYPTION_KEY` | Fernet key that encrypts TOTP secrets at rest |
| `BOOTSTRAP_INVITE_DIGEST` | SHA-256 of the one-time invite for the first account |
| `PG_LOCAL_*` | Local PostgreSQL (shared container). `PG_LOCAL_DATABASE=positron_db` (browser tests: `positron_e2e`) |
| `POSTGRES_*` | Azure / CI PostgreSQL (production uses `sslmode=verify-full`) |
| `EMAIL_ENABLED`, `EMAIL_SMTP_*`, `EMAIL_FROM_*`, `EMAIL_REPLY_TO` | SMTP for invitations and reset (local: agenda_ai mailbox). `false` prints emails in the `[mailer]` console (development only) |
| `EMAIL_IMAP_HOST`, `EMAIL_IMAP_PORT`, `EMAIL_IMAP_USERNAME`, `EMAIL_IMAP_PASSWORD`, `EMAIL_IMAP_FOLDER`, `EMAIL_BOUNCE_CHECK_SECONDS` | Bounce reports read over IMAP and shown as "Não entregue" in the admin area; empty host disables it; credentials default to SMTP |
| `EMAIL_MAX_ATTEMPTS`, `EMAIL_RETRY_BASE_SECONDS`, `EMAIL_PROCESSING_TIMEOUT_SECONDS`, `EMAIL_WORKER_INTERVAL_SECONDS`, `EMAIL_MAX_SENDS_PER_HOUR` | Outbox retry, worker polling, per-address send cap |
| `PASSWORD_RESET_MINUTES` | Reset link lifetime |
| `GRANT_MAX_MINUTES`, `LINK_VIEW_MINUTES`, `LINK_PIN_MAX_FAILURES`, `HISTORY_WINDOW` | Ephemeral access caps: max lifetime (7 days), link viewing session, PIN lockout, history window |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` | Web Push keys (`python manage.py generate_vapid`); empty disables push |
| `OWNER_SESSION_MINUTES`, `CONSULT_PAIR_MINUTES`, `CONSULT_ACCESS_MINUTES`, `ENROLLMENT_MINUTES`, `INVITATION_HOURS`, `PDF_MAX_MB`, `EXAM_PAGE_SIZE` | Product limits (the SPA reads them from `GET /api/session/`) |

## API

JSON envelope everywhere: `{"data": ..., "error": null}` or
`{"data": null, "error": {"code", "message", "fields?"}}` (codes in `exams/responses.py`).
State-changing calls need the `X-CSRFToken` header (token from `GET /api/session/`).

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/session/` | anyone | identity, CSRF token, vault namespace, limits |
| POST | `/api/auth/login/` | anyone | email + derived credential + TOTP; returns the password-sealed vault key |
| POST | `/api/auth/logout/` | anyone | end session |
| POST | `/api/auth/vault/verify/` | owner | check password, return the sealed vault key (new tab) |
| POST | `/api/auth/password-reset/` | anyone | queue reset email (always 202, no enumeration) |
| POST | `/api/auth/password-reset/inspect/`, `/confirm/` | reset link holder | email + recovery copy; confirm with TOTP + recovery proof or fresh vault |
| POST | `/api/consents/` | owner | accept the current Terms + Privacy version (`LEGAL_VERSION`) |
| POST | `/api/access-requests/` | anyone | "Solicitar conta": emails the team inbox (`CONTACT_EMAIL`), requester as Reply-To; rate-limited, honeypot |
| POST | `/api/invitations/` | staff | email an invitation bound to that address (`admin: true` for an admin account) |
| GET | `/api/admin/invitations/`, `/api/admin/access-requests/`, `/api/admin/users/` | staff | admin area lists (`?page=`, 50 per page) |
| PATCH | `/api/admin/users/<id>/` | staff | grant or remove the admin role (never your own) |
| POST | `/api/invitations/bootstrap/` | installation code | email the first (staff) invitation |
| POST | `/api/invitations/inspect/` | invite link holder | email bound to the invitation |
| POST | `/api/enrollment/`, `/api/enrollment/confirm/` | invite link holder | sign-up (sealed vault copies), TOTP confirmation |
| GET, POST | `/api/documents/` | owner | list (`?page=`), upload ciphertext + sealed metadata |
| GET, DELETE | `/api/documents/<id>/` | owner | sealed metadata / delete for good (grants left empty end) |
| GET | `/api/documents/<id>/content/` | owner | ciphertext + `X-Document-Key` |
| GET | `/api/grants/` | owner | pending, active and recent permissions |
| GET | `/api/grants/pending/` | owner | `@` requests waiting (polled by the app shell for the badge/banner) |
| POST | `/api/grants/in-person/`, `/api/grants/<id>/approve/` | owner | approve a QR pairing / an `@` request |
| POST | `/api/grants/links/` | owner | create a remote link |
| POST, DELETE | `/api/grants/<id>/extend/`, `/api/grants/<id>/` | owner | extend / end (idempotent) |
| GET | `/api/pairings/<code>/key/` | owner | reader public key for a pending QR pairing |
| GET, PUT | `/api/profile/`, POST/DELETE `/api/profile/push/`, GET `/api/history/` | owner | `@handle`, push, "quem viu" chain |
| GET, POST | `/api/reader/` (+ `status/`, `documents/<id>/content/`) | reader browser | in-person / `@` request and reading |
| GET, POST | `/api/links/<id>/` (+ `open/`, `status/`, `documents/<doc>/content/`) | link holder | preview, PIN + open, reading |
| GET | `/healthz` | platform | DB round trip |

Every other path returns the SPA `index.html`. State-changing operations are written to the
`exams.audit` logger (who, what, from where; never secrets).

## Tests

```bash
conda activate positron
python manage.py test --noinput      # PostgreSQL: creates and drops test_positron_db
python manage.py makemigrations --check --dry-run

cd frontend
npm test            # Vitest: crypto round trips + vectors computed with Python
npm run typecheck   # tsc
npm run build       # production bundle (no inline scripts, CSP-compatible)
```

PostgreSQL is the only database, in development, tests and production (SQLite was removed:
it does not enforce column lengths and other constraints production relies on).

Browser (end-to-end) runs use a disposable database so each run starts empty:

```bash
python scripts/e2e_database.py reset     # (re)create positron_e2e, empty
PG_LOCAL_DATABASE=positron_e2e BACKEND_PORT=8031 EMAIL_ENABLED=false python start_server.py --build
python scripts/e2e_database.py drop      # remove it afterwards
```

The script can only create/drop `positron_e2e`; the test runner only creates/drops
`test_positron_db`. Neither touches `positron_db` or `agenda_db`.

## Database rules

- Local development uses only the **`positron_db`** database inside the shared container
  `agenda_ai_local_pg` (same container as the agenda_ai project). Never touch `agenda_db` or
  any other database in that container.
- Never run destructive commands against the Azure PostgreSQL. Develop locally, then sync
  new data to the remote.
- `python manage.py prune_access` removes expired grants, invitations and reset links (the
  history is kept);
  `flush_access --confirm-restore` invalidates sessions after a restore.

## Deploy

`docker build .` produces a single image (roles: `platform`, `web`, `mailer`, `migrate`): Node builds the SPA, the Python 3.11 runtime
serves API + SPA with Gunicorn on port 8000, runs migrations at start-up and starts the email
worker beside Gunicorn. Production requires `EMAIL_ENABLED=true`. Azure App
Service + PostgreSQL Flexible Server steps, the first-deploy status (Azure `positron_db` created and
seeded from local) and the settings generator: [docs/azure.md](docs/azure.md).

## Documentation Index

| Document | Content |
|---|---|
| [docs/crypto_assessment_2026-11-25.md](docs/crypto_assessment_2026-11-25.md) | Cryptography review, threat model, hardening roadmap, blockchain verdict |
| [docs/admin_area_2026-11-25.md](docs/admin_area_2026-11-25.md) | Admin area (account menu, top right): invitations with delivery status, access requests, admin role |
| [docs/privacy_lgpd_2026-11-25.md](docs/privacy_lgpd_2026-11-25.md) | Cookie notice (essential only), LGPD consent at sign-up and consent gate, privacy/terms pages, open legal items |
| [docs/mobile_pwa_2026-11-25.md](docs/mobile_pwa_2026-11-25.md) | Mobile layout (tab bar, card table, tap targets) and installable app on iPhone/Android (manifest, install flows, offline page) |
| [docs/ephemeral_access_2026-11-25.md](docs/ephemeral_access_2026-11-25.md) | Grants (in person, links, `@nome`), policy, sealed metadata, history chain, push |
| [docs/auth_email_recovery_2026-11-25.md](docs/auth_email_recovery_2026-11-25.md) | Email identity, invitations by email, password reset with recovery code, outbox |
| [docs/azure.md](docs/azure.md) | Azure App Service + PostgreSQL deployment (in Portuguese) |
