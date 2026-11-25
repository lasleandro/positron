from django.urls import include, path, re_path

from . import access_requests, account, admin_area, enrollment, grants, library, links, password_reset, profile, reader, spa

api = [
    path("session/", account.session, name="session"),
    path("auth/login/", account.owner_login, name="login"),
    path("auth/logout/", account.owner_logout, name="logout"),
    path("auth/vault/verify/", account.verify_vault_password, name="verify_vault_password"),
    path("consents/", account.accept_consent, name="consents"),
    path("auth/password-reset/", password_reset.request_reset, name="password_reset"),
    path("auth/password-reset/inspect/", password_reset.inspect_reset, name="password_reset_inspect"),
    path("auth/password-reset/confirm/", password_reset.confirm_reset, name="password_reset_confirm"),
    path("enrollment/", enrollment.enroll, name="enroll"),
    path("enrollment/confirm/", enrollment.confirm_enrollment, name="confirm_enrollment"),
    path("access-requests/", access_requests.create_access_request, name="access_requests"),
    path("invitations/", enrollment.create_invitation, name="invitations"),
    path("invitations/bootstrap/", enrollment.bootstrap_invitation, name="bootstrap_invitation"),
    path("invitations/inspect/", enrollment.inspect_invitation, name="inspect_invitation"),
    # Admin area (staff only)
    path("admin/invitations/", admin_area.admin_invitations, name="admin_invitations"),
    path("admin/access-requests/", admin_area.admin_access_requests, name="admin_access_requests"),
    path("admin/users/", admin_area.admin_users, name="admin_users"),
    path("admin/users/<int:user_id>/", admin_area.admin_user, name="admin_user"),
    # Owner: documents
    path("documents/", library.documents, name="documents"),
    path("documents/<uuid:document_id>/", library.document_detail, name="document_detail"),
    path("documents/<uuid:document_id>/content/", library.document_content, name="document_content"),
    # Owner: short-lived permissions
    path("grants/", grants.list_grants, name="grants"),
    path("grants/pending/", grants.pending_requests, name="grants_pending"),
    path("grants/in-person/", grants.approve_in_person, name="grant_in_person"),
    path("grants/links/", grants.create_link, name="grant_link"),
    path("grants/<uuid:grant_id>/", grants.revoke_grant, name="grant_revoke"),
    path("grants/<uuid:grant_id>/approve/", grants.approve_request, name="grant_approve"),
    path("grants/<uuid:grant_id>/extend/", grants.extend_grant, name="grant_extend"),
    path("pairings/<str:code>/key/", grants.pairing_key, name="pairing_key"),
    # Owner: settings and history
    path("profile/", profile.profile, name="profile"),
    path("profile/push/", profile.push_subscription, name="push_subscription"),
    path("history/", profile.history, name="history"),
    # Reader screen (no account): in-person QR and @handle requests
    path("reader/", reader.reader, name="reader"),
    path("reader/status/", reader.reader_status, name="reader_status"),
    path("reader/documents/<uuid:document_id>/content/", reader.reader_document_content, name="reader_content"),
    # Remote link recipients (no account)
    path("links/<uuid:grant_id>/", links.link_preview, name="link_preview"),
    path("links/<uuid:grant_id>/open/", links.open_link, name="link_open"),
    path("links/<uuid:grant_id>/status/", links.link_status, name="link_status"),
    path("links/<uuid:grant_id>/documents/<uuid:document_id>/content/", links.link_document_content,
         name="link_content"),
]

urlpatterns = [
    path("healthz", account.health, name="health"),
    path("api/", include(api)),
    # Everything that is not the API is a client-side route of the React app.
    re_path(r"^(?!api/|healthz)(?P<path>.*)$", spa.index, name="spa"),
]

handler404 = "exams.responses.not_found"
