import secrets
from hashlib import sha256

from cryptography.fernet import Fernet
from django.core.management.base import BaseCommand
from django.core.management.utils import get_random_secret_key


class Command(BaseCommand):
    help = "Gera as chaves iniciais e um código de convite para a primeira conta."

    def handle(self, *args, **options):
        token = secrets.token_urlsafe(32)
        self.stdout.write(f"VAULT_NAMESPACE={secrets.token_hex(24)!r}")
        self.stdout.write(f"DJANGO_SECRET_KEY={get_random_secret_key()!r}")
        self.stdout.write(f"TOTP_ENCRYPTION_KEY={Fernet.generate_key().decode()!r}")
        self.stdout.write(f"BOOTSTRAP_INVITE_DIGEST='{sha256(token.encode()).hexdigest()}'")
        self.stdout.write(f"Código de convite inicial para /cadastro/: {token}")
