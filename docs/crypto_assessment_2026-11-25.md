# Cryptography assessment and the blockchain question

Date: 2026-11-25
Scope: the client-side encryption of exams (PDF reports) in Positron / Meus Exames, the
"decrypted only in the frontend" selling point, and whether a blockchain adds value.
Evidence: code in `frontend/src/lib/crypto.ts`, `exams/crypto_format.py`, `exams/sharing.py`,
`exams/consultation.py`; cross-language test vectors in `frontend/src/lib/crypto.test.ts`;
a browser end-to-end run of enroll -> upload -> view -> share -> revoke on 2026-11-25.

## 1. Verdict

- **The core design is sound and already delivers the selling point.** PDFs are encrypted in
  the browser before upload, the server stores only ciphertext and wrapped keys, and each
  viewer (owner or doctor's browser) decrypts locally with WebCrypto. A full database or
  backup leak does not expose report contents.
- **Blockchain is not worth it for this product.** It does nothing for confidentiality (the
  property that matters for health data), conflicts with LGPD erasure duties, and adds cost,
  latency and operational risk. The "fancy" features people associate with blockchain
  (tamper evidence, verifiability, public auditability) are achievable with cheaper,
  standard tools: an append-only hash-chained audit log, optional timestamp anchoring, and a
  transparency log for frontend releases. Section 5 details this.
- **The real weak point is not storage, it is trust in the JavaScript served to the browser**
  and the plaintext metadata. Fixing those is what makes the "only your browser can read it"
  claim robust enough to market. Section 4 lists the work, in priority order.

## 2. What the platform does today

### 2.1 Key hierarchy

> Updated 2026-11-25 (same day): the identity is now the email and the vault key is random,
> sealed by both the password and a recovery code, to support email password reset without
> giving the server access. See [auth_email_recovery_2026-11-25.md](auth_email_recovery_2026-11-25.md).

```
password (typed, never sent)
  └─ PBKDF2-SHA-256, 600k iterations, salt = "meus-exames:v1:" + VAULT_NAMESPACE + ":" + email
       └─ HKDF-SHA-256
            ├─ info "authentication" -> 32-byte credential sent to the server
            │                           (stored as a Django PBKDF2 hash; login also needs TOTP)
            └─ info "vault"          -> password key: seals vault copy #1 (AAD "vault-password:<email>")
recovery code (160-bit random, shown once at sign-up)
  └─ HKDF-SHA-256 -> recovery proof (server keeps a hash) + recovery key: seals vault copy #2
vault key (random 32 bytes, generated and opened only in the browser)
  └─ wraps, per document: random 32-byte data key   (AAD "owner:<id>")
       ├─ encrypts the PDF with AES-256-GCM          (AAD "pdf:<id>")
       └─ seals title / issuer                        (AAD "meta-title:<id>", "meta-issuer:<id>")
```

> Updated 2026-11-25: sharing now uses a unified grant model with three channels (in person,
> remote link, `@nome`). Remote links carry a random 256-bit link key **only in the URL fragment**
> and re-seal the chosen data keys with it (AAD `"link:<id>"`); `@nome` requests use ECDH plus a
> 6-digit comparison code bound to a server nonce. See
> [ephemeral_access_2026-11-25.md](ephemeral_access_2026-11-25.md).

Envelope for every sealed blob: `0x01 | 12-byte IV | ciphertext + 16-byte tag`. The server
validates only the shape (`exams/crypto_format.py`), never the content.

### 2.2 Sharing with the doctor's browser (no doctor account)

1. The office browser generates an ephemeral ECDH P-256 key pair and posts the public key.
   The server returns a short pairing code plus a 64-bit fingerprint of that public key
   (`CODE.fingerprint`), shown as text and QR.
2. The patient's phone fetches the office public key, **recomputes the fingerprint locally
   and refuses to continue on mismatch**. This blocks a server-side key substitution
   (machine-in-the-middle) for the pairing step.
3. The phone generates its own ephemeral pair, derives `HKDF(ECDH, salt = code)` and re-wraps
   only the chosen data keys for that office browser (AAD `"recipient:<exam id>"`).
4. The office browser derives the same key and decrypts in memory. Revocation deletes the
   recipient-wrapped keys, the backend stops serving ciphertext, and the open reader closes
   within ~1.5 s through status polling.

### 2.3 Server-side protections around the crypto

- Login: derived credential + TOTP (Fernet-encrypted secret, replay-protected step counter),
  per-user and global rate limits.
- Strict CSP (`default-src 'none'; script-src 'self' 'wasm-unsafe-eval'`, no inline script),
  `no-store` caching, `frame-ancestors 'none'`, HttpOnly cookies (`__Host-` in production).
- Consultation access bound to an HttpOnly, SameSite=Strict cookie, checked on every PDF fetch.

### 2.4 Verified on 2026-11-25

- `frontend/src/lib/crypto.test.ts`: the TypeScript port reproduces credential and fingerprint
  values computed independently with Python `hashlib`/`cryptography`, wrapped keys have the
  61-byte size the backend enforces, and tampered AAD or a wrong pairing code fails decryption.
- Browser end-to-end run (production-like build, real CSP): enroll, encrypted upload, owner
  decrypt, vault unlock in a fresh tab, pairing, ECDH share, office decrypt, revocation.

## 3. What "decrypted only in the frontend" really guarantees

The claim is true **at rest and in transit through our backend**. It is conditional against an
attacker who controls the code the browser runs. Marketing must stay inside this table.

| Attacker / event | Can read PDF contents? | Why |
|---|---|---|
| Database dump, backup leak, Azure storage snapshot | No | Only AES-GCM ciphertext and wrapped keys are stored. |
| Curious DBA / cloud operator reading rows | No (contents, titles, issuers); **yes (dates, sharing patterns)** | Since 2026-11-25 titles and issuers are sealed; the document date and grant metadata (when, how long, how many opens) stay readable. |
| Someone who intercepts a remote link | Only while it is valid, and only with the PIN when one is set | The key is in the fragment; the server enforces lifetime, opens and PIN lockout; the owner sees every open. |
| Network observer | No | TLS, plus the payload is already ciphertext. |
| Someone who stole a password hash | Offline guessing only | 600k-iteration PBKDF2 slows it; weak passwords still fall. |
| Someone who controls the user's mailbox | No | A reset link also needs the TOTP code, and keeping the reports needs the recovery code; without it the reset creates an empty vault. |
| Doctor's browser after revocation | Only what it already rendered | Revocation stops new fetches; screenshots/copies are out of reach. |
| **Compromised server that serves modified JavaScript** | **Yes** | It can ship code that exfiltrates the password or plaintext. This is the gap every web E2EE product shares. |
| XSS in the SPA | Yes (vault key in `sessionStorage`) | The raw vault key and the office private key (JWK) are readable by any script in the origin. |
| Compromised patient or office device | Yes | Out of scope for any cryptography. |

Two consequences matter for the product:

1. **Metadata is health data.** "Hemograma", "Laboratório X" and a date already reveal sensitive
   personal data under LGPD (art. 5, II). **Addressed 2026-11-25** for titles and issuers (sealed in
   the browser); dates remain readable for ordering.
2. **The server is still trusted to deliver honest code.** Users cannot tell whether the bundle
   they received is the audited one. Closing this gap is what turns the claim from "we promise"
   into "you can verify".

## 4. Recommended hardening (priority order)

| # | Change | Effort | What it buys |
|---|---|---|---|
| 1 | **Encrypt metadata client-side** (title, laboratory; keep only a coarse date or none). Search runs in the browser over the decrypted list. | Medium | **Done 2026-11-25** (title + issuer sealed with the document key; date kept for ordering). |
| 2 | **Non-extractable keys in memory/IndexedDB** instead of base64 keys in `sessionStorage`. Import the vault key and the office ECDH key with `extractable: false` and keep the `CryptoKey` objects (IndexedDB can store them). | Small | XSS can no longer copy the raw key out; it can only use it while the tab lives. |
| 3 | **Verifiable frontend releases**: reproducible Vite build, publish the SHA-256 of every release asset to a public transparency log (Sigstore/Rekor) and in the repo, Subresource Integrity on the entry script, and a "verify this build" page or browser extension that compares hashes. Optionally ship an installable PWA so the code is pinned between updates. | Medium | Turns "trust our server" into "anyone can check the code you run". This is the honest version of the "blockchain-style" pitch. |
| 4 | **Passkeys with the WebAuthn PRF extension** to derive or unwrap the vault key, keeping the password as recovery only. | Medium | Phishing-resistant login and a hardware-backed vault key; removes offline password guessing. |
| 5 | **Recovery key and password change**: generate a random recovery key at enrollment (printed / saved), wrap the vault key with both password-derived and recovery keys. Password change re-wraps only the vault key, not every PDF. | Small | **Done 2026-11-25** for email reset ([details](auth_email_recovery_2026-11-25.md)). Still open: password change while logged in, recovery-code rotation. |
| 6 | **Argon2id** (WASM, already allowed by `'wasm-unsafe-eval'`) instead of PBKDF2 for new accounts, versioned via the `v1` prefix. | Small | Memory-hard; much more expensive to brute force on GPUs. |
| 7 | **Tamper-evident audit log**: hash-chain each grant/revoke/upload event (`h_n = SHA-256(h_{n-1} || event)`), show the patient their own access history, optionally anchor the daily head hash with OpenTimestamps. | Small | **Done 2026-11-25** for grant events ("Quem viu", verified in the browser, last head remembered locally). External anchoring still open. |
| 8 | Longer pairing confirmation (e.g. 96-128-bit fingerprint, or a short authentication string compared visually) if pairing windows ever grow beyond minutes. | Small | Current 64 bits is adequate for a 5-minute, rate-limited window. |

Items 1-3 are the ones that make "only your browser can read your exams" defensible in a
security review or a hospital procurement questionnaire.

## 5. Is blockchain worth it?

### 5.1 What a blockchain would and would not do here

| Goal | Does a blockchain help? | Better tool |
|---|---|---|
| Keep reports confidential | **No.** Public ledgers are the opposite of confidential; anything written there is permanent and replicated worldwide. | The current client-side encryption (plus section 4). |
| Store the PDFs or keys | **No.** Cost, size limits, and permanent exposure if a key or algorithm ever breaks ("harvest now, decrypt later"). | PostgreSQL / Azure Blob with client-side encryption. |
| Store hashes of exams | Risky. A hash of a health document linked to a pseudonymous patient is still personal data under LGPD and cannot be erased. | Keep hashes in our own append-only log. |
| Consent / access grants as smart contracts | No real gain. Access is enforced by who holds the wrapped keys, not by a contract. Adds wallets, gas fees and latency to a 45-minute consultation flow. | Current ECDH grants + revocation. |
| Tamper-evident audit trail | Partly, but overkill. | Hash-chained audit log, optionally **anchored** via OpenTimestamps (Bitcoin-backed, free, no wallet, no personal data on chain). |
| Prove the frontend code was not altered | Partly, but overkill. | Sigstore/Rekor transparency log or Certificate-Transparency-style logs, built for exactly this. |
| Doctor identity (CRM verification) | No need for a chain. | W3C Verifiable Credentials or a CRM lookup at onboarding. |

### 5.2 Costs it would add

- **Compliance**: LGPD right to deletion (art. 18) and data-minimisation are hard to honour on
  an immutable ledger; healthcare buyers will ask.
- **Engineering**: wallets or custodial keys, node/RPC providers, fee management, chain
  reorganisations, and a second trust model to explain to users.
- **Perception**: in health care, "blockchain" tends to raise procurement and security
  questions rather than trust. "End-to-end encrypted and independently verifiable" is a
  stronger and more accurate message.

### 5.3 Recommendation

Do not adopt a blockchain. If a "verifiable" story is wanted for marketing, implement items 3
and 7 of section 4: a public transparency log for frontend releases and an anchored,
hash-chained access log. They deliver the properties people expect from a blockchain
(tamper evidence and public verifiability) without putting anything personal on a public
ledger, and each fits in a small, self-contained change.

## 6. Messaging that stays accurate

Suggested claims, valid **today**:

- "Your reports are encrypted on your device before upload. Our servers store only encrypted
  files and cannot open them."
- "Each consultation receives its own key, only for the exams you choose, and you can end it
  from your phone."
- "Forgot your password? Your recovery code restores access without us ever holding your keys."

Claims to add **only after** the corresponding work in section 4:

- "Even the names of your documents are encrypted" -> **valid since 2026-11-25** (item 1).
- "You can verify the exact code running in your browser" -> after item 3.
- "Sign in with a passkey; no password to steal" -> after item 4.

Avoid: "zero-knowledge" without qualification (metadata is visible today), "unhackable", and
"military-grade" in any form.
