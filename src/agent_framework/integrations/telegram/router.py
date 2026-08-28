"""Telegram message routing, session mapping, MarkdownV2 escaping, and chunking utilities."""

import re


def generate_telegram_session_id(
    chat_id: int,
    user_id: int,
    chat_type: str = "private",
) -> str:
    """Generate an isolated session identifier for Telegram contexts.

    Formats:
        - Private: telegram:private:<user_id>
        - Group:   telegram:group:<chat_id>:user:<user_id>
        - Channel: telegram:channel:<chat_id>
    """
    if chat_type == "private":
        return f"telegram:private:{user_id}"
    if chat_type in ("group", "supergroup"):
        return f"telegram:group:{chat_id}:user:{user_id}"
    if chat_type == "channel":
        return f"telegram:channel:{chat_id}"
    return f"telegram:chat:{chat_id}:user:{user_id}"


def escape_markdown_v2(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2 formatting.

    Preserves code blocks and inline code while escaping reserved punctuation
    outside of code fences: _ * [ ] ( ) ~ > # + - = | { } . !
    """
    if not text:
        return ""

    # Reserved characters in MarkdownV2: _ * [ ] ( ) ~ ` > # + - = | { } . !
    # We escape all reserved characters outside of code blocks
    special_chars = r"_*[]()~>#+-=|{}.!"
    escape_pattern = re.compile(rf"([\\{re.escape(special_chars)}])")

    # Split text into code blocks and normal text to avoid escaping syntax inside code
    parts = re.split(r"(```[\s\S]*?```|`[^`]*?`)", text)
    escaped_parts: list[str] = []

    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            escaped_parts.append(part)
        elif part.startswith("`") and part.endswith("`"):
            escaped_parts.append(part)
        else:
            escaped_parts.append(escape_pattern.sub(r"\\\1", part))

    return "".join(escaped_parts)


def extract_clean_telegram_text(text: str, bot_username: str | None = None) -> str:
    """Strip bot username mention (e.g. @MyBot) and leading command triggers."""
    if not text:
        return ""
    cleaned = text
    if bot_username:
        # Case-insensitive remove of @bot_username
        cleaned = re.sub(rf"@{re.escape(bot_username)}\b", "", cleaned, flags=re.IGNORECASE)

    # Strip command prefix if present (e.g., /ask hello -> hello)
    if cleaned.startswith("/"):
        parts = cleaned.split(maxsplit=1)
        if len(parts) > 1:
            cleaned = parts[1]
        else:
            cleaned = ""

    return cleaned.strip()


def should_process_telegram_message(
    is_bot: bool,
    chat_id: int,
    chat_type: str,
    text: str,
    bot_username: str | None = None,
    allowed_chats: list[int] | None = None,
    require_mention: bool = True,
) -> bool:
    """Evaluate whether an incoming Telegram update should trigger agent processing."""
    # 1. Ignore bot messages
    if is_bot:
        return False

    # 2. Check chat whitelist
    if allowed_chats and chat_id not in allowed_chats:
        return False

    # 3. Private DMs are always processed
    if chat_type == "private":
        return True

    # 4. Group / Supergroup checks
    if chat_type in ("group", "supergroup"):
        if not require_mention:
            return True
        if bot_username and f"@{bot_username.lower()}" in text.lower():
            return True
        if text.startswith("/"):
            return True
        return False

    return True


def split_telegram_message(text: str, max_chunk_size: int = 4096) -> list[str]:
    """Safely split long responses into Telegram-compliant chunks (<= 4096 characters).

    Preserves code block fences across chunk boundaries.
    """
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]

    chunks: list[str] = []
    remaining = text
    in_code_block = False
    code_block_lang = ""

    while remaining:
        if len(remaining) <= max_chunk_size:
            chunks.append(remaining)
            break

        effective_limit = max_chunk_size - (10 if in_code_block else 0)
        target_chunk = remaining[:effective_limit]

        # Prefer splitting on paragraph breaks, line breaks, sentence ends, or spaces
        split_idx = -1
        for delimiter in ("\n\n", "\n", ". ", " "):
            idx = target_chunk.rfind(delimiter)
            if idx != -1 and idx >= (effective_limit // 2):
                split_idx = idx + len(delimiter)
                break

        if split_idx == -1:
            split_idx = effective_limit

        chunk_piece = remaining[:split_idx]
        remaining = remaining[split_idx:].lstrip()

        # Track markdown code block fences
        fence_matches = list(re.finditer(r"```(\w*)", chunk_piece))
        for match in fence_matches:
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = match.group(1)

        # Rebalance code block fence across split boundary
        if in_code_block:
            chunk_piece += "\n```"
            remaining = f"```{code_block_lang}\n" + remaining

        chunks.append(chunk_piece)

    return chunks
