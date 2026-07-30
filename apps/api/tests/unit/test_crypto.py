import os

import pytest

from jamasp.security.crypto import decrypt, encrypt


def test_roundtrip_recovers_plaintext():
    key = os.urandom(32)
    secret = "postgresql://user:p@ssw0rd@db.internal:5432/hr"
    assert decrypt(encrypt(secret, key), key) == secret


def test_ciphertext_differs_across_calls():
    key = os.urandom(32)
    assert encrypt("same", key) != encrypt("same", key)


def test_wrong_key_raises():
    blob = encrypt("secret", os.urandom(32))
    with pytest.raises(ValueError):
        decrypt(blob, os.urandom(32))


def test_tampered_ciphertext_raises():
    key = os.urandom(32)
    blob = bytearray(encrypt("secret", key))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError):
        decrypt(bytes(blob), key)
