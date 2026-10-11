import pytest
from io import StringIO
from pithon.pipe import budget_log_content, run_pipe

def test_budget_log_content_small():
    short_log = "2026-10-11 INFO Started service\n2026-10-11 INFO Processing request\n"
    assert budget_log_content(short_log, max_chars=1000) == short_log

def test_budget_log_content_large_truncation():
    lines = [f"2026-10-11 Line {i} with some log data" for i in range(1000)]
    huge_log = "\n".join(lines)
    
    budgeted = budget_log_content(huge_log, max_chars=500)
    assert len(budgeted) <= 800
    assert "[... omitted" in budgeted
    assert "Line 0" in budgeted
    assert "Line 999" in budgeted

class MockEngine:
    def __init__(self):
        self.last_prompt = None

    def generate_stream(self, prompt, temperature=0.0, max_tokens=512):
        self.last_prompt = prompt
        yield "Root cause: "
        yield "Memory leak in worker thread."

def test_run_pipe_execution():
    engine = MockEngine()
    out = StringIO()
    log_data = "ERROR 500 Out of memory at worker.py:42"
    
    exit_code = run_pipe(
        engine=engine,
        user_prompt="Identify the failure",
        preset="log-analyzer",
        stdin_content=log_data,
        out_stream=out
    )
    
    assert exit_code == 0
    assert out.getvalue().strip() == "Root cause: Memory leak in worker thread."
    assert "Identify the failure" in engine.last_prompt
    assert "ERROR 500" in engine.last_prompt
