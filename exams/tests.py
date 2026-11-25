import base64
import json
import secrets
import time
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import pyotp
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .crypto_format import comparison_code, fingerprint
from .policy import event_material
from .mailer import EmailRetryableError
from .models import AccountMFA, AccountVault, Document, EmailDelivery, Grant, GrantEvent, Invitation, PushSubscription
from .outbox import process_due
from .security import mfa_cipher

SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def token(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


PASSWORD = token(b"p" * 32)
WRAPPED = token(b"\x01" + b"w" * 60)
SHARED = token(b"\x01" + b"g" * 60)
PUBLIC = token(ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
    Encoding.X962, PublicFormat.UncompressedPoint,
))
CIPHERTEXT = b"\x01" + b"c" * 45
PDF = b"%PDF-1.4\n%%EOF\n"
KEY = Fernet.generate_key().decode()
NEW_PASSWORD = token(b"n" * 32)
RECOVERY = token(b"r" * 32)
User = get_user_model()


class FakeSender:
    """Captures rendered messages instead of talking to SMTP."""

    def __init__(self, error=None):
        self.messages, self.error = [], error

    def send(self, message):
        if self.error:
            raise self.error
        self.messages.append(message)


SEALED = token(b"\x01" + b"t" * 40)


def make_document(owner, sealed=SEALED, date="2026-10-01"):
    return Document.objects.create(owner=owner, sealed_title=sealed, document_date=date,
                                   ciphertext=CIPHERTEXT, wrapped_key=WRAPPED)


def link_token(message):
    return message.text_body.split("#", 1)[1].split()[0]


def make_owner(email, staff=False):
    user = User.objects.create(username=email, email=email, password=make_password(PASSWORD), is_staff=staff)
    AccountMFA.objects.create(user=user, encrypted_secret=mfa_cipher().encrypt(SECRET.encode()).decode())
    AccountVault.objects.create(user=user, wrapped_password=WRAPPED, wrapped_recovery=SHARED,
                                recovery_verifier=make_password(RECOVERY))
    return user


def post_json(client, url, payload=None):
    return client.post(url, json.dumps(payload or {}), content_type="application/json")


def error_code(response):
    return response.json()["error"]["code"]


def chain_is_valid(owner):
    previous = "0" * 64
    for event in GrantEvent.objects.filter(owner=owner).order_by("id"):
        if event.prev_hash != previous or sha256(event_material(previous, event).encode()).hexdigest() != event.hash:
            return False
        previous = event.hash
    return True


class OwnerTestCase(TestCase):
    def setUp(self):
        self.owner = Client()
        self.viewer = Client()
        self.stranger = Client()
        self.user = make_owner("paciente@example.com")
        self.other = make_owner("outro@example.com")
        self.visible = make_document(self.user)
        self.second = make_document(self.user, date="2026-09-01")
        self.hidden = make_document(self.other)
        self.owner.force_login(self.user)

    def share(self, document=None, **extra):
        document_id = str((document or self.visible).id)
        return {"documents": [document_id], "share_keys": {document_id: SHARED}, **extra}


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class InPersonGrantTests(OwnerTestCase):
    def request_reader(self, client=None, **body):
        response = post_json(client or self.viewer, reverse("reader"), {"recipient_key": PUBLIC, **body})
        self.assertEqual(response.status_code, 201)
        return response.json()["data"]

    def state(self):
        return self.viewer.get(reverse("reader_status")).json()["data"]["state"]

    def test_in_person_grant_serves_only_selected_document_until_revocation(self):
        pending = self.request_reader()
        code, short_code = pending["code"], pending["code"].split(".")[0]
        self.assertEqual(code, Grant.objects.get().pairing_code + "." + fingerprint(PUBLIC))
        self.assertTrue(pending["qr"].startswith("data:image/svg"))
        visible_url = reverse("reader_content", args=[self.visible.id])
        approve = reverse("grant_in_person")
        self.assertEqual(self.viewer.get(visible_url).status_code, 403)
        self.assertEqual(self.state(), "pending")
        self.assertEqual(post_json(self.stranger, approve, self.share(code=code, sender_key=PUBLIC)).status_code, 401)
        self.assertEqual(error_code(post_json(self.owner, approve, self.share(self.hidden, code=code, sender_key=PUBLIC))),
                         "no_exams_selected")
        self.assertEqual(error_code(post_json(self.owner, approve, self.share(code=code, sender_key=PUBLIC, minutes=999))),
                         "invalid_policy")
        self.assertEqual(self.owner.get(reverse("pairing_key", args=[short_code])).json()["data"]["recipient_key"], PUBLIC)
        mismatch = post_json(self.owner, approve, self.share(code=short_code + "." + "0" * 16, sender_key=PUBLIC))
        self.assertEqual(error_code(mismatch), "pairing_mismatch")
        granted = post_json(self.owner, approve, self.share(code=code, sender_key=PUBLIC, minutes=15))
        self.assertEqual(granted.status_code, 201)
        grant_id = granted.json()["data"]["id"]
        self.assertEqual(post_json(self.owner, approve, self.share(code=code, sender_key=PUBLIC)).status_code, 409)

        active = self.viewer.get(reverse("reader")).json()["data"]
        self.assertEqual((active["state"], active["salt"], active["sender_key"]), ("active", short_code, PUBLIC))
        self.assertEqual([doc["sealed_title"] for doc in active["documents"]], [SEALED])
        response = self.viewer.get(visible_url)
        self.assertEqual((response.content, response["X-Document-Key"]), (CIPHERTEXT, SHARED))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.viewer.get(reverse("reader_content", args=[self.second.id])).status_code, 404)
        self.assertEqual(self.stranger.get(visible_url).status_code, 403)

        self.stranger.force_login(self.other)
        self.assertEqual(self.stranger.get(reverse("grants")).json()["data"], [])
        self.assertEqual(self.stranger.delete(reverse("grant_revoke", args=[grant_id])).status_code, 204)
        self.assertEqual(self.state(), "active")
        self.assertEqual(self.owner.delete(reverse("grant_revoke", args=[grant_id])).status_code, 204)
        self.assertEqual(self.state(), "revoked")
        self.assertEqual(self.viewer.get(visible_url).status_code, 403)
        kinds = list(GrantEvent.objects.filter(owner=self.user).values_list("kind", flat=True))
        self.assertEqual(kinds, ["approved", "opened", "ended"])
        self.assertTrue(chain_is_valid(self.user))
        history = self.owner.get(reverse("history")).json()["data"]
        self.assertEqual([event["kind"] for event in history["events"]], kinds)

    def test_in_person_pairing_and_access_expire(self):
        code = self.request_reader()["code"]
        Grant.objects.update(pair_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(error_code(post_json(self.owner, reverse("grant_in_person"), self.share(code=code, sender_key=PUBLIC))),
                         "pairing_unavailable")
        self.assertEqual(self.state(), "expired")
        fresh = self.request_reader()["code"]
        self.assertEqual(post_json(self.owner, reverse("grant_in_person"), self.share(code=fresh, sender_key=PUBLIC)).status_code, 201)
        Grant.objects.filter(pairing_code=fresh.split(".")[0]).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.viewer.get(reverse("reader_content", args=[self.visible.id])).status_code, 403)
        self.assertEqual(self.state(), "expired")

    def test_grant_extend_is_capped(self):
        code = self.request_reader()["code"]
        grant_id = post_json(self.owner, reverse("grant_in_person"), self.share(code=code, sender_key=PUBLIC)).json()["data"]["id"]
        self.assertEqual(error_code(post_json(self.owner, reverse("grant_extend", args=[grant_id]), {"minutes": 7})), "invalid_policy")
        with self.settings(GRANT_MAX_MINUTES=60):
            extended = post_json(self.owner, reverse("grant_extend", args=[grant_id]), {"minutes": 1440}).json()["data"]
        self.assertLessEqual(datetime.fromisoformat(extended["expires_at"]), timezone.now() + timedelta(minutes=61))


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class HandleRequestTests(OwnerTestCase):
    def test_handle_request_needs_approval_and_unknown_handle_looks_identical(self):
        self.assertEqual(self.owner.put(reverse("profile"), json.dumps({"handle": "Joao", "active": True}),
                                        content_type="application/json").json()["data"]["handle"], "joao")
        other = Client()
        other.force_login(self.other)
        taken = other.put(reverse("profile"), json.dumps({"handle": "joao", "active": True}), content_type="application/json")
        self.assertEqual(error_code(taken), "handle_taken")

        known = post_json(self.viewer, reverse("reader"), {"recipient_key": PUBLIC, "handle": "joao"})
        unknown = post_json(Client(), reverse("reader"), {"recipient_key": PUBLIC, "handle": "ninguem"})
        self.assertEqual((known.status_code, unknown.status_code), (201, 201))
        self.assertEqual(sorted(known.json()["data"]), sorted(unknown.json()["data"]))
        self.assertEqual(EmailDelivery.objects.filter(purpose="read_request").count(), 1)

        [pending] = [g for g in self.owner.get(reverse("grants")).json()["data"] if g["state"] == "pending"]
        nonce = known.json()["data"]["nonce"]
        self.assertEqual((pending["recipient_key"], pending["nonce"], pending["duplicate"]), (PUBLIC, nonce, False))
        self.assertEqual(len(comparison_code(PUBLIC, nonce)), 6)
        approve = reverse("grant_approve", args=[pending["id"]])
        self.assertEqual(post_json(other, approve, self.share(self.hidden, sender_key=PUBLIC)).status_code, 409)
        self.assertEqual(post_json(self.owner, approve, self.share(sender_key=PUBLIC, minutes=45)).status_code, 201)
        active = self.viewer.get(reverse("reader")).json()["data"]
        self.assertEqual((active["state"], active["salt"]), ("active", nonce))

        self.owner.put(reverse("profile"), json.dumps({"handle": "joao", "active": False}), content_type="application/json")
        paused = post_json(Client(), reverse("reader"), {"recipient_key": PUBLIC, "handle": "joao"})
        self.assertEqual(paused.status_code, 201)
        self.assertEqual(EmailDelivery.objects.filter(purpose="read_request").count(), 1)


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class HandleRetryTests(OwnerTestCase):
    def test_handle_request_again_after_expiry_creates_new_pending_request(self):
        self.owner.put(reverse("profile"), json.dumps({"handle": "joao", "active": True}), content_type="application/json")
        first = post_json(self.viewer, reverse("reader"), {"recipient_key": PUBLIC, "handle": "joao"})
        self.assertEqual(first.status_code, 201)
        Grant.objects.update(pair_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.viewer.get(reverse("reader_status")).json()["data"]["state"], "expired")
        again = post_json(self.viewer, reverse("reader"), {"recipient_key": PUBLIC, "handle": "joao"})
        self.assertEqual(again.status_code, 201, again.content[:300])
        self.assertEqual(again.json()["data"]["state"], "pending")


class RateKeyTests(TestCase):
    def test_rate_key_every_purpose_fits_security_state_column(self):
        import re as regex
        from pathlib import Path

        from .models import SecurityState
        from .security import rate_key
        limit = SecurityState._meta.get_field("name").max_length
        source = "".join(path.read_text() for path in Path(__file__).parent.glob("*.py") if path.name != "tests.py")
        purposes = set(regex.findall(r'rate_key\("([a-z-]+)"', source))
        self.assertIn("request-mail", purposes)
        for purpose in purposes:
            self.assertLessEqual(len(rate_key(purpose, "x" * 200)), limit, purpose)
        for name in regex.findall(r'allow_attempt\("([a-z-]+)"', source):
            self.assertLessEqual(len(name), limit, name)
        with self.assertRaises(ValueError):
            rate_key("a-very-long-purpose-name", "x")


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class NotificationFailureTests(OwnerTestCase):
    def test_reader_request_succeeds_when_notification_fails(self):
        self.owner.put(reverse("profile"), json.dumps({"handle": "joao", "active": True}), content_type="application/json")
        with patch("exams.reader.enqueue", side_effect=RuntimeError("smtp down")):
            response = post_json(self.viewer, reverse("reader"), {"recipient_key": PUBLIC, "handle": "joao"})
        self.assertEqual(response.status_code, 201)
        self.assertIn(settings.READER_COOKIE_NAME, response.cookies)
        self.assertEqual(self.viewer.get(reverse("reader_status")).json()["data"]["state"], "pending")


class LinkGrantTests(OwnerTestCase):
    def create(self, **policy):
        return post_json(self.owner, reverse("grant_link"), {**self.share(), "minutes": 60, **policy})

    def open(self, client, grant_id, pin=None):
        return post_json(client, reverse("link_open", args=[grant_id]), {"pin": pin} if pin else {})

    def test_link_policy_requires_pin_for_long_or_multi_document_links(self):
        both = [str(self.visible.id), str(self.second.id)]
        multi = {"documents": both, "share_keys": {doc: SHARED for doc in both}, "minutes": 60}
        self.assertEqual(error_code(post_json(self.owner, reverse("grant_link"), multi)), "pin_required")
        self.assertEqual(error_code(self.create(minutes=7 * 24 * 60)), "pin_required")
        self.assertEqual(error_code(self.create(minutes=5)), "invalid_policy")
        self.assertEqual(self.create(minutes=7 * 24 * 60, pin="2468").status_code, 201)

    def test_link_view_once_serves_first_opener_only_until_revoked(self):
        grant_id = self.create(max_opens=1, label="Dra. Ana").json()["data"]["id"]
        preview = self.viewer.get(reverse("link_preview", args=[grant_id])).json()["data"]
        self.assertEqual((preview["state"], preview["pin_required"], preview["document_count"]), ("available", False, 1))
        self.assertEqual(self.viewer.get(reverse("link_content", args=[grant_id, self.visible.id])).status_code, 403)
        opened = self.open(self.viewer, grant_id).json()["data"]
        self.assertEqual(opened["documents"][0]["wrapped_key"], SHARED)
        content = self.viewer.get(reverse("link_content", args=[grant_id, self.visible.id]))
        self.assertEqual(content.content, CIPHERTEXT)
        self.assertEqual(error_code(self.open(self.stranger, grant_id)), "link_unavailable")
        self.assertEqual(self.stranger.get(reverse("link_preview", args=[grant_id])).json()["data"], {"state": "unavailable"})
        self.assertEqual(self.stranger.get(reverse("link_content", args=[grant_id, self.visible.id])).status_code, 403)
        self.assertEqual(self.viewer.get(reverse("link_status", args=[grant_id])).json()["data"]["state"], "active")
        self.owner.delete(reverse("grant_revoke", args=[grant_id]))
        self.assertEqual(self.viewer.get(reverse("link_content", args=[grant_id, self.visible.id])).status_code, 403)
        self.assertEqual(self.viewer.get(reverse("link_status", args=[grant_id])).json()["data"]["state"], "ended")
        kinds = list(GrantEvent.objects.filter(owner=self.user).values_list("kind", flat=True))
        self.assertEqual(kinds, ["created", "opened", "viewed", "ended"])
        self.assertTrue(chain_is_valid(self.user))

    def test_link_wrong_pin_locks_after_limit(self):
        grant_id = self.create(pin="1357").json()["data"]["id"]
        self.assertEqual(error_code(self.open(self.viewer, grant_id)), "invalid_pin")
        with self.settings(LINK_PIN_MAX_FAILURES=3):
            self.assertEqual(error_code(self.open(self.viewer, grant_id, "0000")), "invalid_pin")
            self.assertEqual(self.open(self.viewer, grant_id, "1357").status_code, 200)
            self.assertEqual(error_code(self.open(self.viewer, grant_id, "0001")), "invalid_pin")
            self.assertEqual(error_code(self.open(self.viewer, grant_id, "0002")), "link_unavailable")
        self.assertEqual(self.open(self.viewer, grant_id, "1357").status_code, 410)
        self.assertEqual(Grant.objects.get(pk=grant_id).end_reason, "locked")

    def test_link_unknown_id_looks_like_ended(self):
        response = self.viewer.get(reverse("link_preview", args=[uuid4()]))
        self.assertEqual(response.json()["data"], {"state": "unavailable"})


class DocumentDeletionTests(OwnerTestCase):
    def test_document_delete_owner_only_and_ends_emptied_grants(self):
        link = post_json(self.owner, reverse("grant_link"), {**self.share(), "minutes": 60}).json()["data"]["id"]
        self.stranger.force_login(self.other)
        self.assertEqual(self.stranger.delete(reverse("document_detail", args=[self.visible.id])).status_code, 204)
        self.assertTrue(Document.objects.filter(pk=self.visible.id).exists())
        self.assertEqual(self.owner.delete(reverse("document_detail", args=[self.visible.id])).status_code, 204)
        self.assertFalse(Document.objects.filter(pk=self.visible.id).exists())
        self.assertEqual(Grant.objects.get(pk=link).end_reason, "revoked")
        self.assertTrue(chain_is_valid(self.user))
        self.assertEqual(self.owner.delete(reverse("document_detail", args=[self.visible.id])).status_code, 204)

    def test_pending_requests_lists_only_waiting_handle_requests(self):
        self.owner.put(reverse("profile"), json.dumps({"handle": "ana", "active": True}), content_type="application/json")
        self.assertEqual(self.owner.get(reverse("grants_pending")).json()["data"]["count"], 0)
        post_json(self.viewer, reverse("reader"), {"recipient_key": PUBLIC, "handle": "ana"})
        data = self.owner.get(reverse("grants_pending")).json()["data"]
        self.assertEqual(data["count"], 1)
        Grant.objects.update(pair_until=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.owner.get(reverse("grants_pending")).json()["data"]["count"], 0)
        self.assertEqual(self.stranger.get(reverse("grants_pending")).status_code, 401)


class HistoryAndPushTests(OwnerTestCase):
    def test_history_chain_detects_edits(self):
        post_json(self.owner, reverse("grant_link"), {**self.share(), "minutes": 60})
        post_json(self.owner, reverse("grant_link"), {**self.share(), "minutes": 60})
        self.assertTrue(chain_is_valid(self.user))
        first = GrantEvent.objects.filter(owner=self.user).order_by("id").first()
        GrantEvent.objects.filter(pk=first.pk).update(detail="editado")
        self.assertFalse(chain_is_valid(self.user))

    @override_settings(VAPID_PUBLIC_KEY="pub", VAPID_PRIVATE_KEY="priv")
    def test_push_notifies_owner_and_drops_gone_subscriptions(self):
        PushSubscription.objects.create(user=self.user, endpoint="https://push.example/a", p256dh="p" * 87, auth="a" * 22)

        class Inline:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch("exams.push.threading.Thread", Inline), patch("exams.push.send_one", return_value=410) as send:
            grant_id = post_json(self.owner, reverse("grant_link"), {**self.share(), "minutes": 60}).json()["data"]["id"]
            post_json(self.viewer, reverse("link_open", args=[grant_id]), {})
        self.assertEqual(send.call_count, 1)
        self.assertIn(b"Link aberto", send.call_args.args[1])
        self.assertFalse(PushSubscription.objects.exists())

@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class EnrollmentTests(TestCase):
    def deliver(self):
        sender = FakeSender()
        process_due(sender=sender)
        return sender.messages

    def enroll(self, client, invite):
        return post_json(client, reverse("enroll"), {
            "token": invite, "password": PASSWORD, "wrapped_password": WRAPPED,
            "wrapped_recovery": SHARED, "recovery_proof": RECOVERY,
        })

    def complete(self, client, started):
        secret = started.json()["data"]["secret"]
        return post_json(client, reverse("confirm_enrollment"), {"otp": pyotp.TOTP(secret).now()})

    def test_enrollment_bootstrap_email_invite_then_staff_invite_single_use(self):
        code = secrets.token_urlsafe(32)
        with self.settings(BOOTSTRAP_INVITE_DIGEST=sha256(code.encode()).hexdigest()):
            queued = post_json(self.client, reverse("bootstrap_invitation"), {"token": code, "email": " Ana@Example.com "})
            self.assertEqual(queued.status_code, 202)
            [message] = self.deliver()
            self.assertEqual(message.to_address, "ana@example.com")
            invite = link_token(message)
            inspected = post_json(self.client, reverse("inspect_invitation"), {"token": invite})
            self.assertEqual(inspected.json()["data"]["email"], "ana@example.com")
            started = self.enroll(self.client, invite)
            self.assertEqual(started.status_code, 201)
            confirmed = self.complete(self.client, started)
            self.assertEqual(confirmed.json()["data"]["user"], {"email": "ana@example.com", "is_staff": True})
            self.assertEqual(confirmed.json()["data"]["wrapped_vault"], WRAPPED)
            self.assertEqual(AccountVault.objects.get().wrapped_recovery, SHARED)
            again = post_json(Client(), reverse("bootstrap_invitation"), {"token": code, "email": "b@example.com"})
            self.assertEqual(error_code(again), "invalid_invite")

        self.assertEqual(post_json(self.client, reverse("invitations"), {"email": "bia@example.com"}).status_code, 202)
        [message] = self.deliver()
        invite = link_token(message)
        invited = Client()
        self.assertEqual(self.complete(invited, self.enroll(invited, invite)).status_code, 201)
        self.assertFalse(User.objects.get(username="bia@example.com").is_staff)
        self.assertEqual(error_code(self.enroll(Client(), invite)), "invalid_invite")
        self.assertEqual(error_code(post_json(self.client, reverse("invitations"), {"email": "bia@example.com"})),
                         "username_taken")

    def test_enrollment_invitation_rejects_non_email(self):
        user = make_owner("staff@example.com", staff=True)
        self.client.force_login(user)
        response = post_json(self.client, reverse("invitations"), {"email": "las.leandro"})
        self.assertEqual((response.status_code, error_code(response)), (400, "validation_failed"))
        self.assertIn("email", response.json()["error"]["fields"])

    def test_enrollment_confirm_without_pending_session_expires(self):
        response = post_json(self.client, reverse("confirm_enrollment"), {"otp": "123456"})
        self.assertEqual((response.status_code, error_code(response)), (410, "enrollment_expired"))


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = make_owner("ana@example.com")
        make_document(self.user)

    def reset_link(self):
        self.assertEqual(post_json(self.client, reverse("password_reset"), {"email": "ANA@example.com"}).status_code, 202)
        sender = FakeSender()
        process_due(sender=sender)
        return link_token(sender.messages[0])

    def confirm(self, link, **overrides):
        payload = {"token": link, "otp": pyotp.TOTP(SECRET).now(), "mode": "recovery", "password": NEW_PASSWORD,
                   "wrapped_password": token(b"\x01" + b"z" * 60), "recovery_proof": RECOVERY, **overrides}
        return post_json(self.client, reverse("password_reset_confirm"), payload)

    def test_password_reset_unknown_email_same_reply_no_mail(self):
        response = post_json(self.client, reverse("password_reset"), {"email": "ghost@example.com"})
        self.assertEqual(response.status_code, 202)
        self.assertFalse(EmailDelivery.objects.exists())

    def test_password_reset_with_recovery_code_keeps_reports_and_ends_sessions(self):
        session = Client()
        session.force_login(self.user)
        link = self.reset_link()
        inspected = post_json(self.client, reverse("password_reset_inspect"), {"token": link}).json()["data"]
        self.assertEqual(inspected, {"email": "ana@example.com", "wrapped_recovery": SHARED})
        self.assertEqual(error_code(self.confirm(link, recovery_proof=token(b"x" * 32))), "invalid_recovery_code")
        with patch("exams.security.time.time", return_value=time.time() + 30):
            self.assertEqual(self.confirm(link).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(Document.objects.filter(owner=self.user).count(), 1)
        self.assertEqual(AccountVault.objects.get().wrapped_password, token(b"\x01" + b"z" * 60))
        self.assertEqual(session.get(reverse("documents")).status_code, 401)
        self.assertEqual(error_code(self.confirm(link)), "invalid_reset_link")
        self.assertTrue(EmailDelivery.objects.filter(purpose="password_changed").exists())

    def test_password_reset_fresh_vault_deletes_unreadable_reports(self):
        link = self.reset_link()
        new_recovery = token(b"q" * 32)
        self.assertEqual(error_code(self.confirm(link, mode="fresh")), "validation_failed")
        response = self.confirm(link, mode="fresh", recovery_proof=new_recovery, wrapped_recovery=WRAPPED)
        self.assertEqual(response.json()["data"], {"mode": "fresh"})
        self.assertFalse(Document.objects.filter(owner=self.user).exists())
        vault = AccountVault.objects.get()
        self.assertEqual(vault.wrapped_recovery, WRAPPED)
        self.assertTrue(check_password(new_recovery, vault.recovery_verifier))


class OutboxTests(TestCase):
    @override_settings(EMAIL_MAX_ATTEMPTS=2, EMAIL_RETRY_BASE_SECONDS=0)
    def test_outbox_retryable_failure_retries_then_fails_without_issuing_tokens(self):
        delivery = EmailDelivery.objects.create(purpose="invitation", to_address="x@example.com")
        failing = FakeSender(error=EmailRetryableError("timeout"))
        process_due(sender=failing)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempt_count), ("retry_wait", 1))
        self.assertFalse(Invitation.objects.exists())
        process_due(sender=failing, now=timezone.now() + timedelta(seconds=1))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "failed")

    def test_outbox_duplicate_pending_delivery_is_reused(self):
        from .outbox import enqueue
        self.assertEqual(enqueue("invitation", "x@example.com").pk, enqueue("invitation", "x@example.com").pk)


class SessionTests(TestCase):
    def test_session_anonymous_exposes_limits_and_no_personal_data(self):
        data = self.client.get(reverse("session")).json()["data"]
        self.assertIsNone(data["user"])
        self.assertTrue(data["csrf_token"])
        self.assertEqual(data["limits"]["access_minutes"], 45)
        self.assertEqual(error_code(self.client.get(reverse("documents"))), "auth_required")

    def test_spa_routes_and_unknown_api_paths(self):
        page = self.client.get("/documentos/")
        self.assertIn(page.status_code, {200, 503})
        self.assertIn("frame-ancestors 'none'", page["Content-Security-Policy"])
        self.assertEqual(error_code(self.client.get("/api/nao-existe/")), "not_found")
