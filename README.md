Telegram MCP (User-based, Multi-User)

This is a Telegram MCP (Model Context Protocol) server that allows multiple users to connect their Telegram user accounts using OTP authentication and then interact with Telegram via MCP tools.

It follows the same MCP pattern as Discord and GitHub MCPs and is designed to be deployed on platforms like Railway.

🚀 Features

✅ Telegram user account integration (not bot)

✅ Multi-user support using user_id

✅ MCP-compatible /mcp endpoint

✅ OTP-based Telegram login

✅ Tools for listing chats, sending messages, and searching messages

✅ Ready for Varticas / agent integration

🌐 Base URL
Local
http://127.0.0.1:8000

Production (example)
https://telegram-mcp.up.railway.app

📌 Important Concepts
user_id

This is your app’s user identifier (e.g. Varticas user ID)

Telegram’s internal user ID is never used

Every request must include the same user_id

🔐 Authentication Flow (Required Once Per User)

Telegram does not use OAuth.
Authentication is done via phone number + OTP.

1️⃣ Send OTP (Login)

Endpoint

GET /auth/telegram/login


Query Parameters

Param	Type	Required	Description
user_id	string	✅	Your app’s user ID
phone	string	✅	Telegram phone number with country code

Example

GET /auth/telegram/login?user_id=user123&phone=+919876543210


Response

{
  "status": "code_sent"
}


📲 User will receive an OTP on Telegram.

2️⃣ Verify OTP

Endpoint

GET /auth/telegram/verify


Query Parameters

Param	Type	Required	Description
user_id	string	✅	Same user ID
phone	string	✅	Same phone number
code	string	✅	OTP received

Example

GET /auth/telegram/verify?user_id=user123&phone=+919876543210&code=12345


Success Response

{
  "status": "connected",
  "user_id": "user123"
}


✅ Telegram session is now stored
✅ User can call MCP tools

🔗 MCP Endpoint

All MCP calls go to:

POST /mcp


Content-Type:

application/json

🧰 MCP Tool Discovery
tools/list

Returns all supported tools.

Request

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}


Response

{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      { "name": "telegram.list_chats" },
      { "name": "telegram.send_message" },
      { "name": "telegram.search_messages" }
    ]
  }
}

📬 MCP Tools
🟦 telegram.list_chats

Returns recent Telegram chats for the user.

Parameters

Param	Type	Required	Description
user_id	string	✅	Connected user ID

Request

{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "telegram.list_chats",
  "params": {
    "user_id": "user123"
  }
}


Response

{
  "jsonrpc": "2.0",
  "id": 2,
  "result": [
    { "id": 123456789, "name": "Saved Messages" },
    { "id": 987654321, "name": "Friends Group" }
  ]
}

🟦 telegram.send_message

Send a message to a Telegram chat.

Parameters

Param	Type	Required	Description
user_id	string	✅	Connected user ID
chat_id	number	✅	Telegram chat ID
text	string	✅	Message text

Request

{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "telegram.send_message",
  "params": {
    "user_id": "user123",
    "chat_id": 123456789,
    "text": "Hello from Telegram MCP 🚀"
  }
}


Response

{
  "jsonrpc": "2.0",
  "id": 3,
  "result": "Message sent"
}

🟦 telegram.search_messages

Search messages in a chat.

Parameters

Param	Type	Required	Description
user_id	string	✅	Connected user ID
chat_id	number	✅	Telegram chat ID
query	string	✅	Search text

Request

{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "telegram.search_messages",
  "params": {
    "user_id": "user123",
    "chat_id": 123456789,
    "query": "Hello"
  }
}


Response

{
  "jsonrpc": "2.0",
  "id": 4,
  "result": [
    { "id": 101, "text": "Hello from Telegram MCP 🚀" }
  ]
}

⚠️ Important Notes

OTP expires quickly (≈ 60–90 seconds)

Only one active OTP per user

Do not restart server during OTP flow (in-memory state)

For production, move session storage to Redis or DB

🛠 Deployment Notes (Railway)

Use /mcp as the MCP endpoint

Set environment variables:

TELEGRAM_API_ID
TELEGRAM_API_HASH


Start command:

python -m uvicorn main:app --host 0.0.0.0 --port $PORT

✅ Status

This MCP is:

Agent-ready

Multi-user safe

Production-uitable (with persistent storage)

Compatible with Varticas MCP architecture# Telegram_MCP
