"""Escaping helpers for Telegram legacy Markdown (``parse_mode="Markdown"``).

Every outbound bot message goes out with ``parse_mode="Markdown"``, so any
character the user controls -- a task title, a note body, a search query, a
calendar event title -- can break entity parsing. Telegram answers an unbalanced
marker with HTTP 400 "can't parse entities", and ``TelegramBot._call_api``
swallows the error, which makes the whole command fail silently.

Only escape *user-supplied* values. The bot's own ``*bold*`` markers are
intentional entities and must be left alone, so this cannot be applied blindly
at the send boundary.

The legacy dialect recognises ``_italic_``, ``*bold*``, ``` `code` ```,
```pre```, and ``[text](url)``. Per the Bot API, those five characters plus the
escape character itself are escaped by prefixing a backslash.
"""

import re
from typing import Any

# A zero-width space between the characters of a backtick run: invisible on
# screen, but it breaks the sequence the Markdown parser is scanning for.
_ZWSP = "\u200b"
_FENCE_BREAK = re.compile(r"(`{3,})")

# str.translate applies a per-character mapping in a single pass, so ordering is
# never an issue -- a literal backslash cannot be double-escaped by accident.
_ESCAPE_TABLE = str.maketrans({
    "\\": "\\\\",
    "_": "\\_",
    "*": "\\*",
    "`": "\\`",
    "[": "\\[",
    "]": "\\]",
})


def escape_markdown(text: Any) -> str:
    """Return ``text`` with Telegram legacy Markdown metacharacters escaped.

    Safe to call on non-string values: anything that is not a string is
    stringified first, so callers never have to guard.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text.translate(_ESCAPE_TABLE)


def escape_code(text: Any) -> str:
    """Neutralise backtick runs that would terminate a ``` fenced code block.

    A code span suppresses entity parsing, so ``*``/``_``/``[]`` inside it are
    already safe. The one character that can break out is a literal backtick:
    Telegram scans for the closing fence greedily, so a run of three or more
    backticks anywhere in the payload ends the block early and dumps the rest
    of the message as raw text.

    Separating the offending characters with a zero-width space keeps them
    visible and stops the fence from closing. Runs of one or two backticks are
    left untouched -- they cannot close a triple-backtick fence.
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return _FENCE_BREAK.sub(lambda m: _ZWSP.join(m.group(1)), text)
