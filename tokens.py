# tokens.py
# Storage strategy:
#   - Telegram session strings  → Redis (persistent, no expiry)
#   - Phone code hash + OTP ts  → Redis (auto-expires after OTP_EXPIRY_SECONDS)
#   - Auth clients (Telethon)   → In-memory only (objects cannot be serialised)

import os
import time
import redis
from dotenv import load_dotenv

load_dotenv()

OTP_EXPIRY_SECONDS = 90

# ── Redis connection ──────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL is not set in environment variables")

# decode_responses=True so all values come back as str, not bytes
_redis: redis.Redis = redis.from_url(REDIS_URL, decode_responses=True)

# Key prefixes
_SESSION_PREFIX   = "tg:session:"       # tg:session:<user_id>
_CODE_HASH_PREFIX = "tg:code_hash:"     # tg:code_hash:<user_id>
_CODE_TS_PREFIX   = "tg:code_ts:"       # tg:code_ts:<user_id>  (unix float as str)

# ── In-memory store (auth clients only) ──────────────────────────────────────

_TELEGRAM_AUTH_CLIENTS: dict = {}


# ── Auth client (in-memory, not Redis-able) ───────────────────────────────────

def save_auth_client(user_id: str, client) -> None:
    _TELEGRAM_AUTH_CLIENTS[user_id] = client


def get_auth_client(user_id: str):
    return _TELEGRAM_AUTH_CLIENTS.get(user_id)


def clear_auth_client(user_id: str) -> None:
    _TELEGRAM_AUTH_CLIENTS.pop(user_id, None)


# ── Telegram session string ───────────────────────────────────────────────────

def save_telegram_session(user_id: str, session_string: str) -> None:
    """Persist the Telethon StringSession to Redis (no expiry)."""
    _redis.set(f"{_SESSION_PREFIX}{user_id}", session_string)


def get_telegram_session(user_id: str) -> str | None:
    """Retrieve the Telethon StringSession from Redis, or None."""
    return _redis.get(f"{_SESSION_PREFIX}{user_id}")


def delete_telegram_session(user_id: str) -> None:
    """Remove a session (e.g. on logout)."""
    _redis.delete(f"{_SESSION_PREFIX}{user_id}")


# ── Phone code hash (OTP flow) ────────────────────────────────────────────────

def save_phone_code_hash(user_id: str, phone_code_hash: str) -> None:
    """Store the phone_code_hash in Redis and record the timestamp.

    Both keys are given a TTL slightly longer than OTP_EXPIRY_SECONDS so Redis
    cleans them up automatically even if clear_phone_code_hash is never called.
    """
    ttl = OTP_EXPIRY_SECONDS + 30  # small grace period
    _redis.setex(f"{_CODE_HASH_PREFIX}{user_id}", ttl, phone_code_hash)
    _redis.setex(f"{_CODE_TS_PREFIX}{user_id}", ttl, str(time.time()))


def get_phone_code_hash(user_id: str) -> str | None:
    """Retrieve the stored phone_code_hash, or None if absent/expired."""
    return _redis.get(f"{_CODE_HASH_PREFIX}{user_id}")


def clear_phone_code_hash(user_id: str) -> None:
    """Explicitly remove the OTP hash and timestamp from Redis."""
    _redis.delete(
        f"{_CODE_HASH_PREFIX}{user_id}",
        f"{_CODE_TS_PREFIX}{user_id}",
    )


def is_otp_expired(user_id: str) -> bool:
    """Return True if the OTP was never issued, or has exceeded OTP_EXPIRY_SECONDS."""
    ts_str = _redis.get(f"{_CODE_TS_PREFIX}{user_id}")
    if not ts_str:
        return True  # key missing or already expired by Redis TTL
    try:
        return (time.time() - float(ts_str)) > OTP_EXPIRY_SECONDS
    except (ValueError, TypeError):
        return True
