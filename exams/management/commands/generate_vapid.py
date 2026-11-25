import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.core.management.base import BaseCommand


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Command(BaseCommand):
    help = "Gera o par de chaves VAPID (Web Push) para o .env."

    def handle(self, *args, **options):
        key = ec.generate_private_key(ec.SECP256R1())
        raw_private = key.private_numbers().private_value.to_bytes(32, "big")
        raw_public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64(raw_public)}")
        self.stdout.write(f"VAPID_PRIVATE_KEY={b64(raw_private)}")
