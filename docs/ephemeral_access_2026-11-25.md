# Ephemeral access (Pode Abrir): grants, links, personal address, history

Date: 2026-11-25
Status: implemented (migration `exams/0004_grants_documents`).
Roadmap: [FINISHED_ROADMAPS/ephemeral_access_podeabrir_roadmap_2026-11-25.md](FINISHED_ROADMAPS/ephemeral_access_podeabrir_roadmap_2026-11-25.md).

## Product rules

- Brand **Pode Abrir**, domain **podeabrir.com**. The platform is for any sensitive document;
  medical exams are the lead example.
- Every permission is short-lived, scoped to chosen documents, visible in "Compartilhamentos",
  extendable, and can be ended at any moment. Recipients never get a download (no control is
  offered); printing is blocked on reader pages; a watermark (channel/label + time) is tiled
  over every page; a countdown is always visible.
- Browsers cannot prevent screenshots; the product says so on the landing page.

## Data model

| Model | Purpose |
|---|---|
| `Document` (was `Exam`) | PDF ciphertext, vault-wrapped data key, **sealed title and issuer** (AES-GCM with the document's own data key, AAD `meta-title:<id>` / `meta-issuer:<id>`), plaintext date for ordering. |
| `Grant` | One permission: `channel` (`in_person`, `link`, `handle`), owner, reader browser digest (cookie), pairing code or nonce, ECDH keys, `label`, `pair_until`, `expires_at`, `max_opens`/`opens`, `pin_verifier`/`pin_failures`, `ended_at`/`end_reason`. Replaces `Consultation`/`SharedExam`. |
| `GrantDocument` | The data key re-sealed **in the owner's browser** for this grant only. Deleted when the grant ends. |
| `GrantEvent` | Append-only history, hash-chained per owner: `hash = SHA-256(prev_hash \| at \| channel \| kind \| grant \| document \| agent \| detail)`. Kept when grants are pruned. Browser family only, no IP. |
| `OwnerProfile` | Optional `@handle` (opt-in, `handle_active`). Also the per-owner lock for the event chain. |
| `PushSubscription` | Web Push endpoints of the owner's devices. |

## Channels

| Channel | Reader gets | Key transport | Confirmation |
|---|---|---|---|
| In person (`/ler/`) | QR + code on the reader screen; owner opens `/autorizar/#CODE.FP` | ECDH P-256, HKDF salt = pairing code | 64-bit key fingerprint in the QR, checked by the phone |
| Personal address (`/@nome`) | "Pedir acesso" creates a pending request; owner approves at `/autorizar/pedido/<id>` | ECDH P-256, HKDF salt = server nonce | 6-digit code = SHA-256(reader key \|\| server nonce), shown on both screens. The server-chosen nonce prevents grinding a key to match a code. Two pending requests with the same code are both blocked. |
| Remote link (`/s/<id>#<key>`) | Neutral page, PIN if required, explicit "Abrir" | Random 256-bit link key **only in the URL fragment**; data keys sealed with it (AAD `link:<id>`) | PIN verified by the server with lockout |

Unknown, paused or malformed `@handles` produce the same response as real ones (an ownerless
pending grant that simply expires), so the page never confirms that an address exists. Unknown,
ended and exhausted link ids look identical (`{"state": "unavailable"}`).

## Policy (server-enforced)

| Rule | Value |
|---|---|
| In-person / `@` lifetimes | 15 min, 45 min (default), 2 h, 8 h |
| Link lifetimes | 1 h, 24 h (default), 7 days |
| Extend | +15 min, +1 h, +24 h; never beyond now + `GRANT_MAX_MINUTES` (7 days) |
| Opens (links) | once (view once), 2–20, or unlimited; counted atomically on "Abrir" |
| PIN (links) | required for more than one document or more than 24 h; 4–8 digits; `LINK_PIN_MAX_FAILURES` (5) wrong attempts lock the link |
| Viewing session (links) | signed HttpOnly cookie, path-scoped to the link, lasts `LINK_VIEW_MINUTES` (30) or until expiry; revocation and expiry are checked on every content request |
| Pending requests | `CONSULT_PAIR_MINUTES` (5); rate limits per handle and globally |

Link previews (WhatsApp, Slack, mail scanners) only fetch the HTML: content is released by a
POST after the click, so they cannot consume a view.

## API

| Method | Path | Who |
|---|---|---|
| GET | `/api/grants/` | owner: active, pending and recent (7 days) grants |
| GET | `/api/grants/pending/` | owner: waiting `@handle` requests (app-shell poll: nav badge, banner, tab title) |
| DELETE | `/api/documents/<id>/` | owner: delete a document; grants left without documents end (`documento excluído` in the history) |
| POST | `/api/grants/in-person/` | owner: approve a QR pairing `{code, documents, share_keys, sender_key, minutes}` |
| POST | `/api/grants/<id>/approve/` | owner: approve a `@handle` request |
| POST | `/api/grants/links/` | owner: create a link `{documents, share_keys, minutes, max_opens, pin, label}` |
| POST | `/api/grants/<id>/extend/` | owner `{minutes}` |
| DELETE | `/api/grants/<id>/` | owner: end (idempotent, 204) |
| GET | `/api/history/` | owner: last `HISTORY_WINDOW` events, oldest first |
| GET, PUT | `/api/profile/` | owner: `@handle`, active flag, address QR, push public key |
| POST, DELETE | `/api/profile/push/` | owner: push subscription |
| GET, POST | `/api/reader/` | reader browser: state / request (in person, or `{handle}`) |
| GET | `/api/reader/status/`, `/api/reader/documents/<id>/content/` | reader browser |
| GET | `/api/links/<id>/` | anyone: neutral preview |
| POST | `/api/links/<id>/open/` | link holder: PIN + open (counts) |
| GET | `/api/links/<id>/status/`, `/api/links/<id>/documents/<doc>/content/` | viewing session |

## History integrity

The "Quem viu" panel re-hashes the chain in the browser (WebCrypto SHA-256) and remembers the
newest `(id, hash)` in `localStorage`. It reports "íntegro", "o histórico mudou desde a sua última
visita" (a remembered link changed or disappeared) or "o encadeamento não confere". This detects
edits and deletions after the fact; it does not stop an attacker who controls the server from
rewriting history before the owner's first view (external anchoring is listed in the open roadmap).

## Notifications

Delivery requires (a) an **active** personal address (unknown or paused addresses are silent by
design, and Conta warns while the address is off) and, for push, (b) "Ativar neste dispositivo" in
Conta on each browser/phone. Desktop Chrome, Edge and Firefox receive push as well as phones. While
the app is open, every owner page also shows a banner, a badge on "Compartilhamentos" and the
count in the tab title, independent of push.

- Email (outbox): "Pedido de leitura" for `@handle` requests, at most one per owner per 5 minutes.
- Web Push (installable PWA, `public/sw.js` with no fetch handler and no cache): pending request
  and "link aberto". Payload encrypted per RFC 8291 (`http_ece`), signed with VAPID (`py-vapid`),
  sent with the standard library. Texts are generic: never document titles or recipient labels.
  Keys: `python manage.py generate_vapid` -> `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`.

## Verification (2026-11-25)

- Django tests (20): in-person grant isolation, revocation, expiry and policy; extension cap;
  `@handle` request/approval, unknown and paused handles indistinguishable, duplicate handle;
  link PIN policy, view once, revocation of an open session, PIN lockout, unknown link ids;
  history chain valid and tamper-detected; push delivery and removal of gone subscriptions;
  plus enrollment, reset, outbox and session tests.
- Vitest (12): Python cross-check vectors (credentials, fingerprint, **comparison code**),
  sealed metadata bound to purpose/id, recovery and vault re-sealing.
- Browser end-to-end on a production-like build with the real CSP (no console errors): sign-up,
  two uploads with local search, in-person read with watermark, extend and end; view-once link
  (second recipient refused); PIN link (wrong PIN refused, right PIN opens); `@nome` request with
  the same 6-digit code on both screens, approval and reading; unknown `@` address identical;
  history verified in the browser.
- Web Push: real `send_one` against a local endpoint; payload decrypted with the subscriber keys.
  Delivery through Google/Mozilla/Apple push services was not tested from this environment.
