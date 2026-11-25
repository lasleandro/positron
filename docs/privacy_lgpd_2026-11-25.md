# Privacy, cookies and LGPD consent

Date: 2026-11-25. Legal texts are drafts: company fields in brackets must be completed and the
texts reviewed by legal counsel before launch.

## Decisions

| Topic | Decision | Why |
|---|---|---|
| Cookie banner | **Informative notice** ("Entendi" + link), no accept/reject | Only strictly necessary cookies exist (session, CSRF, reader session, link session); no analytics, ads or third parties. An opt-in banner would imply choices that do not exist. |
| Legal basis | Contract (art. 7º, V) for the service; **specific, highlighted consent** for sensitive data such as health exams (art. 11, I); legitimate interest / fraud prevention for security (arts. 7º, IX, 11, II, "g"); legal obligation for access logs (Marco Civil, art. 15) | Documents are encrypted and unreadable to the server, but storing them is still processing of possibly sensitive data. |
| Consent record | `ConsentRecord(user, version, accepted_at)`, unique per version; created at sign-up (required checkbox) | Proof of consent (art. 8º, § 1º, burden on the controller). |
| Policy updates | `LEGAL_VERSION` (env). Owners without a record for the current version see a **consent gate** in place of the app; the legal pages stay readable | New acceptance on material changes; also covers accounts created before this feature. |
| Rights (art. 18) | Request by e-mail to the contact/DPO address, answer within 15 days; self-service delete of documents and grants | Self-service account deletion and data export are not built yet (see below). |

## Pages and API

- `/privacidade` (Política de Privacidade, with the cookie table at `#cookies`) and `/termos` (Termos de Uso), linked in the footer, the sign-up consent, the consent gate and Conta.
- `POST /api/consents/ {accept: true, version}`: records acceptance of the current version (owner only). `GET /api/session/` returns `legal_version` and `user.consent_ok`.
- Sign-up (`POST /api/enrollment/`) requires `consent: true`.

## Operational obligations implied by the texts

- **Access logs for 6 months** (Marco Civil, art. 15): configure App Service log retention accordingly (the `exams.audit` log lines carry date, action and IP).
- **Fill the bracketed fields**: legal name, CNPJ, address, DPO name, Azure region, retention period for access requests, court district.
- **Answer rights requests** sent to the contact address within 15 days.

## Not done (recommended next)

- Self-service account deletion and data export (portability) in Conta.
- Automatic pruning of old access requests once a retention period is decided.

## Verification

Django tests: sign-up refused without consent; consent recorded with the current version;
account without a record has `consent_ok=false`; stale version refused; version bump requires a
new acceptance. Browser: cookie notice shown, dismissed and remembered; legal pages render;
sign-up blocked without the checkbox; deleting the consent record shows the gate in place of the
app, policy readable from it, acceptance restores access; on phones the notice sits above the tab
bar and the install banner waits for it.
