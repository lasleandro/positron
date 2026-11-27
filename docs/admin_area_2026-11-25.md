# Admin area (2026-11-25)

Where admins invite people, answer "Solicitar conta" requests and decide who else is an admin.
Reached from the account menu in the top right (Administração), at `/administracao/`.
The old `/convites/` page redirects there.

## Roles

- **Admin** is Django's `is_staff`. The first account, created with the installation code, is
  admin; others become admin through an admin invitation or the toggle in Pessoas.
- Every admin endpoint uses `staff_required` (401 without a session, 403 for members). The
  frontend guard (`RequireOwner staff`) only hides the page; the server is the authority.
- Nobody changes their own role (`cannot_change_own_role`): no self-escalation and no way for
  the last admin to lock everyone out by accident.
- As of 2026-11-25, `las.leandro@gmail.com` is admin both locally and on Azure (it was the
  bootstrap account, so no promotion was needed).

## Sections

| Tab (`?aba=`) | What it shows | Actions |
|---|---|---|
| Convites (`convites`) | invitation emails from the outbox, newest first: Na fila, Enviado, Não entregue (bounce, with reason), Falhou, Expirou, Conta criada | send an invitation (optionally as admin; domains that receive no mail are refused at once); resend a failed or expired one |
| Solicitações (`solicitacoes`) | "Solicitar conta" messages: name, email, message, date; Nova, Convidada, Já tem conta | Convidar (sends a regular invitation to that email) |
| Pessoas (`pessoas`) | accounts: joined, last access, admin flag | toggle admin (not for yourself) |

Statuses are derived, not stored: invitation status combines the outbox row, the open
`Invitation` rows and existing accounts; request status checks accounts and invitation emails
for the same address. No migration was needed.

All actions are optimistic (row appears or flips at once, rolls back with the server's message on
failure). While an invitation is queued, and for 5 minutes after it is sent (bounces arrive later),
the list refreshes every 5 s. Undeliverable addresses: see
[auth_email_recovery_2026-11-25.md](auth_email_recovery_2026-11-25.md#undeliverable-addresses-2026-11-25).

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/invitations/` | `{email, admin?}`; `admin: true` makes the new account admin |
| GET | `/api/admin/invitations/?page=` | `{items, page, has_more}`, 50 per page |
| GET | `/api/admin/access-requests/?page=` | same envelope |
| GET | `/api/admin/users/?page=` | same envelope; `is_self` marks the caller |
| PATCH | `/api/admin/users/<id>/` | `{is_staff: bool}`; rate limited (30 per 5 min per admin); audit `admin.role_changed` |

## Header

The owner header keeps Documentos and Compartilhamentos as links; Conta, Administração (admins)
and Sair moved into the account menu (email + chevron, icon only on phones, closes on Escape,
outside click and navigation). On phones the menu stays in the header while the section links
move to the bottom tab bar.

## Verification (2026-11-25)

- Django: `AdminAreaTests` (access control, invitation status through the outbox, pagination
  and request status, promote/demote and self-change refusal). 36/36 tests pass on Postgres.
- Browser E2E on a production build (`positron_e2e`): menu items and closing; invite listed at
  once and followed to Enviado; admin invite flagged; existing account refused; access request
  invited and persisted; member gets 403 and no menu item; promotion persists and unlocks the
  menu for the promoted user; phone menu and admin page without horizontal overflow.
