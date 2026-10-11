"""Chat templating utilities for Qwen, SmolLM, and generic instruct models."""

from typing import Any, Dict, List

def detect_model_type(model_path: str) -> str:
    """Infer chat template format from model file name or path."""
    lower = model_path.lower()
    if "qwen" in lower:
        return "qwen"
    elif "smollm" in lower:
        return "smollm"
    return "generic"

def format_chat_prompt(messages: List[Dict[str, Any]], model_type: str = "qwen") -> str:
    """Format an OpenAI-style list of messages into the model's raw prompt string."""
    formatted = []
    
    if model_type in ("qwen", "smollm"):
        # ChatML format: <|im_start|>role\ncontent<|im_end|>\n
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Multi-part content support
                text_parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                content = "\n".join(text_parts)
            formatted.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
        formatted.append("<|im_start|>assistant\n")
    else:
        # Generic role: content format
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            formatted.append(f"### {role}:\n{content}\n\n")
        formatted.append("### Assistant:\n")

    return "".join(formatted)
