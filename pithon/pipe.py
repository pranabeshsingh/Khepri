"""Stdin pipe ingestion and log budgeting for resource-constrained models."""

import sys
from typing import Any, Optional, TextIO
from pithon.presets import get_preset_system_prompt
from pithon.template import format_chat_prompt

def budget_log_content(text: str, max_chars: int = 7000) -> str:
    """Intelligently truncate oversized log text to fit in model context window.
    
    Retains the header lines (initial startup/context) and trailing lines (where the crash occurs),
    dropping intermediate repetitive lines.
    """
    if len(text) <= max_chars:
        return text
    
    lines = text.splitlines()
    if len(lines) <= 10:
        return text[:max_chars]

    # Allocate ~20% of budget to header, ~80% to tail
    head_budget = int(max_chars * 0.2)
    tail_budget = int(max_chars * 0.8)

    head_lines = []
    current_head_len = 0
    head_idx = 0
    while head_idx < len(lines) and current_head_len + len(lines[head_idx]) + 1 <= head_budget:
        head_lines.append(lines[head_idx])
        current_head_len += len(lines[head_idx]) + 1
        head_idx += 1

    tail_lines = []
    current_tail_len = 0
    tail_idx = len(lines) - 1
    while tail_idx >= head_idx and current_tail_len + len(lines[tail_idx]) + 1 <= tail_budget:
        tail_lines.append(lines[tail_idx])
        current_tail_len += len(lines[tail_idx]) + 1
        tail_idx -= 1
    tail_lines.reverse()

    omitted_count = max(0, len(lines) - len(head_lines) - len(tail_lines))
    separator = f"\n[... omitted {omitted_count} lines of intermediate logs ...]\n"
    
    return "\n".join(head_lines) + separator + "\n".join(tail_lines)

def run_pipe(
    engine: Any,
    user_prompt: Optional[str] = None,
    preset: str = "log-analyzer",
    stdin_content: str = "",
    out_stream: TextIO = sys.stdout
) -> int:
    """Process piped log input and stream response to stdout."""
    system_prompt = get_preset_system_prompt(preset)
    budgeted_input = budget_log_content(stdin_content)
    
    content_parts = []
    if user_prompt and user_prompt.strip():
        content_parts.append(user_prompt.strip())
    if budgeted_input.strip():
        content_parts.append(f"Logs/Input:\n```\n{budgeted_input.strip()}\n```")
    
    user_content = "\n\n".join(content_parts) if content_parts else "Analyze the provided input."

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    model_type = getattr(engine, "model_type", "qwen")
    prompt = format_chat_prompt(messages, model_type=model_type)

    for chunk in engine.generate_stream(prompt, temperature=0.0):
        out_stream.write(chunk)
        out_stream.flush()

    out_stream.write("\n")
    out_stream.flush()
    return 0
