# tokens.py
import time

_TELEGRAM_SESSIONS = {}
_TELEGRAM_CODE_HASH = {}
_TELEGRAM_CODE_TIME = {}

# 🔥 NEW
_TELEGRAM_AUTH_CLIENTS = {}

OTP_EXPIRY_SECONDS = 90


def save_auth_client(user_id: str, client):
    _TELEGRAM_AUTH_CLIENTS[user_id] = client


def get_auth_client(user_id: str):
    return _TELEGRAM_AUTH_CLIENTS.get(user_id)


def clear_auth_client(user_id: str):
    _TELEGRAM_AUTH_CLIENTS.pop(user_id, None)


def save_telegram_session(user_id: str, session_string: str):
    _TELEGRAM_SESSIONS[user_id] = session_string


def get_telegram_session(user_id: str):
    return _TELEGRAM_SESSIONS.get(user_id)


def save_phone_code_hash(user_id: str, phone_code_hash: str):
    _TELEGRAM_CODE_HASH[user_id] = phone_code_hash
    _TELEGRAM_CODE_TIME[user_id] = time.time()


def get_phone_code_hash(user_id: str):
    return _TELEGRAM_CODE_HASH.get(user_id)


def clear_phone_code_hash(user_id: str):
    _TELEGRAM_CODE_HASH.pop(user_id, None)
    _TELEGRAM_CODE_TIME.pop(user_id, None)


def is_otp_expired(user_id: str):
    sent_time = _TELEGRAM_CODE_TIME.get(user_id)
    if not sent_time:
        return True
    return (time.time() - sent_time) > OTP_EXPIRY_SECONDS
