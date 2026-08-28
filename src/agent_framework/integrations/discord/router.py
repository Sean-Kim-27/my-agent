"""Discord message routing, session mapping, filtering, and safe chunking utilities."""

import re


def generate_session_id(
    author_id: int,
    channel_id: int,
    guild_id: int | None = None,
    thread_id: int | None = None,
    is_dm: bool = False,
) -> str:
    """Generate an isolated session identifier for Discord contexts.

    Formats:
        - Thread:  discord:guild:<guild_id>:thread:<thread_id>:user:<author_id>
        - Channel: discord:guild:<guild_id>:channel:<channel_id>:user:<author_id>
        - DM:      discord:dm:<author_id>
    """
    if is_dm or guild_id is None:
        return f"discord:dm:{author_id}"
    if thread_id is not None:
        return f"discord:guild:{guild_id}:thread:{thread_id}:user:{author_id}"
    return f"discord:guild:{guild_id}:channel:{channel_id}:user:{author_id}"


def should_process_message(
    author_id: int,
    is_bot: bool,
    channel_id: int,
    guild_id: int | None,
    bot_user_id: int | None,
    mentions_bot: bool,
    allowed_channels: list[int] | None = None,
    require_mention: bool = True,
    is_dm: bool = False,
) -> bool:
    """Evaluate whether an incoming Discord message should trigger agent processing."""
    # 1. Ignore own messages and all bot messages
    if is_bot or (bot_user_id is not None and author_id == bot_user_id):
        return False

    # 2. Check channel whitelist if configured
    if allowed_channels and channel_id not in allowed_channels:
        return False

    # 3. Direct messages are always processed without mention
    if is_dm or guild_id is None:
        return True

    # 4. Guild messages check mention requirement
    if require_mention and not mentions_bot:
        return False

    return True


def extract_clean_content(content: str, bot_user_id: int | None = None) -> str:
    """Strip Discord bot mention tags (<@bot_id> or <@!bot_id>) and whitespace."""
    if not content:
        return ""
    cleaned = content
    if bot_user_id is not None:
        cleaned = re.sub(rf"<@!?{bot_user_id}>", "", cleaned)
    else:
        cleaned = re.sub(r"<@!?\d+>", "", cleaned)
    return cleaned.strip()


def split_message_content(text: str, max_chunk_size: int = 2000) -> list[str]:
    """Safely split long responses into Discord-compliant chunks (<= 2000 characters).

    Preserves code block fences across split chunks.
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

        # Find best split point within max_chunk_size (leaving room for code fences if needed)
        effective_limit = max_chunk_size - (10 if in_code_block else 0)
        target_chunk = remaining[:effective_limit]

        # Try splitting on paragraph breaks, line breaks, sentence ends, or spaces
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

        # Track markdown code block state (count ```)
        fence_matches = list(re.finditer(r"```(\w*)", chunk_piece))
        for match in fence_matches:
            if in_code_block:
                in_code_block = False
                code_block_lang = ""
            else:
                in_code_block = True
                code_block_lang = match.group(1)

        # If chunk ended inside an open code block, close it in this chunk and reopen in next
        if in_code_block:
            chunk_piece += "\n```"
            remaining = f"```{code_block_lang}\n" + remaining

        chunks.append(chunk_piece)

    return chunks
