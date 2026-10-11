import pytest
from unittest.mock import patch, mock_open
from pithon.engine import check_memory_headroom, LlamaEngine

def test_check_memory_headroom_linux_sufficient():
    meminfo_content = "MemTotal:        1000000 kB\nMemFree:          200000 kB\nMemAvailable:     450000 kB\n"
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=meminfo_content)):
        assert check_memory_headroom(min_free_mb=100) is True

def test_check_memory_headroom_linux_insufficient():
    meminfo_content = "MemTotal:        1000000 kB\nMemFree:           20000 kB\nMemAvailable:      50000 kB\n"
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data=meminfo_content)):
        assert check_memory_headroom(min_free_mb=100) is False

def test_engine_mock_mode_streaming():
    engine = LlamaEngine(model_path=":mock:", n_ctx=1024, n_threads=3, mock_mode=True)
    assert engine.model_type == "generic"
    assert engine.n_threads == 3
    
    tokens = list(engine.generate_stream("Hello", temperature=0.0, max_tokens=20))
    generated_text = "".join(tokens)
    assert len(generated_text) > 0
    assert "Mock response" in generated_text
