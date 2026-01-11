import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from telethon import TelegramClient
from telethon.sessions import StringSession

from telegram_api import get_client
from tokens import (
    save_telegram_session,
    save_phone_code_hash,
    save_auth_client,
    get_auth_client,
    clear_auth_client,
    get_phone_code_hash,
    clear_phone_code_hash,
    is_otp_expired,
)
print("PORT =", os.getenv("PORT"))


load_dotenv()


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # App is ready immediately
    yield

app = FastAPI(lifespan=lifespan)

print("PORT =", os.getenv("PORT"))


load_dotenv()
API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")


# =========================================================
# MCP HANDLER (shared logic)
# =========================================================
async def handle_mcp(req: Request):
    body = await req.json()
    method = body.get("method")
    id_ = body.get("id")
    params = body.get("params", {})

    # ---------- tools/list ----------
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": {
                "tools": [
                    {"name": "telegram.list_chats"},
                    {"name": "telegram.send_message"},
                    {"name": "telegram.search_messages"},
                ]
            },
        }

    # ---------- telegram.list_chats ----------
    if method == "telegram.list_chats":
        user_id = params["user_id"]
        client = await get_client(user_id)

        dialogs = await client.get_dialogs(limit=20)
        chats = [{"id": d.id, "name": d.name} for d in dialogs]

        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": chats,
        }

    # ---------- telegram.send_message ----------
    if method == "telegram.send_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        text = params["text"]

        client = await get_client(user_id)
        await client.send_message(chat_id, text)

        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": "Message sent",
        }

    # ---------- telegram.search_messages ----------
    if method == "telegram.search_messages":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        query = params["query"]

        client = await get_client(user_id)
        messages = await client.get_messages(chat_id, search=query, limit=10)

        return {
            "jsonrpc": "2.0",
            "id": id_,
            "result": [{"id": m.id, "text": m.text} for m in messages],
        }

    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": "Unknown method",
    }


# =========================================================
# MCP ENDPOINTS
# =========================================================

@app.get("/")
async def root():
    return {"status": "ok"}



# Primary MCP endpoint (USE THIS IN RAILWAY / VARTICAS)
@app.post("/mcp")
async def mcp(req: Request):
    return await handle_mcp(req)


# Optional backward compatibility (safe to remove later)
@app.post("/")
async def root(req: Request):
    return await handle_mcp(req)


# =========================================================
# TELEGRAM AUTH FLOW
# =========================================================

@app.get("/auth/telegram/login")
async def telegram_login(user_id: str, phone: str):
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    sent = await client.send_code_request(phone)

    save_phone_code_hash(user_id, sent.phone_code_hash)
    save_auth_client(user_id, client)

    return {"status": "code_sent"}


@app.get("/auth/telegram/verify")
async def telegram_verify(user_id: str, phone: str, code: str):
    if is_otp_expired(user_id):
        return {"error": "OTP expired. Please request again."}

    client = get_auth_client(user_id)
    if not client:
        return {"error": "Auth session lost. Please login again."}

    phone_code_hash = get_phone_code_hash(user_id)
    if not phone_code_hash:
        return {"error": "No active OTP session."}

    try:
        await client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )
    except Exception as e:
        return {"error": str(e)}

    session_string = client.session.save()
    save_telegram_session(user_id, session_string)

    clear_phone_code_hash(user_id)
    clear_auth_client(user_id)

    return {
        "status": "connected",
        "user_id": user_id,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}

