import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Union, Optional, List, Any, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient, utils, functions, types
from telethon.tl.types import User, Chat, Channel
from telethon.sessions import StringSession
from contextlib import asynccontextmanager

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

# =========================================================
# ENV SETUP
# =========================================================

load_dotenv()

API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    raise RuntimeError("TELEGRAM_API_ID or TELEGRAM_API_HASH not set")

API_ID = int(API_ID)

print("PORT =", os.getenv("PORT"))

# =========================================================
# FASTAPI APP (Railway-safe)
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# =========================================================
# CORS (REQUIRED FOR FRONTEND)
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://api.varticas.com",
        "https://www.varticas.com",
        "https://telegram.varticas.com",
        "http://localhost:3000",
        "http://localhost:3001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# HEALTH ENDPOINTS (Railway probes these)
# =========================================================

@app.get("/")
async def root():
    return {"status": "ok", "service": "telegram-mcp"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _get_entity_type(entity: Any) -> str:
    """Return a normalized, human-readable entity type."""
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "supergroup" if entity.megagroup else "channel"
    if isinstance(entity, Chat):
        return "group"
    return "unknown"


def _format_entity(entity) -> Dict[str, Any]:
    """Format entity information consistently."""
    result = {"id": entity.id}
    if hasattr(entity, "title"):
        result["name"] = entity.title
        result["type"] = _get_entity_type(entity)
    elif hasattr(entity, "first_name"):
        name_parts = []
        if entity.first_name:
            name_parts.append(entity.first_name)
        if hasattr(entity, "last_name") and entity.last_name:
            name_parts.append(entity.last_name)
        result["name"] = " ".join(name_parts)
        result["type"] = "user"
        if hasattr(entity, "username") and entity.username:
            result["username"] = entity.username
        if hasattr(entity, "phone") and entity.phone:
            result["phone"] = entity.phone
    return result


def _get_sender_name(message) -> str:
    """Get sender name from a message."""
    if not message.sender:
        return "Unknown"
    if hasattr(message.sender, "title") and message.sender.title:
        return message.sender.title
    elif hasattr(message.sender, "first_name"):
        first = getattr(message.sender, "first_name", "") or ""
        last = getattr(message.sender, "last_name", "") or ""
        full = f"{first} {last}".strip()
        return full if full else "Unknown"
    return "Unknown"


def _json_serializer(obj):
    """JSON serializer for non-serializable objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


# =========================================================
# MCP HANDLER (JSON-RPC)
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
                    # ── Chat / Message Read ──
                    {
                        "name": "telegram.list_chats",
                        "description": "List recent chats (paginated, filter by type: user/group/channel)",
                        "params": {"user_id": "string", "chat_type": "string|null", "limit": "number"},
                    },
                    {
                        "name": "telegram.get_chat",
                        "description": "Get detailed info about a specific chat by ID or username",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.get_messages",
                        "description": "Get paginated messages from a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "page": "number", "page_size": "number"},
                    },
                    {
                        "name": "telegram.list_messages",
                        "description": "Get messages with optional text search and date filters (from_date/to_date: YYYY-MM-DD)",
                        "params": {"user_id": "string", "chat_id": "number|string", "limit": "number", "search_query": "string|null", "from_date": "string|null", "to_date": "string|null"},
                    },
                    {
                        "name": "telegram.search_messages",
                        "description": "Search messages in a chat by text query",
                        "params": {"user_id": "string", "chat_id": "number|string", "query": "string", "limit": "number"},
                    },
                    {
                        "name": "telegram.get_pinned_messages",
                        "description": "Get all pinned messages in a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.get_history",
                        "description": "Get full chat history up to a limit",
                        "params": {"user_id": "string", "chat_id": "number|string", "limit": "number"},
                    },
                    {
                        "name": "telegram.get_participants",
                        "description": "List all participants in a group or channel",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    # ── Message Actions ──
                    {
                        "name": "telegram.send_message",
                        "description": "Send a text message to a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "text": "string"},
                    },
                    {
                        "name": "telegram.reply_to_message",
                        "description": "Reply to a specific message in a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number", "text": "string"},
                    },
                    {
                        "name": "telegram.edit_message",
                        "description": "Edit a message you sent",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number", "new_text": "string"},
                    },
                    {
                        "name": "telegram.delete_message",
                        "description": "Delete a message by ID",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number"},
                    },
                    {
                        "name": "telegram.forward_message",
                        "description": "Forward a message from one chat to another",
                        "params": {"user_id": "string", "from_chat_id": "number|string", "message_id": "number", "to_chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.pin_message",
                        "description": "Pin a message in a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number"},
                    },
                    {
                        "name": "telegram.unpin_message",
                        "description": "Unpin a message in a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number"},
                    },
                    {
                        "name": "telegram.mark_as_read",
                        "description": "Mark all messages as read in a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.send_reaction",
                        "description": "React to a message with an emoji (e.g. 👍 ❤️ 🔥)",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number", "emoji": "string"},
                    },
                    # ── Contacts ──
                    {
                        "name": "telegram.list_contacts",
                        "description": "List all contacts in the Telegram account",
                        "params": {"user_id": "string"},
                    },
                    {
                        "name": "telegram.search_contacts",
                        "description": "Search contacts by name, username, or phone",
                        "params": {"user_id": "string", "query": "string"},
                    },
                    {
                        "name": "telegram.add_contact",
                        "description": "Add a new contact (by phone or username)",
                        "params": {"user_id": "string", "phone": "string|null", "first_name": "string", "last_name": "string", "username": "string|null"},
                    },
                    # ── Chat Management ──
                    {
                        "name": "telegram.mute_chat",
                        "description": "Mute notifications for a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.unmute_chat",
                        "description": "Unmute notifications for a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.archive_chat",
                        "description": "Archive a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    {
                        "name": "telegram.unarchive_chat",
                        "description": "Unarchive a chat",
                        "params": {"user_id": "string", "chat_id": "number|string"},
                    },
                    # ── Media ──
                    {
                        "name": "telegram.send_file",
                        "description": "Send a file (image, doc, video) to a chat",
                        "params": {"user_id": "string", "chat_id": "number|string", "file_path": "string", "caption": "string|null"},
                    },
                    {
                        "name": "telegram.download_media",
                        "description": "Download media from a chat message to a file path",
                        "params": {"user_id": "string", "chat_id": "number|string", "message_id": "number", "file_path": "string"},
                    },
                    # ── Profile / Self ──
                    {
                        "name": "telegram.get_me",
                        "description": "Get your own Telegram profile information",
                        "params": {"user_id": "string"},
                    },
                    # ── Extras ──
                    {
                        "name": "telegram.create_poll",
                        "description": "Create a native poll in a chat",
                        "params": {"user_id": "string", "chat_id": "number", "question": "string", "options": "array", "multiple_choice": "boolean", "quiz_mode": "boolean"},
                    },
                    {
                        "name": "telegram.get_user_status",
                        "description": "Get the online status of a user",
                        "params": {"user_id": "string", "target_user_id": "number|string"},
                    },
                    {
                        "name": "telegram.resolve_username",
                        "description": "Resolve a Telegram username to a user/chat ID",
                        "params": {"user_id": "string", "username": "string"},
                    },
                    {
                        "name": "telegram.search_public_chats",
                        "description": "Search for public channels, chats, or bots by name",
                        "params": {"user_id": "string", "query": "string"},
                    },
                ]
            },
        }

    # ==========================================
    # ── CHAT / READ TOOLS ──
    # ==========================================

    # ---------- telegram.list_chats ----------
    if method == "telegram.list_chats":
        user_id = params["user_id"]
        chat_type = params.get("chat_type")  # "user", "group", "channel", or None for all
        limit = int(params.get("limit", 20))
        client = await get_client(user_id)
        try:
            dialogs = await client.get_dialogs(limit=limit)
            chats = []
            for d in dialogs:
                entity = d.entity
                etype = _get_entity_type(entity)
                if chat_type and etype != chat_type:
                    continue
                name = getattr(entity, "title", None) or getattr(entity, "first_name", "Unknown")
                username = getattr(entity, "username", None)
                entry = {"id": d.id, "name": name, "type": etype, "unread": d.unread_count}
                if username:
                    entry["username"] = username
                chats.append(entry)
            return {"jsonrpc": "2.0", "id": id_, "result": chats}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_chat ----------
    if method == "telegram.get_chat":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            result = [f"ID: {entity.id}"]
            is_user = isinstance(entity, User)
            if hasattr(entity, "title"):
                result.append(f"Title: {entity.title}")
                result.append(f"Type: {_get_entity_type(entity)}")
                if getattr(entity, "username", None):
                    result.append(f"Username: @{entity.username}")
                try:
                    count = (await client.get_participants(entity, limit=0)).total
                    result.append(f"Participants: {count}")
                except Exception:
                    pass
            elif is_user:
                name = entity.first_name
                if entity.last_name:
                    name += f" {entity.last_name}"
                result.append(f"Name: {name}")
                result.append(f"Type: user")
                if entity.username:
                    result.append(f"Username: @{entity.username}")
                if entity.phone:
                    result.append(f"Phone: {entity.phone}")
                result.append(f"Bot: {'Yes' if entity.bot else 'No'}")
            return {"jsonrpc": "2.0", "id": id_, "result": "\n".join(result)}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_messages ----------
    if method == "telegram.get_messages":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        page = int(params.get("page", 1))
        page_size = int(params.get("page_size", 20))
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            offset = (page - 1) * page_size
            messages = await client.get_messages(entity, limit=page_size, add_offset=offset)
            if not messages:
                return {"jsonrpc": "2.0", "id": id_, "result": []}
            result = []
            for msg in messages:
                sender = _get_sender_name(msg)
                result.append({
                    "id": msg.id,
                    "sender": sender,
                    "date": msg.date.isoformat(),
                    "text": msg.message or "",
                    "has_media": bool(msg.media),
                    "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
                })
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.list_messages ----------
    if method == "telegram.list_messages":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        limit = int(params.get("limit", 20))
        search_query = params.get("search_query")
        from_date = params.get("from_date")
        to_date = params.get("to_date")
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            from_date_obj = None
            to_date_obj = None
            from datetime import timezone
            if from_date:
                from_date_obj = datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if to_date:
                to_date_obj = (datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1, microseconds=-1)).replace(tzinfo=timezone.utc)

            messages = []
            if search_query:
                async for msg in client.iter_messages(entity, search=search_query):
                    if to_date_obj and msg.date > to_date_obj:
                        continue
                    if from_date_obj and msg.date < from_date_obj:
                        break
                    messages.append(msg)
                    if len(messages) >= limit:
                        break
            elif from_date_obj or to_date_obj:
                if from_date_obj:
                    async for msg in client.iter_messages(entity, offset_date=from_date_obj, reverse=True):
                        if to_date_obj and msg.date > to_date_obj:
                            break
                        if msg.date < from_date_obj:
                            continue
                        messages.append(msg)
                        if len(messages) >= limit:
                            break
                else:
                    async for msg in client.iter_messages(entity, offset_date=to_date_obj + timedelta(microseconds=1)):
                        messages.append(msg)
                        if len(messages) >= limit:
                            break
            else:
                messages = await client.get_messages(entity, limit=limit)

            result = []
            for msg in messages:
                result.append({
                    "id": msg.id,
                    "sender": _get_sender_name(msg),
                    "date": msg.date.isoformat(),
                    "text": msg.message or "[Media/No text]",
                    "has_media": bool(msg.media),
                    "reply_to": msg.reply_to.reply_to_msg_id if msg.reply_to else None,
                })
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.search_messages ----------
    if method == "telegram.search_messages":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        query = params["query"]
        limit = int(params.get("limit", 10))
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            messages = await client.get_messages(entity, search=query, limit=limit)
            result = [{"id": m.id, "sender": _get_sender_name(m), "date": m.date.isoformat(), "text": m.message or ""} for m in messages]
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_pinned_messages ----------
    if method == "telegram.get_pinned_messages":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            try:
                from telethon.tl.types import InputMessagesFilterPinned
                messages = await client.get_messages(entity, filter=InputMessagesFilterPinned())
            except Exception:
                all_msgs = await client.get_messages(entity, limit=50)
                messages = [m for m in all_msgs if getattr(m, "pinned", False)]
            result = [{"id": m.id, "sender": _get_sender_name(m), "date": m.date.isoformat(), "text": m.message or "[Media]"} for m in messages]
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_history ----------
    if method == "telegram.get_history":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        limit = int(params.get("limit", 50))
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            messages = await client.get_messages(entity, limit=limit)
            result = [{"id": m.id, "sender": _get_sender_name(m), "date": m.date.isoformat(), "text": m.message or "[Media]"} for m in messages]
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_participants ----------
    if method == "telegram.get_participants":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            participants = await client.get_participants(chat_id)
            result = [
                {
                    "id": p.id,
                    "name": f"{getattr(p, 'first_name', '')} {getattr(p, 'last_name', '')}".strip(),
                    "username": getattr(p, "username", None),
                    "bot": getattr(p, "bot", False),
                }
                for p in participants
            ]
            return {"jsonrpc": "2.0", "id": id_, "result": result}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── MESSAGE ACTION TOOLS ──
    # ==========================================

    # ---------- telegram.send_message ----------
    if method == "telegram.send_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        text = params["text"]
        client = await get_client(user_id)
        try:
            dialogs = await client.get_dialogs(limit=200)
            entity = None
            for d in dialogs:
                if d.id == chat_id:
                    entity = d.entity
                    break
            if not entity:
                # fallback: try direct entity resolution
                entity = await client.get_entity(chat_id)
            await client.send_message(entity, text)
            return {"jsonrpc": "2.0", "id": id_, "result": "Message sent"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.reply_to_message ----------
    if method == "telegram.reply_to_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        text = params["text"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.send_message(entity, text, reply_to=message_id)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Replied to message {message_id}"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.edit_message ----------
    if method == "telegram.edit_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        new_text = params["new_text"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.edit_message(entity, message_id, new_text)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Message {message_id} edited"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.delete_message ----------
    if method == "telegram.delete_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.delete_messages(entity, message_id)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Message {message_id} deleted"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.forward_message ----------
    if method == "telegram.forward_message":
        user_id = params["user_id"]
        from_chat_id = params["from_chat_id"]
        message_id = int(params["message_id"])
        to_chat_id = params["to_chat_id"]
        client = await get_client(user_id)
        try:
            from_entity = await client.get_entity(from_chat_id)
            to_entity = await client.get_entity(to_chat_id)
            await client.forward_messages(to_entity, message_id, from_entity)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Message {message_id} forwarded"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.pin_message ----------
    if method == "telegram.pin_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.pin_message(entity, message_id)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Message {message_id} pinned"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.unpin_message ----------
    if method == "telegram.unpin_message":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.unpin_message(entity, message_id)
            return {"jsonrpc": "2.0", "id": id_, "result": f"Message {message_id} unpinned"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.mark_as_read ----------
    if method == "telegram.mark_as_read":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            await client.send_read_acknowledge(entity)
            return {"jsonrpc": "2.0", "id": id_, "result": "Marked as read"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.send_reaction ----------
    if method == "telegram.send_reaction":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        emoji = params["emoji"]
        client = await get_client(user_id)
        try:
            from telethon.tl.types import ReactionEmoji
            peer = await client.get_input_entity(chat_id)
            await client(functions.messages.SendReactionRequest(
                peer=peer, msg_id=message_id, big=False, reaction=[ReactionEmoji(emoticon=emoji)]
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": f"Reaction '{emoji}' sent"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── CONTACT TOOLS ──
    # ==========================================

    # ---------- telegram.list_contacts ----------
    if method == "telegram.list_contacts":
        user_id = params["user_id"]
        client = await get_client(user_id)
        try:
            result = await client(functions.contacts.GetContactsRequest(hash=0))
            contacts = []
            for u in result.users:
                name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
                contacts.append({
                    "id": u.id,
                    "name": name,
                    "username": getattr(u, "username", None),
                    "phone": getattr(u, "phone", None),
                })
            return {"jsonrpc": "2.0", "id": id_, "result": contacts}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.search_contacts ----------
    if method == "telegram.search_contacts":
        user_id = params["user_id"]
        query = params["query"]
        client = await get_client(user_id)
        try:
            result = await client(functions.contacts.SearchRequest(q=query, limit=50))
            contacts = []
            for u in result.users:
                name = f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
                contacts.append({
                    "id": u.id,
                    "name": name,
                    "username": getattr(u, "username", None),
                    "phone": getattr(u, "phone", None),
                })
            return {"jsonrpc": "2.0", "id": id_, "result": contacts}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.add_contact ----------
    if method == "telegram.add_contact":
        user_id = params["user_id"]
        phone = params.get("phone") or ""
        first_name = params.get("first_name", "")
        last_name = params.get("last_name", "")
        username = params.get("username") or ""
        client = await get_client(user_id)
        try:
            if not phone and not username:
                return {"jsonrpc": "2.0", "id": id_, "error": "Either phone or username must be provided"}
            if username:
                username_clean = username.lstrip("@")
                resolve_result = await client(functions.contacts.ResolveUsernameRequest(username=username_clean))
                if not resolve_result.users:
                    return {"jsonrpc": "2.0", "id": id_, "error": f"User @{username_clean} not found"}
                u = resolve_result.users[0]
                from telethon.tl.types import InputUser
                await client(functions.contacts.AddContactRequest(
                    id=InputUser(user_id=u.id, access_hash=u.access_hash),
                    first_name=first_name, last_name=last_name, phone="",
                ))
                return {"jsonrpc": "2.0", "id": id_, "result": f"Contact @{username_clean} added"}
            else:
                from telethon.tl.types import InputPhoneContact
                result = await client(functions.contacts.ImportContactsRequest(contacts=[
                    InputPhoneContact(client_id=0, phone=phone, first_name=first_name, last_name=last_name)
                ]))
                if result.imported:
                    return {"jsonrpc": "2.0", "id": id_, "result": "Contact added"}
                return {"jsonrpc": "2.0", "id": id_, "error": "Contact not added"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── CHAT MANAGEMENT TOOLS ──
    # ==========================================

    # ---------- telegram.mute_chat ----------
    if method == "telegram.mute_chat":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            from telethon.tl.types import InputPeerNotifySettings
            peer = await client.get_entity(chat_id)
            await client(functions.account.UpdateNotifySettingsRequest(
                peer=peer, settings=InputPeerNotifySettings(mute_until=2**31 - 1)
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": f"Chat {chat_id} muted"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.unmute_chat ----------
    if method == "telegram.unmute_chat":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            from telethon.tl.types import InputPeerNotifySettings
            peer = await client.get_entity(chat_id)
            await client(functions.account.UpdateNotifySettingsRequest(
                peer=peer, settings=InputPeerNotifySettings(mute_until=0)
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": f"Chat {chat_id} unmuted"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.archive_chat ----------
    if method == "telegram.archive_chat":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            peer = utils.get_input_peer(entity)
            await client(functions.folders.EditPeerFoldersRequest(
                folder_peers=[types.InputFolderPeer(peer=peer, folder_id=1)]
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": f"Chat {chat_id} archived"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.unarchive_chat ----------
    if method == "telegram.unarchive_chat":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            peer = utils.get_input_peer(entity)
            await client(functions.folders.EditPeerFoldersRequest(
                folder_peers=[types.InputFolderPeer(peer=peer, folder_id=0)]
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": f"Chat {chat_id} unarchived"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── MEDIA TOOLS ──
    # ==========================================

    # ---------- telegram.send_file ----------
    if method == "telegram.send_file":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        file_path = params["file_path"]
        caption = params.get("caption")
        client = await get_client(user_id)
        try:
            if not os.path.isfile(file_path):
                return {"jsonrpc": "2.0", "id": id_, "error": f"File not found: {file_path}"}
            if not os.access(file_path, os.R_OK):
                return {"jsonrpc": "2.0", "id": id_, "error": f"File not readable: {file_path}"}
            entity = await client.get_entity(chat_id)
            await client.send_file(entity, file_path, caption=caption)
            return {"jsonrpc": "2.0", "id": id_, "result": f"File sent to {chat_id}"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.download_media ----------
    if method == "telegram.download_media":
        user_id = params["user_id"]
        chat_id = params["chat_id"]
        message_id = int(params["message_id"])
        file_path = params["file_path"]
        client = await get_client(user_id)
        try:
            entity = await client.get_entity(chat_id)
            msg = await client.get_messages(entity, ids=message_id)
            if not msg or not msg.media:
                return {"jsonrpc": "2.0", "id": id_, "error": "No media found in this message"}
            dir_path = os.path.dirname(file_path) or "."
            if not os.access(dir_path, os.W_OK):
                return {"jsonrpc": "2.0", "id": id_, "error": f"Directory not writable: {dir_path}"}
            await client.download_media(msg, file=file_path)
            if not os.path.isfile(file_path):
                return {"jsonrpc": "2.0", "id": id_, "error": "Download failed: file not created"}
            return {"jsonrpc": "2.0", "id": id_, "result": f"Downloaded to {file_path}"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── PROFILE / SELF TOOLS ──
    # ==========================================

    # ---------- telegram.get_me ----------
    if method == "telegram.get_me":
        user_id = params["user_id"]
        client = await get_client(user_id)
        try:
            me = await client.get_me()
            return {"jsonrpc": "2.0", "id": id_, "result": _format_entity(me)}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ==========================================
    # ── EXTRA TOOLS ──
    # ==========================================

    # ---------- telegram.create_poll ----------
    if method == "telegram.create_poll":
        user_id = params["user_id"]
        chat_id = int(params["chat_id"])
        question = params["question"]
        options = params["options"]
        multiple_choice = bool(params.get("multiple_choice", False))
        quiz_mode = bool(params.get("quiz_mode", False))
        client = await get_client(user_id)
        try:
            import random
            from telethon.tl.types import InputMediaPoll, Poll, PollAnswer, TextWithEntities
            entity = await client.get_entity(chat_id)
            if len(options) < 2 or len(options) > 10:
                return {"jsonrpc": "2.0", "id": id_, "error": "Poll must have 2–10 options"}
            poll = Poll(
                id=random.randint(0, 2**63 - 1),
                question=TextWithEntities(text=question, entities=[]),
                answers=[PollAnswer(text=TextWithEntities(text=opt, entities=[]), option=bytes([i])) for i, opt in enumerate(options)],
                multiple_choice=multiple_choice,
                quiz=quiz_mode,
                public_voters=True,
            )
            await client(functions.messages.SendMediaRequest(
                peer=entity, media=InputMediaPoll(poll=poll),
                message="", random_id=random.randint(0, 2**63 - 1),
            ))
            return {"jsonrpc": "2.0", "id": id_, "result": "Poll created"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.get_user_status ----------
    if method == "telegram.get_user_status":
        user_id = params["user_id"]
        target_user_id = params["target_user_id"]
        client = await get_client(user_id)
        try:
            user = await client.get_entity(target_user_id)
            return {"jsonrpc": "2.0", "id": id_, "result": str(user.status)}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.resolve_username ----------
    if method == "telegram.resolve_username":
        user_id = params["user_id"]
        username = params["username"]
        client = await get_client(user_id)
        try:
            result = await client(functions.contacts.ResolveUsernameRequest(username=username.lstrip("@")))
            if result.users:
                return {"jsonrpc": "2.0", "id": id_, "result": _format_entity(result.users[0])}
            if result.chats:
                return {"jsonrpc": "2.0", "id": id_, "result": _format_entity(result.chats[0])}
            return {"jsonrpc": "2.0", "id": id_, "error": "Username not resolved"}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    # ---------- telegram.search_public_chats ----------
    if method == "telegram.search_public_chats":
        user_id = params["user_id"]
        query = params["query"]
        client = await get_client(user_id)
        try:
            result = await client(functions.contacts.SearchRequest(q=query, limit=20))
            chats = [_format_entity(u) for u in result.users]
            chats += [_format_entity(c) for c in result.chats]
            return {"jsonrpc": "2.0", "id": id_, "result": chats}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": id_, "error": str(e)}

    return {
        "jsonrpc": "2.0",
        "id": id_,
        "error": f"Unknown method: {method}",
    }

# =========================================================
# MCP ENDPOINT
# =========================================================

@app.post("/mcp")
async def mcp(req: Request):
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

    return {"status": "connected", "user_id": user_id}
