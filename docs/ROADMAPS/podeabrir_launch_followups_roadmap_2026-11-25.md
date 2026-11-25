# Roadmap: podeabrir.com launch follow-ups

Date: 2026-11-25
Status: not started.
Origin: items from [FINISHED_ROADMAPS/ephemeral_access_podeabrir_roadmap_2026-11-25.md](../FINISHED_ROADMAPS/ephemeral_access_podeabrir_roadmap_2026-11-25.md)
that need an external action, a provider, or real devices.

## 1. Launch on the domain (external, S)

- Azure custom domain `podeabrir.com` + `www`, managed certificate, `APP_ORIGIN` (steps in
  [azure.md](../azure.md) §5).
- Mailbox on `@podeabrir.com` with SPF, DKIM, DMARC; replace the tennisos test mailbox in the
  App Service settings; check inbox placement (Gmail, Outlook).
- VAPID keys per environment in the secret store.
- Done when: invitations, reset and "pedido de leitura" emails arrive from `@podeabrir.com` and
  pass SPF/DKIM; production smoke test in azure.md §5 passes.

## 2. Push on real devices (S)

- Install the PWA on Android (Chrome) and iOS 16.4+ (home screen); enable notifications in Conta;
  trigger a `@nome` request and a link open.
- Done when: notifications arrive within seconds on both platforms and a removed subscription
  (410) is cleaned up.

## 3. External anchoring of the history chain (S)

- Daily job: take each owner's latest event hash (or a Merkle root over all heads), anchor it with
  OpenTimestamps, store the proof; show "ancorado em <data>" in "Quem viu".
- Closes the remaining gap: a compromised server rewriting history before the owner's first view.

## 4. Verified professionals (L, needs a provider)

- Optional verification of doctors (CRM) and other professionals, shown to the owner when
  approving a request. Requires a reliable data source/contract (e.g. CFM data or a KYC provider)
  and a privacy assessment. No implementation until a provider is chosen.
