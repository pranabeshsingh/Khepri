"""Interactive terminal chat loop for Pithon."""

import sys
from typing import Any
from pithon.presets import get_preset_system_prompt
from pithon.template import format_chat_prompt

def run_chat(engine: Any, preset: str = "default") -> int:
    """Run interactive terminal REPL."""
    system_prompt = get_preset_system_prompt(preset)
    messages = [{"role": "system", "content": system_prompt}]
    model_type = getattr(engine, "model_type", "qwen")

    print("\n" + "=" * 55)
    print("  Pithon Local Chat (Raspberry Pi 3 SLM)")
    print(f"  Preset: {preset}")
    print("  Commands: /clear (reset conversation), /exit (quit)")
    print("=" * 55 + "\n")

    while True:
        try:
            user_input = input("user › ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting Pithon chat...")
            break

        if not user_input:
            continue

        if user_input in ("/exit", "/quit"):
            print("Goodbye!")
            break

        if user_input == "/clear":
            messages = [{"role": "system", "content": system_prompt}]
            print("[Conversation history cleared]\n")
            continue

        messages.append({"role": "user", "content": user_input})
        prompt = format_chat_prompt(messages, model_type=model_type)

        print("assistant › ", end="", flush=True)
        tokens = []
        for chunk in engine.generate_stream(prompt, temperature=0.2):
            tokens.append(chunk)
            sys.stdout.write(chunk)
            sys.stdout.flush()
        print("\n")

        full_reply = "".join(tokens)
        messages.append({"role": "assistant", "content": full_reply})

    return 0
