"""Low-level model loader, memory headroom checks, and generation loop."""

import os
import sys
import time
from typing import Iterator, Optional
from pithon.template import detect_model_type

def check_memory_headroom(min_free_mb: int = 100) -> bool:
    """Check if the system has sufficient available RAM (especially on Linux / Pi)."""
    meminfo_path = "/proc/meminfo"
    if os.path.exists(meminfo_path):
        try:
            with open(meminfo_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            avail_kb = int(parts[1])
                            return avail_kb >= min_free_mb * 1024
        except Exception:
            return True
    return True

class LlamaEngine:
    """Wrapper around llama_cpp with memory awareness and fallback simulation."""

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_batch: int = 128,
        n_threads: int = 3,
        mock_mode: bool = False
    ):
        self.model_path = model_path
        self.n_ctx = min(n_ctx, 2048)
        self.n_batch = min(n_batch, self.n_ctx)
        self.n_threads = max(1, min(n_threads, 4))
        self.mock_mode = mock_mode or (model_path == ":mock:")
        self.model_type = detect_model_type(model_path)
        self.llm = None

        if not self.mock_mode:
            self._load_model()

    def _load_model(self) -> None:
        """Initialize llama_cpp.Llama instance."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        try:
            from llama_cpp import Llama
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_batch=self.n_batch,
                n_threads=self.n_threads,
                verbose=False
            )
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python is not installed. Run `pip install llama-cpp-python`."
            ) from e

    def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.0,
        top_p: float = 0.8,
        max_tokens: int = 512
    ) -> Iterator[str]:
        """Stream generated tokens as strings."""
        if self.mock_mode:
            sample_words = ["Mock", " ", "response", " ", "for", ": ", prompt[:20], "..."]
            for word in sample_words:
                time.sleep(0.01)
                yield word
            return

        if not check_memory_headroom(min_free_mb=80):
            yield "\n[Error: Insufficient system memory available on host]\n"
            return

        stream = self.llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stream=True
        )

        for chunk in stream:
            choices = chunk.get("choices", [])
            if choices:
                delta = choices[0].get("text", "")
                if delta:
                    yield delta
