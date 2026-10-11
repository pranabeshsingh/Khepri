import pytest
from pithon.template import format_chat_prompt, detect_model_type

def test_detect_model_type():
    assert detect_model_type("models/qwen2.5-0.5b-instruct-q4_k_m.gguf") == "qwen"
    assert detect_model_type("models/Qwen2.5-Coder-0.5B.gguf") == "qwen"
    assert detect_model_type("models/SmolLM-360M-Instruct.Q4_K_M.gguf") == "smollm"
    assert detect_model_type("models/random-model.gguf") == "generic"

def test_format_chat_prompt_qwen():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]
    prompt = format_chat_prompt(messages, model_type="qwen")
    expected = (
        "<|im_start|>system\nYou are a helpful assistant.<|im_end|>\n"
        "<|im_start|>user\nHello!<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    assert prompt == expected

def test_format_chat_prompt_multi_turn():
    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help?"},
        {"role": "user", "content": "What is the weather?"}
    ]
    prompt = format_chat_prompt(messages, model_type="qwen")
    expected = (
        "<|im_start|>user\nHi<|im_end|>\n"
        "<|im_start|>assistant\nHello! How can I help?<|im_end|>\n"
        "<|im_start|>user\nWhat is the weather?<|im_end|>\n"
        "<|im_start|>assistant\n"
    )
    assert prompt == expected

def test_format_chat_prompt_empty_and_fallback():
    assert format_chat_prompt([], model_type="qwen") == "<|im_start|>assistant\n"
