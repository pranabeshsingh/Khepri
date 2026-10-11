import pytest
from pithon.agent.calc import safe_calculate

def test_arithmetic():
    assert safe_calculate("2 + 3 * 4") == "14"
    assert safe_calculate("(10 - 2) / 4") == "2"
    assert safe_calculate("2 ** 10") == "1024"
    assert safe_calculate("15 % 4") == "3"

def test_math_functions():
    assert safe_calculate("sqrt(81)") == "9"
    assert safe_calculate("round(3.14159, 2)") == "3.14"
    assert safe_calculate("abs(-42)") == "42"

def test_syntax_normalization():
    assert safe_calculate("10 × 5 ÷ 2") == "25"
    assert safe_calculate("= 100 + 20") == "120"
    assert safe_calculate("2 ^ 3") == "8"

def test_security_rejection():
    assert "Error" in safe_calculate("__import__('os').system('ls')")
    assert "Error" in safe_calculate("eval('1+1')")
    assert "Error" in safe_calculate("open('/etc/passwd')")
