# Email identity, invitations by email and password reset with recovery code

Date: 2026-11-25
Status: implemented, migration `exams/0003_email_identity_recovery`.
Reused from agenda_ai (without modifying it): SMTP sender, durable outbox with bounded retry,
digest-only single-use tokens issued at render time, pt-BR email templates (rebranded).

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Identity | The account identity is the email (normalized lowercase, max 150). | Needed to send reset links. It also salts the browser key derivation, so **email changes are not supported** in v0. |
| Email proof | Sign-up only through an invitation emailed to that address; the account is bound to it. | A typo or someone else's address can never become the reset channel. |
| First account | The installation code (`BOOTSTRAP_INVITE_DIGEST`) only requests an invitation to the given email; that invitation grants staff. | Same proof-of-email path for everyone. Valid until one account exists. |
| Reset vs E2EE | Vault key is random and sealed twice in the browser: by the password key and by a recovery code shown once at sign-up. | An email link alone can never reveal reports; the server still cannot read them. |
| Lost recovery code | Reset can create a fresh empty vault; old reports (undecryptable) are deleted after explicit confirmation. | Account access is recoverable, data honestly is not. |

## Key hierarchy (v2)

```
password -> PBKDF2-SHA-256 600k -> HKDF -> authentication credential (server stores Django hash)
                                        -> password key  --seals--> vault key copy #1 (AAD vault-password:<email>)
recovery code (160-bit, base32 XXXX-...) -> HKDF -> recovery proof (server stores Django hash)
                                                 -> recovery key --seals--> vault key copy #2 (AAD vault-recovery:<email>)
vault key (random 256-bit, browser only) --seals--> per-exam data keys --> PDFs (unchanged)
```

`AccountVault` stores both sealed copies and the recovery verifier. Login and the new-tab
unlock return copy #1; the reset link page returns copy #2.

## Flows

1. **First access** (`/cadastro/` without a link): installation code + email ->
   `POST /api/invitations/bootstrap/` -> invitation email.
2. **Invite** (staff, `/convites/`): email -> `POST /api/invitations/` (202, optimistic UI).
3. **Sign-up** (`/cadastro/#token`): `POST /api/invitations/inspect/` shows the bound email;
   password + confirmation; the browser creates vault key, recovery code and both sealed copies;
   `POST /api/enrollment/`; step 2 shows the recovery code (copy / download, "I saved it"
   required), the TOTP QR, then `POST /api/enrollment/confirm/`.
4. **Forgot password** (`/esqueci-senha/`): `POST /api/auth/password-reset/` always answers 202
   with the same message (no account enumeration). Per-address cap `EMAIL_MAX_SENDS_PER_HOUR`.
5. **Reset** (`/redefinir-senha/#token`, valid `PASSWORD_RESET_MINUTES`):
   `POST /api/auth/password-reset/inspect/` returns email + copy #2. Requires a TOTP code and:
   - **recovery code**: the browser opens copy #2, re-seals the same vault key with the new
     password, sends the recovery proof; reports are preserved;
   - **"Perdi meu código"**: explicit confirmation; new vault + new recovery code; the server
     deletes the user's documents and ends every open grant (updated 2026-11-25 for the grant model).
   `POST /api/auth/password-reset/confirm/` consumes the link, changes the password hash (which
   invalidates every session) and queues a "password changed" email.

## Email delivery

- `manage.py send_emails` drains `EmailDelivery` (started by `start_server.py`, and beside
  Gunicorn in the container). Retries with exponential backoff up to `EMAIL_MAX_ATTEMPTS`;
  stale `processing` rows are recovered after `EMAIL_PROCESSING_TIMEOUT_SECONDS`.
- Tokens are created when the message is rendered, inside the same transaction as the send:
  a failed send issues no token and does not supersede the previous link.
- Links carry tokens in the URL fragment (`#token`), so they never reach server logs.
- `EMAIL_ENABLED=false` (development only) prints messages and links in the `[mailer]` console.
  Production refuses to start without email.
- GoDaddy SMTP with the `@podeabrir.com` mailbox; the sender is `auth@podeabrir.com`. SPF, DKIM
  and DMARC still have to be confirmed before launch (see
  ROADMAPS/podeabrir_launch_followups_roadmap_2026-11-25.md).
- The wordmark travels inside each message (`cid:` inline PNG from `exams/email_assets/logo.png`),
  so it shows whatever server sent it and without loading remote images.
- Every message carries `X-PodeAbrir-Ref: <delivery id>`, which bounce reports quote back.

### Undeliverable addresses (2026-11-25)

- **Domain check, at invite time** (`mail_domains.py`, dnspython): the recipient domain must have
  an MX record (or an A/AAAA record, the implicit MX) and must not publish a null MX (RFC 7505).
  A clear "no" refuses the invitation with `email_domain_undeliverable`; DNS trouble never blocks
  it. Skipped when `EMAIL_ENABLED=false`, since nothing is sent then. It cannot detect a missing
  mailbox at a real domain.
- **Bounce reports, after sending** (`bounces.py`): GoDaddy accepts almost any recipient and
  mails a delivery status notification (RFC 3464) to the sender later. Every
  `EMAIL_BOUNCE_CHECK_SECONDS` the mail worker logs into `EMAIL_IMAP_HOST` (credentials default to
  the SMTP ones), searches only unread messages from the last 7 days whose `Content-Type`
  mentions `delivery-status`, reads them with `BODY.PEEK` and keeps permanent failures
  (`Action: failed`, `Status: 5.x.x`). The delivery is found by the quoted reference, else by the
  latest sent delivery to that address, and marked `bounced` with the status code. Only recognised
  reports are flagged as read; other mail in that mailbox is never downloaded or changed, and
  nothing from the messages is logged. A failure here is logged and retried; it never stops the
  outbox.
- The admin area shows `bounced` as "Não entregue" with the reason (address does not exist,
  mailbox full or disabled, refused) and no resend button.
- Anyone can mail a fake report to the sender address; the worst case is a delivery wrongly shown
  as "Não entregue" (no access or data is affected), and the reference must match the recipient.
- Verified 2026-11-25: IMAP login and the search work against the real mailbox (read-only check,
  0 reports in the last 7 days). Where bounces for `auth@podeabrir.com` actually land (that mailbox
  or a separate one) has not been confirmed with a real bounce yet; if it is a separate mailbox, set
  `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD`.

## Verification (2026-11-25)

- Django tests (15): bootstrap invite by email -> staff, staff invite single use, non-email
  rejected, reset unknown email silent, reset with recovery code keeps reports and ends sessions,
  wrong recovery code rejected, lost-code reset deletes reports, outbox retry/failure without
  issuing tokens, duplicate pending deliveries reused.
- Vitest (9): Python cross-check vectors, recovery code parsing, both sealed copies open the same
  vault, re-seal after reset rejects the old password.
- Browser end-to-end (production-like build, console email): first access -> emailed invite ->
  sign-up with recovery code -> upload -> staff invite -> reset with recovery code -> login with
  the new password decrypts the old report -> lost-code reset -> empty vault, new code.
- SMTP: login to the GoDaddy mailbox verified; no real message was sent during automated tests.

## Not included (v0)

Email change, password change while logged in, recovery-code rotation, TOTP recovery (a lost
authenticator still blocks login and reset).
