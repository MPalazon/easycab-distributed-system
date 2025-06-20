import base64, secrets, hashlib
from cryptography.fernet import Fernet, InvalidToken
TOKEN_HEX_LENGTH = 32
def _derive_key(key_str: str) -> bytes: return base64.urlsafe_b64encode(hashlib.sha256(key_str.encode('utf-8')).digest())
def generate_token() -> str: return secrets.token_hex(TOKEN_HEX_LENGTH // 2)
def generate_session_key() -> str: return secrets.token_hex(32)
def encrypt(data: bytes, key_str: str) -> bytes:
    try: return Fernet(_derive_key(key_str)).encrypt(data)
    except Exception: return b''
def decrypt(encrypted_data: bytes, key_str: str) -> bytes:
    try: return Fernet(_derive_key(key_str)).decrypt(encrypted_data)
    except (InvalidToken, TypeError, ValueError): return b''