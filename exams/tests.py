import base64
import json
import secrets
import time
from datetime import datetime, timedelta
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pyotp
from dns import resolver as dns_resolver
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
from .models import AccessRequest, AccountMFA, AccountVault, ConsentRecord, Document, EmailDelivery, Grant, GrantEvent, Invitation, PushSubscription
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


# Invitations check the recipient's mail domain in DNS; tests never touch the network.
_domain_check = patch("exams.enrollment.undeliverable", return_value=False)


def setUpModule():
    _domain_check.start()


def tearDownModule():
    _domain_check.stop()


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
        self.assertEqual(active["grant"], grant_id)
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


class ConsentGateTests(TestCase):
    def test_consent_gate_for_existing_account_and_policy_updates(self):
        user = make_owner("antiga@example.com")
        self.client.force_login(user)
        self.assertFalse(self.client.get(reverse("session")).json()["data"]["user"]["consent_ok"])
        stale = post_json(self.client, reverse("consents"), {"accept": True, "version": "2000-01-01"})
        self.assertEqual(stale.status_code, 400)
        accepted = post_json(self.client, reverse("consents"), {"accept": True, "version": settings.LEGAL_VERSION})
        self.assertTrue(accepted.json()["data"]["user"]["consent_ok"])
        with self.settings(LEGAL_VERSION="2099-01-01"):
            self.assertFalse(self.client.get(reverse("session")).json()["data"]["user"]["consent_ok"])
        self.assertEqual(post_json(Client(), reverse("consents"), {"accept": True, "version": settings.LEGAL_VERSION}).status_code, 401)


class AccessRequestTests(TestCase):
    def send(self, client=None, **body):
        return post_json(client or self.client, reverse("access_requests"), {"email": "nova@example.com", **body})

    def test_access_request_emails_contact_with_requester_as_reply_to(self):
        response = self.send(name="Nova Pessoa", message="Sou da Clínica Sol")
        self.assertEqual(response.status_code, 202)
        delivery = EmailDelivery.objects.get(purpose="access_request")
        self.assertEqual(delivery.to_address, settings.CONTACT_EMAIL)
        sender = FakeSender()
        process_due(sender=sender)
        [message] = sender.messages
        self.assertEqual(message.reply_to, "nova@example.com")
        self.assertIn("Clínica Sol", message.text_body)
        self.assertIn("Nova Pessoa", message.text_body)

    def test_access_request_honeypot_and_limits(self):
        self.assertEqual(self.send(website="http://spam").status_code, 202)
        self.assertFalse(EmailDelivery.objects.exists())
        self.assertEqual(error_code(self.send(email="nao-e-email")), "validation_failed")
        for _ in range(3):
            self.assertEqual(self.send(email="repete@example.com").status_code, 202)
        self.assertEqual(error_code(self.send(email="repete@example.com")), "rate_limited")
        self.assertEqual(EmailDelivery.objects.filter(purpose="access_request").count(), 3)


def load_settings_generator():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "scripts" / "generate_azure_app_settings.py"
    spec = importlib.util.spec_from_file_location("generate_azure_app_settings", path)
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


class AzureSettingsGeneratorTests(TestCase):
    BASE = {
        "APP_ENV": "development", "APP_ORIGIN": "http://localhost:5190", "DJANGO_SECRET_KEY": "s" * 60,
        "VAULT_NAMESPACE": "n" * 48, "TOTP_ENCRYPTION_KEY": KEY, "PG_LOCAL_HOST": "localhost",
        "PG_LOCAL_PASSWORD": "local", "AZURE_PG_HOST": "db.postgres.database.azure.com", "AZURE_PG_PORT": "5432",
        "AZURE_PG_DATABASE": "positron_db", "AZURE_PG_USER": "admin", "AZURE_PG_PASSWORD": "remote",
        "EMAIL_SMTP_HOST": "smtp.example.com", "EMAIL_SMTP_USERNAME": "u", "EMAIL_SMTP_PASSWORD": "p",
        "EMAIL_FROM_ADDRESS": "auth@podeabrir.com", "BACKEND_PORT": "8030", "UNRELATED_KEY": "x",
    }

    def setUp(self):
        self.gen = load_settings_generator()

    def test_generator_maps_database_drops_dev_keys_and_validates_django(self):
        result = self.gen.build_app_settings(dict(self.BASE), {}, "podeabrir", origin="https://podeabrir.com")
        self.assertEqual(result.errors, [])
        values = result.values
        self.assertEqual((values["POSTGRES_HOST"], values["POSTGRES_DB"]), ("db.postgres.database.azure.com", "positron_db"))
        self.assertEqual((values["APP_ENV"], values["APP_ORIGIN"], values["WEBSITES_PORT"]), ("production", "https://podeabrir.com", "8000"))
        for dropped in ("PG_LOCAL_HOST", "PG_LOCAL_PASSWORD", "BACKEND_PORT", "UNRELATED_KEY", "AZURE_PG_HOST"):
            self.assertNotIn(dropped, values)
        self.assertTrue(any("DJANGO_SECRET_KEY is reused" in warning for warning in result.warnings))
        entries = json.loads(self.gen.to_azure_json(values))
        self.assertEqual(entries[0].keys(), {"name", "value", "slotSetting"})

    def test_generator_rejects_missing_or_invalid_secrets_and_warns_on_data_keys(self):
        broken = {**self.BASE, "TOTP_ENCRYPTION_KEY": "not-fernet", "AZURE_PG_PASSWORD": ""}
        errors = self.gen.build_app_settings(broken, {}, "podeabrir", validate_django=False).errors
        self.assertTrue(any("TOTP_ENCRYPTION_KEY" in error for error in errors))
        self.assertTrue(any("POSTGRES_PASSWORD" in error for error in errors))
        short = self.gen.build_app_settings({**self.BASE, "DJANGO_SECRET_KEY": "short"}, {}, "podeabrir")
        self.assertTrue(any("DJANGO_SECRET_KEY" in error for error in short.errors))
        changed = self.gen.build_app_settings(dict(self.BASE), {"VAULT_NAMESPACE": "m" * 48}, "podeabrir")
        self.assertTrue(any("VAULT_NAMESPACE differs" in warning for warning in changed.warnings))

    def test_generator_key_vault_references_secrets_only(self):
        result = self.gen.build_app_settings(dict(self.BASE), {}, "podeabrir", key_vault="pa-kv", validate_django=False)
        self.assertTrue(result.values["DJANGO_SECRET_KEY"].startswith("@Microsoft.KeyVault(VaultName=pa-kv;"))
        self.assertTrue(result.values["POSTGRES_PASSWORD"].startswith("@Microsoft.KeyVault("))
        self.assertEqual(result.values["POSTGRES_DB"], "positron_db")
        self.assertIn("email-smtp-password", result.key_vault_secret_names)


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
        listed = next(g for g in self.owner.get(reverse("grants")).json()["data"] if g["id"] == grant_id)
        reading_left = datetime.fromisoformat(listed["viewing_until"]) - timezone.now()
        self.assertEqual(listed["state"], "exhausted")
        self.assertTrue(timedelta(minutes=29) < reading_left <= timedelta(minutes=settings.LINK_VIEW_MINUTES))
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
            "wrapped_recovery": SHARED, "recovery_proof": RECOVERY, "consent": True,
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
            self.assertEqual(confirmed.json()["data"]["user"], {"email": "ana@example.com", "is_staff": True, "consent_ok": True})
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

    def test_enrollment_requires_consent_and_records_version(self):
        code = secrets.token_urlsafe(32)
        with self.settings(BOOTSTRAP_INVITE_DIGEST=sha256(code.encode()).hexdigest()):
            post_json(self.client, reverse("bootstrap_invitation"), {"token": code, "email": "ana@example.com"})
            invite = link_token(self.deliver()[0])
            refused = post_json(self.client, reverse("enroll"), {
                "token": invite, "password": PASSWORD, "wrapped_password": WRAPPED,
                "wrapped_recovery": SHARED, "recovery_proof": RECOVERY,
            })
            self.assertEqual(refused.status_code, 400)
            self.assertIn("consent", refused.json()["error"]["fields"])
            confirmed = self.complete(self.client, self.enroll(self.client, invite))
        self.assertTrue(confirmed.json()["data"]["user"]["consent_ok"])
        self.assertEqual(ConsentRecord.objects.get().version, settings.LEGAL_VERSION)

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


class MailDomainTests(TestCase):
    @staticmethod
    def resolver(answers):
        """Fake resolve(): ``answers[record_type]`` is a list of exchanges or an exception class."""
        def resolve(_self, domain, record_type):
            answer = answers.get(record_type, dns_resolver.NoAnswer)
            if isinstance(answer, type) and issubclass(answer, Exception):
                raise answer()
            return [SimpleNamespace(exchange=SimpleNamespace(to_text=lambda value=value: value)) for value in answer]
        return patch("dns.resolver.Resolver.resolve", resolve)

    def test_mail_domain_dns_answers_map_to_yes_no_unknown(self):
        from .mail_domains import domain_accepts_mail
        cases = [
            ({"MX": ["mx1.example.net."]}, True),
            ({"MX": ["."]}, False),                                   # RFC 7505 null MX
            ({"MX": dns_resolver.NXDOMAIN}, False),                   # domain does not exist
            ({"MX": dns_resolver.NoAnswer, "A": ["203.0.113.5"]}, True),  # implicit MX
            ({"MX": dns_resolver.NoAnswer}, False),                   # no MX, no address
            ({"MX": dns_resolver.LifetimeTimeout}, None),             # DNS trouble: unknown
        ]
        for answers, expected in cases:
            with self.subTest(answers=answers), self.resolver(answers):
                self.assertIs(domain_accepts_mail("ana@dominio.example"), expected)

    @override_settings(TOTP_ENCRYPTION_KEY=KEY)
    def test_mail_domain_invitation_refused_only_when_domain_clearly_rejects_mail(self):
        admin = Client()
        admin.force_login(make_owner("admin@example.com", staff=True))
        with patch("exams.enrollment.undeliverable", return_value=True):
            response = post_json(admin, reverse("invitations"), {"email": "ana@gmial.com"})
        self.assertEqual((response.status_code, error_code(response)), (400, "email_domain_undeliverable"))
        self.assertFalse(EmailDelivery.objects.filter(to_address="ana@gmial.com").exists())

    def test_mail_domain_not_checked_when_emails_are_not_sent(self):
        from .mail_domains import undeliverable
        with patch("exams.mail_domains.domain_accepts_mail", return_value=False):
            with override_settings(EMAIL_ENABLED=False):
                self.assertFalse(undeliverable("ana@gmial.com"))
            with override_settings(EMAIL_ENABLED=True):
                self.assertTrue(undeliverable("ana@gmial.com"))


def delivery_report(recipient, status="5.1.1", action="failed", reference=""):
    """A delivery status notification (RFC 3464) as an SMTP relay mails it back."""
    quoted = f"X-PodeAbrir-Ref: {reference}\r\n" if reference else ""
    return (
        "From: Mail Delivery System <MAILER-DAEMON@relay.example.net>\r\n"
        "To: auth@podeabrir.com\r\nSubject: Undelivered Mail Returned to Sender\r\nMIME-Version: 1.0\r\n"
        'Content-Type: multipart/report; report-type=delivery-status; boundary="B"\r\n\r\n'
        "--B\r\nContent-Type: text/plain\r\n\r\nYour message could not be delivered.\r\n"
        "--B\r\nContent-Type: message/delivery-status\r\n\r\n"
        "Reporting-MTA: dns; relay.example.net\r\n\r\n"
        f"Final-Recipient: rfc822; {recipient}\r\nAction: {action}\r\nStatus: {status}\r\n"
        "Diagnostic-Code: smtp; 550 5.1.1 user unknown\r\n\r\n"
        "--B\r\nContent-Type: text/rfc822-headers\r\n\r\n"
        f"From: Pode Abrir <auth@podeabrir.com>\r\nTo: {recipient}\r\n{quoted}Subject: Seu convite\r\n\r\n"
        "--B--\r\n"
    ).encode()


class FakeImap:
    """Just enough IMAP for check_bounces: UID SEARCH/FETCH/STORE over in-memory messages."""

    def __init__(self, messages):
        self.messages, self.flagged, self.calls = messages, [], []

    def login(self, user, password):
        self.calls.append("login")

    def select(self, folder):
        self.calls.append(f"select {folder}")

    def logout(self):
        self.calls.append("logout")

    def uid(self, command, *args):
        if command == "SEARCH":
            self.calls.append(" ".join(str(arg) for arg in args[1:]))
            return "OK", [b" ".join(self.messages)]
        if command == "FETCH":
            uid, what = args
            raw = self.messages[uid]
            if what == "(RFC822.SIZE)":
                return "OK", [b"1 (UID " + uid + b" RFC822.SIZE " + str(len(raw)).encode() + b")"]
            return "OK", [(b"1 (UID " + uid + b" BODY[] {%d}" % len(raw), raw), b")"]
        if command == "STORE":
            self.flagged.append(args[0])
            return "OK", [b""]
        raise AssertionError(command)


class BounceTests(TestCase):
    def sent(self, to, days_ago=0):
        return EmailDelivery.objects.create(purpose="invitation", to_address=to, status="sent",
                                            sent_at=timezone.now() - timedelta(days=days_ago))

    def test_bounce_report_parsing_keeps_only_permanent_failures(self):
        from .bounces import Bounce, parse_bounces
        reference = str(uuid4())
        self.assertEqual(parse_bounces(delivery_report("Ana@Example.com", reference=reference)),
                         [Bounce("ana@example.com", "5.1.1", reference)])
        self.assertEqual(parse_bounces(delivery_report("ana@example.com", status="4.2.2", action="delayed")), [])
        self.assertEqual(parse_bounces(b"From: amiga@example.com\r\nSubject: oi\r\n\r\nTudo bem?"), [])

    def test_bounce_matches_quoted_reference_then_latest_to_address(self):
        from .bounces import Bounce, record_bounce
        older, latest = self.sent("ana@example.com", days_ago=2), self.sent("ana@example.com")
        stale = self.sent("velho@example.com", days_ago=30)
        self.assertEqual(record_bounce(Bounce("ana@example.com", "5.1.1", str(older.id))).pk, older.pk)
        self.assertEqual(record_bounce(Bounce("ana@example.com", "5.2.2", "not-a-uuid")).pk, latest.pk)
        self.assertIsNone(record_bounce(Bounce("velho@example.com", "5.1.1")))
        self.assertIsNone(record_bounce(Bounce("ninguem@example.com", "5.1.1")))
        older.refresh_from_db(); latest.refresh_from_db(); stale.refresh_from_db()
        self.assertEqual((older.status, older.last_error_code), ("bounced", "dsn:5.1.1"))
        self.assertEqual((latest.status, latest.last_error_code), ("bounced", "dsn:5.2.2"))
        self.assertEqual(stale.status, "sent")

    def test_bounce_check_flags_only_reports_it_understood(self):
        from .bounces import MAX_MESSAGE_BYTES, check_bounces
        delivery = self.sent("ana@example.com")
        imap = FakeImap({
            b"7": delivery_report("ana@example.com", reference=str(delivery.id)),
            b"8": b"Content-Type: text/plain\r\nSubject: delivery-status da reuniao\r\n\r\npessoal",
            b"9": delivery_report("ana@example.com") + b"x" * MAX_MESSAGE_BYTES,
        })
        self.assertEqual(check_bounces(connect=lambda: imap), 1)
        self.assertEqual(imap.flagged, [b"7"])
        self.assertIn("UNSEEN SINCE", imap.calls[2])
        self.assertIn("HEADER Content-Type delivery-status", imap.calls[2])
        self.assertEqual(imap.calls[-1], "logout")
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "bounced")

    @override_settings(TOTP_ENCRYPTION_KEY=KEY)
    def test_bounce_shows_in_admin_invitations(self):
        from .bounces import Bounce, record_bounce
        self.sent("ana@example.com")
        record_bounce(Bounce("ana@example.com", "5.1.1"))
        admin = Client()
        admin.force_login(make_owner("admin@example.com", staff=True))
        item = admin.get(reverse("admin_invitations")).json()["data"]["items"][0]
        self.assertEqual((item["status"], item["bounce_code"]), ("bounced", "5.1.1"))

    def test_bounce_reference_header_set_on_every_delivery(self):
        delivery = EmailDelivery.objects.create(purpose="invitation", to_address="ana@example.com")
        sender = FakeSender()
        process_due(sender=sender)
        self.assertEqual(sender.messages[0].reference, str(delivery.id))


class OutboxTests(TestCase):
    @override_settings(EMAIL_SMTP_HOST="smtp.example.com", EMAIL_SMTP_USERNAME="u", EMAIL_SMTP_PASSWORD="p",
                       EMAIL_FROM_ADDRESS="nao-responda@example.com", EMAIL_SMTP_SECURITY="ssl")
    def test_outbox_logo_travels_inside_the_message_not_from_the_server(self):
        from email import message_from_string

        from .email_templates import LOGO_CID, invitation_email
        from .mailer import SmtpEmailSender
        message = invitation_email("ana@example.com", "https://podeabrir.com/cadastro/#token", 72)
        self.assertIn(f'src="cid:{LOGO_CID}"', message.html_body)
        self.assertNotIn("/brand/", message.html_body)
        mime = message_from_string(SmtpEmailSender()._mime(message))
        self.assertEqual(mime.get_content_type(), "multipart/related")
        parts = {part.get_content_type(): part for part in mime.walk()}
        self.assertIn("text/plain", parts)
        self.assertIn("text/html", parts)
        logo = parts["image/png"]
        self.assertEqual(logo["Content-ID"], f"<{LOGO_CID}>")
        self.assertTrue(logo.get_payload(decode=True).startswith(b"\x89PNG"))

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


@override_settings(TOTP_ENCRYPTION_KEY=KEY)
class AdminAreaTests(TestCase):
    def setUp(self):
        self.admin_user = make_owner("admin@example.com", staff=True)
        self.member = make_owner("membro@example.com")
        self.admin = Client()
        self.admin.force_login(self.admin_user)
        self.plain = Client()
        self.plain.force_login(self.member)

    def items(self, name, client=None, **query):
        return (client or self.admin).get(reverse(name), query).json()["data"]["items"]

    def test_admin_area_requires_admin_role(self):
        for name in ("admin_invitations", "admin_access_requests", "admin_users"):
            self.assertEqual(self.plain.get(reverse(name)).status_code, 403)
            self.assertEqual(Client().get(reverse(name)).status_code, 401)
        patch_url = reverse("admin_user", args=[self.member.pk])
        self.assertEqual(self.plain.patch(patch_url, json.dumps({"is_staff": True}), content_type="application/json").status_code, 403)
        self.assertEqual(error_code(post_json(self.plain, reverse("invitations"), {"email": "x@example.com"})), "forbidden")

    def test_admin_invitations_list_status_and_admin_invites(self):
        self.assertEqual(post_json(self.admin, reverse("invitations"), {"email": "nova@example.com", "admin": True}).status_code, 202)
        post_json(self.admin, reverse("invitations"), {"email": "outra@example.com"})
        listed = {item["email"]: item for item in self.items("admin_invitations")}
        self.assertEqual((listed["nova@example.com"]["admin"], listed["nova@example.com"]["status"]), (True, "queued"))
        self.assertFalse(listed["outra@example.com"]["admin"])
        process_due(sender=FakeSender())
        listed = {item["email"]: item for item in self.items("admin_invitations")}
        self.assertEqual(listed["nova@example.com"]["status"], "sent")
        Invitation.objects.filter(email="outra@example.com").update(expires_at=timezone.now() - timedelta(minutes=1))
        make_owner("nova@example.com")
        listed = {item["email"]: item for item in self.items("admin_invitations")}
        self.assertEqual((listed["nova@example.com"]["status"], listed["outra@example.com"]["status"]), ("account", "expired"))

    def test_admin_access_requests_show_progress_and_paginate(self):
        for index in range(52):
            AccessRequest.objects.create(email=f"pessoa{index}@example.com", name="Pessoa", message="Quero usar")
        AccessRequest.objects.create(email="membro@example.com", name="Membro")
        first = self.admin.get(reverse("admin_access_requests")).json()["data"]
        self.assertEqual((len(first["items"]), first["has_more"]), (50, True))
        self.assertEqual(first["items"][0]["status"], "account")
        post_json(self.admin, reverse("invitations"), {"email": "pessoa51@example.com"})
        self.assertEqual(self.items("admin_access_requests")[1]["status"], "invited")
        last = self.admin.get(reverse("admin_access_requests"), {"page": 2}).json()["data"]
        self.assertEqual((len(last["items"]), last["has_more"]), (3, False))
        self.assertEqual(self.admin.get(reverse("admin_access_requests"), {"page": "x"}).status_code, 400)

    def test_admin_users_promote_demote_but_never_self(self):
        users = {item["email"]: item for item in self.items("admin_users")}
        self.assertTrue(users["admin@example.com"]["is_self"])
        url = reverse("admin_user", args=[self.member.pk])
        promoted = self.admin.patch(url, json.dumps({"is_staff": True}), content_type="application/json")
        self.assertEqual(promoted.json()["data"]["is_staff"], True)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_staff)
        self.admin.patch(url, json.dumps({"is_staff": False}), content_type="application/json")
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff)
        own = self.admin.patch(reverse("admin_user", args=[self.admin_user.pk]), json.dumps({"is_staff": False}), content_type="application/json")
        self.assertEqual(error_code(own), "cannot_change_own_role")
        bad = self.admin.patch(url, json.dumps({"is_staff": "yes"}), content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.admin.patch(reverse("admin_user", args=[99999]), json.dumps({"is_staff": True}), content_type="application/json").status_code, 404)


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
