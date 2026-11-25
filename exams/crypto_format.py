import base64
import binascii
import re
from hashlib import sha256

from cryptography.hazmat.primitives.asymmetric import ec


def decode_token(value, size):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Formato inválido.")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except binascii.Error as error:
        raise ValueError("Formato inválido.") from error
    if len(raw) != size or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
        raise ValueError("Formato inválido.")
    return raw


def public_key_bytes(value):
    raw = decode_token(value, 65)
    if raw[0] != 4:
        raise ValueError("Formato de chave inválido.")
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    return raw


def fingerprint(value):
    return sha256(public_key_bytes(value)).hexdigest()[:16]


def wrapped_key_bytes(value):
    raw = decode_token(value, 61)
    if raw[0] != 1:
        raise ValueError("Versão de chave inválida.")
    return raw


def sealed_blob(value, max_bytes):
    """AES-GCM envelope produced in the browser (0x01 | iv | ciphertext+tag), of bounded size."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Formato inválido.")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except binascii.Error as error:
        raise ValueError("Formato inválido.") from error
    if raw[:1] != b"\x01" or not 29 <= len(raw) <= max_bytes:
        raise ValueError("Formato inválido.")
    return raw


def comparison_code(recipient_key, nonce):
    """6 digits both screens show for a @handle request: SHA-256(public key || server nonce).
    The server-chosen nonce stops an attacker from grinding keys to match a code it has seen."""
    digest = sha256(public_key_bytes(recipient_key) + nonce.encode()).digest()
    return f"{int.from_bytes(digest[:4], 'big') % 1_000_000:06d}"
