---
description: Instructions for using Telegram tools to manage chats, messages, contacts, and media.
name: Telegram MCP Skill
---

# Telegram Tool Usage Guide

You are equipped with tools to interact with Telegram via the Telegram MCP (Model Context Protocol). This document provides architectural context and guidelines for the LLM agent on how to reason about which tool to call and when.

## Available Tool Domains

The Telegram MCP exposes various operations categorized into the following domains:

- **Chat / Message Read**: Exploring and fetching chat histories.
  - `telegram.list_chats`, `telegram.get_chat`, `telegram.get_messages`, `telegram.list_messages`, `telegram.search_messages`, `telegram.get_pinned_messages`, `telegram.get_history`, `telegram.get_participants`
- **Message Actions**: Managing outgoing and existing messages in chats.
  - `telegram.send_message`, `telegram.reply_to_message`, `telegram.edit_message`, `telegram.delete_message`, `telegram.forward_message`, `telegram.pin_message`, `telegram.unpin_message`, `telegram.mark_as_read`, `telegram.send_reaction`
- **Contacts**: Managing the user's contacts list.
  - `telegram.list_contacts`, `telegram.search_contacts`, `telegram.add_contact`
- **Chat Management**: Settings related to chat interactions.
  - `telegram.mute_chat`, `telegram.unmute_chat`, `telegram.archive_chat`, `telegram.unarchive_chat`
- **Media**: Sending and downloading media.
  - `telegram.send_file`, `telegram.download_media`
- **Extras & Profile**: Profile info, resolving statuses, and public searches.
  - `telegram.get_me`, `telegram.create_poll`, `telegram.get_user_status`, `telegram.resolve_username`, `telegram.search_public_chats`

## How to Decide Which Tool to Call

When a user asks you to interact with Telegram, follow this reasoning process:

### 1. Identify the Objective
Determine the user's overarching goal:
- **Reading activity**: Is the user trying to see their messages or unread chats? Use Chat / Message Read tools (e.g., `telegram.list_chats`, `telegram.get_messages`).
- **Initiating/Modifying interaction**: Is the user trying to reply, react, or send something? Use Message Actions.
- **Finding people/groups**: Use `telegram.resolve_username` or `telegram.search_public_chats` to find a `chat_id` before interacting with a new entity.

### 2. Parameter Resolution (Crucial)
Almost every tool requires two common parameters:
- `user_id`: The ID of the authenticated user sending the request. This represents the session.
- `chat_id`: The target entity (user, group, or channel). This can be a numeric ID (e.g., `123456789`) or a string username (e.g., `@example_user`). If you don't know the `chat_id`, you must resolve it first.

#### Resolving Chat IDs workflow:
1. If the user mentions a specific user (e.g., "send a message to Bob"), try to resolve it by searching contacts (`telegram.search_contacts`) or finding recent chats (`telegram.list_chats`). 
2. If given a username (e.g., "@Bob123"), you can use `telegram.resolve_username`.
3. Once the target's numeric `chat_id` is found, proceed with the actual action (like `telegram.send_message`).

### 3. Execution Flow Examples

**Scenario 1: Sending a message to someone specific**
*User Prompt*: "Tell Alice I will be 10 minutes late."
*Agent Reasoning*:
1. I need to find Alice's `chat_id`. I should call `telegram.search_contacts` with query="Alice".
2. From the contact search result, I extract Alice's ID (e.g., `987654321`).
3. Now, I call `telegram.send_message` with `chat_id=987654321` and `text="I will be 10 minutes late."`.

**Scenario 2: Searching recent messages in a group**
*User Prompt*: "Did anyone mention 'project deadline' in the Dev Group recently?"
*Agent Reasoning*:
1. I need the `chat_id` for "Dev Group". I call `telegram.list_chats` to parse the ID.
2. Once the group's ID is acquired, I call `telegram.search_messages` with `chat_id=<Dev Group ID>`, `query="project deadline"`, and `limit=10`.
3. I synthesize the returned messages and inform the user.

## Error Handling
- **Authentication**: If you receive an error about Telegram not being connected or a missing session, tell the user they need to log in to Telegram via the main app portal.
- **Entity Not Found/Invalid `chat_id`**: If a tool fails indicating it cannot find the peer, fall back to resolving the peer again—try `telegram.resolve_username` or refresh the chat list using `telegram.list_chats`. Telegram sometimes needs to "see" an entity in the recent dialogs before it can send to them by ID.
