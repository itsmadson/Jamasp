import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from jamasp.config import get_settings

NONCE_BYTES = 12


def encrypt(plaintext: str, key: bytes) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plaintext.encode(), None)


def decrypt(ciphertext: bytes, key: bytes) -> str:
    nonce, body = ciphertext[:NONCE_BYTES], ciphertext[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, body, None).decode()
    except InvalidTag as exc:
        raise ValueError("decryption failed: wrong key or tampered ciphertext") from exc


def key_from_settings() -> bytes:
    raw = get_settings().secret_key
    if not raw:
        raise RuntimeError("JAMASP_SECRET_KEY is not set; refusing to start")
    key = base64.urlsafe_b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("JAMASP_SECRET_KEY must decode to 32 bytes")
    return key
