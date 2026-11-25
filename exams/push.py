"""Web Push to the owner's installed app (RFC 8291 payload encryption + RFC 8292 VAPID).

Built on http_ece and py-vapid (the same primitives pywebpush uses) with a stdlib HTTP call,
to avoid pulling aiohttp/requests. Best effort: notifications never block or fail a request,
and the in-app lists stay the source of truth.
"""

import base64
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import http_ece
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.db import connection
from py_vapid import Vapid

from .models import PushSubscription

logger = logging.getLogger("exams.outbox")
TTL_SECONDS = 300


def b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def push_enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_one(subscription: dict, payload: bytes) -> int:
    """POST one encrypted message; returns the push service HTTP status."""
    body = http_ece.encrypt(
        payload, private_key=ec.generate_private_key(ec.SECP256R1()),
        dh=b64decode(subscription["p256dh"]), auth_secret=b64decode(subscription["auth"]), version="aes128gcm",
    )
    endpoint = urlsplit(subscription["endpoint"])
    vapid = Vapid.from_raw(b64decode(settings.VAPID_PRIVATE_KEY))
    headers = vapid.sign({
        "aud": f"{endpoint.scheme}://{endpoint.netloc}", "sub": settings.VAPID_SUBJECT,
        "exp": int(time.time()) + 12 * 3600,
    })
    headers.update({"Content-Encoding": "aes128gcm", "TTL": str(TTL_SECONDS), "Urgency": "high"})
    request = urllib.request.Request(subscription["endpoint"], data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def deliver(subscriptions: list[dict], payload: bytes) -> None:
    """Runs in its own background thread: send, forget gone subscriptions, release the DB."""
    try:
        gone = []
        for subscription in subscriptions:
            try:
                status = send_one(subscription, payload)
            except (OSError, ValueError) as error:
                logger.warning("push failed: %s", type(error).__name__)
                continue
            if status in (404, 410):
                gone.append(subscription["endpoint"])
        if gone:
            PushSubscription.objects.filter(endpoint__in=gone).delete()
    finally:
        # Close only the connection this background thread opened (never a request's own).
        if threading.current_thread() is not threading.main_thread():
            connection.close()


def notify_owner(user, title: str, body: str, url: str) -> None:
    """Fire-and-forget. Message text is generic: never document titles or recipient details."""
    if not push_enabled():
        return
    subscriptions = list(PushSubscription.objects.filter(user=user).values("endpoint", "p256dh", "auth"))
    if not subscriptions:
        return
    payload = json.dumps({"title": title, "body": body, "url": url}).encode()
    threading.Thread(target=deliver, args=(subscriptions, payload), daemon=True).start()
