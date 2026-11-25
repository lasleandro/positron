# Roadmap: ephemeral access and podeabrir.com (Pode Abrir)

Date: 2026-11-25
Status: **finished 2026-11-25** (software). External actions and deferred items moved to
[ROADMAPS/podeabrir_launch_followups_roadmap_2026-11-25.md](../ROADMAPS/podeabrir_launch_followups_roadmap_2026-11-25.md).
Implementation record: [ephemeral_access_2026-11-25.md](../ephemeral_access_2026-11-25.md).

| Phase | Status |
|---|---|
| 0 Domain and entry points | Done in code: brand "Pode Abrir", new landing page (security, privacy, ease of use, use cases), "Ler documentos" in header and hero, broader "documentos" wording, sender name. **External**: Azure custom domain/certificate and `@podeabrir.com` mail (steps in `docs/azure.md` §5; development keeps tennisos). |
| 1 Unified Grant model | Done: `Grant`/`GrantDocument`/`GrantEvent`, policy enforcement, "Compartilhamentos" with Estender/Encerrar (optimistic) and "Quem viu". |
| 2 Remote share links | Done: fragment key, lifetimes, view once / N opens, PIN with lockout, neutral recipient page, countdown, watermark, no download, live opens. |
| 3 Personal address `/@nome` | Done: opt-in handle, indistinguishable unknown/paused addresses, server-nonce comparison code, duplicate-code block, email notification, printable QR card. |
| 4 Installable app and push | Done: manifest, icons, cache-free service worker, Web Push (RFC 8291 + VAPID). Not tested against real push services from this environment. |
| 5 Trust layer | Done: hash-chained history verified in the browser; encrypted metadata (title, issuer). **Deferred**: external anchoring of the chain, verified professionals (needs a CRM data provider). |
Domain: **podeabrir.com** (owned).

## 1. Goal

Make short-lived permission the core of the product: the patient decides **who** can open
**which** documents, **for how long** and **how many times**, and can end it at any moment, like
a Snapchat for medical documents. That covers two situations:

- **In person**: the doctor's screen asks for access and the patient approves on the phone. This
  exists today as `/consultorio/` (QR + 45 min).
- **Remote**: the patient sends a link that opens selected documents for a limited time or
  number of views, over WhatsApp, email or anything else.

Both must keep the current guarantee: documents are decrypted only in the browser that received
the permission; the server never holds a usable key.

## 2. Assessment of the proposal

| Idea | Verdict | Adjustment |
|---|---|---|
| "Ler documentos" button on the landing page that shows the QR | Yes, quick win | It is today's `/consultorio/` under a clearer name. Put it as a primary button in the header and hero. |
| Personal address `podeabrir.com/joao` | Yes, with care | (a) It must **never reveal anything** about João (no name, no exam count) and must **not** make it possible to discover who uses the platform. (b) Opening it creates an access **request** that João approves on his phone, confirming a short code shown on both screens, so nobody can trick him into approving another browser. (c) Personal names collide with app routes (`/exames`, `/entrar`, ...); a reserved-words list or the `/@joao` form solves it. |
| Remote short-lived sharing | Yes, the biggest new value | Implement as an end-to-end-encrypted link whose key is in the URL fragment (`#...`, never sent to the server), the model used by Bitwarden Send and Firefox Send. Policies: expiry, max opens, view once, optional PIN, revocation. |

### Suggested improvements

1. **One permission model, several channels.** Today `Consultation` + `SharedExam` model only the
   in-person flow. Generalize to a `Grant` (documents + recipient key + policy + channel). The
   QR, the personal address and remote links become channels of the same thing, with the same
   list, the same "Encerrar" button and the same history.
2. **Short defaults, easy extension.** Default to short lifetimes (in person 45 min, link 24 h,
   cap 7 days) with an "Estender" action, instead of long permissions that people forget.
3. **"Quem viu" history** for the patient: every open is recorded (time, channel, browser family),
   shown in the app and later hash-chained (crypto assessment, item 7). This is what builds trust
   and is the honest version of the "Snapchat" promise.
4. **Deterrents, not false promises.** Browsers cannot block screenshots. Instead: a visible
   countdown, a watermark with recipient and time over every page, no download button, printing
   blocked, and the page closes when the permission ends. Communicate it plainly.
5. **Brand and email on the new domain.** Sending from `@podeabrir.com` with SPF/DKIM/DMARC
   replaces the temporary tennisos mailbox before production.

## 3. Target model

```
Grant
  owner, channel (in_person | link | handle_request), state (pending | active | ended)
  policy: expires_at, max_opens, view_once, pin_required
  recipient_key (public ECDH key, or none for links)    created_at, ended_at, end_reason
  └─ GrantDocument: exam, wrapped_key (data key re-sealed for this grant only)
  └─ GrantEvent: opened | denied | extended | ended, at, browser family (no IP stored)
```

Cryptography per channel (the vault key never leaves the owner's browser in any of them):

| Channel | How the recipient gets the data keys |
|---|---|
| In person (today) | ECDH between office browser and phone, code + fingerprint confirmation. Unchanged. |
| Personal address | Same as in person: the request carries the reader browser's public key; the phone shows a 6-digit comparison code (derived from both keys) that must match the reader screen before approval. |
| Remote link | The phone generates a random 256-bit link key, re-seals the chosen data keys with it and puts it **only in the fragment** `podeabrir.com/s/<id>#<key>`. Optional PIN: link key = HKDF(random part, PBKDF2(PIN)), so a leaked link alone is not enough. |

Server-side enforcement on every content request: grant active, not expired, opens below the
limit (counted atomically), PIN attempts rate-limited. "View once" deletes the wrapped keys on
the first successful open. Content is fetched only after an explicit "Abrir" click, so
link-preview bots (WhatsApp, Slack, email scanners) cannot consume a view.

## 4. Phases

Each phase is shippable on its own. The order puts remote links before the personal address,
because links are independent and need no notification infrastructure.

### Phase 0: domain and entry points (S)

- `podeabrir.com` on Azure App Service: custom domain, managed certificate, `APP_ORIGIN`,
  HSTS. Redirect `www`.
- Sending domain `@podeabrir.com` (SPF, DKIM, DMARC); swap the tennisos mailbox **when the domain mail is configured** (development keeps tennisos, decision 6).
- "Ler documentos" in the header and hero of the landing page (= current `/consultorio/`, which
  keeps working).
- Decide the brand (section 5) and update copy, page title, emails and favicon.
- Done when: production at `https://podeabrir.com`, invite/reset emails from the new domain
  pass SPF/DKIM, landing page leads to the QR in one click.

### Phase 1: unified Grant model (M)

- New `Grant`, `GrantDocument`, `GrantEvent`; migrate the in-person flow onto them (data
  migration from `Consultation`/`SharedExam`; no behavior change for the user).
- Policy fields and server enforcement (expiry, max opens, view once).
- "Acessos" page becomes "Compartilhamentos": active and recent grants, by channel, with
  Encerrar / Estender (optimistic UI, rollback on failure) and the "Quem viu" event list.
- Done when: the existing E2E flow passes unchanged; new tests for expiry, max opens and
  view once; history shows every open.

### Phase 2: remote share links (M)

- Owner: choose documents, lifetime (1 h / 24 h / 7 d, capped), max opens or view once,
  optional PIN; get a link and native share sheet (`navigator.share`) / copy.
- Recipient page `/s/<id>`: neutral landing ("Alguém compartilhou documentos com você"),
  explicit "Abrir", PIN if required, reader with countdown and watermark, closes on expiry or
  revocation (same polling as today).
- Owner sees opens in real time and can end the link.
- Done when: links work in WhatsApp/email without preview bots consuming views; PIN
  brute force blocked; E2E covering expiry, view once, revocation and wrong PIN.

### Phase 3: personal address podeabrir.com/@nome (M)

- Owner claims an address `/@nome` (opt-in, editable, with suggestions that do not reveal the real
  name).
- Visiting the address shows the standard reader page and creates a pending request to that
  owner; the page never confirms whether the address exists (same page and timing for unknown
  addresses).
- Owner approves in the app: sees the comparison code, picks documents and lifetime.
  Notification by email in this phase, plus in-app list of pending requests.
- Abuse controls: requests expire in 5 minutes, per-address and per-IP rate limits, the owner
  can pause the address.
- Optional: printable card / sticker with the QR of the address (for the clinic counter).
- Done when: request -> approval -> reading works without scanning; unknown and paused
  addresses are indistinguishable from active ones; abuse limits tested.

### Phase 4: installable app and push (M)

- PWA (manifest, service worker for the shell only, never caching documents) and Web Push, so
  requests and "alguém abriu seu documento" arrive instantly. iOS requires the app to be
  installed on the home screen (iOS 16.4+).
- Done when: pending request notification arrives in seconds on Android and installed iOS.

### Phase 5: trust layer (L, can run in parallel)

- Hash-chained "Quem viu" log, optionally anchored (crypto assessment, item 7).
- Encrypted metadata (crypto assessment, item 1); becomes more important once documents travel
  over the internet.
- Verified professionals (optional): a doctor identity checked against CRM, shown to the patient
  when approving.

## 5. Decisions (recorded 2026-11-25)

| # | Question | Decision |
|---|---|---|
| 1 | Brand | **Rename to "Pode Abrir".** Landing page focused on security, privacy and ease of use, with use cases. Medical exams are the lead example, but the platform is for any sensitive document: the UI says "documentos", not "exames". Crypto domain strings (`meus-exames:v1:`) stay internal and unchanged. |
| 2 | Personal address format | **`podeabrir.com/@nome`.** No collision with app routes. |
| 3 | Personal address default | **Off (opt-in).** |
| 4 | PIN on remote links | **On by default for 7-day or multi-document links**, optional for short single-document links. |
| 5 | Download by recipients | **Never by default.** No download control is offered to recipients. |
| 6 | Development email | **Keep the tennisos mailbox** until `@podeabrir.com` mail is configured; only the sender name changes to "Pode Abrir". |

## 6. Risks and limits to communicate

- **Screenshots and photos of the screen cannot be prevented** by any web app; the product
  deters (watermark, countdown, history) and says so.
- **Whoever holds a remote link can open it** while it is valid: PIN, view once and short
  lifetimes reduce the window; the owner sees every open.
- **LGPD**: document access history is personal data about both patient and recipient: keep it
  minimal (no IP, browser family only), give the patient deletion of their history, document
  retention.
- **Web Push on iOS** only works for installed PWAs; email stays as the fallback.

## 7. Size estimate

S = up to 2 days, M = about a week, L = several weeks, for one developer with tests and docs.
Phases 0-2 (domain, unified grants, remote links) deliver the "Snapchat for documents"
experience; Phase 3 adds the personal address on top of the same model.
