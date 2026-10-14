"""Deterministic, sandboxed mathematical expression evaluator."""

import ast
import math
import operator
from typing import Any, Union

_SAFE_OPERATORS: dict[Any, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

_SAFE_FUNCTIONS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "ceil": math.ceil,
    "floor": math.floor,
}

def _eval_node(node: ast.AST) -> Union[int, float]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")

    if isinstance(node, ast.Name):
        if node.id in _SAFE_CONSTANTS:
            return _SAFE_CONSTANTS[node.id]
        raise ValueError(f"Unknown variable: {node.id}")

    if isinstance(node, ast.UnaryOp):
        uop_type = type(node.op)
        if uop_type in _SAFE_OPERATORS:
            return _SAFE_OPERATORS[uop_type](_eval_node(node.operand))
        raise ValueError(f"Unsupported unary operator: {uop_type}")

    if isinstance(node, ast.BinOp):
        bop_type = type(node.op)
        if bop_type in _SAFE_OPERATORS:
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            if bop_type is ast.Pow and (right > 1000 or left > 100000):
                raise ValueError("Exponent too large")
            return _SAFE_OPERATORS[bop_type](left, right)
        raise ValueError(f"Unsupported binary operator: {bop_type}")

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCTIONS:
            args = [_eval_node(arg) for arg in node.args]
            return _SAFE_FUNCTIONS[node.func.id](*args)
        raise ValueError(f"Unsupported function call: {ast.dump(node.func)}")

    raise ValueError(f"Unsupported syntax expression: {type(node).__name__}")

def safe_calculate(expression: str) -> str:
    """Safely evaluate mathematical expressions without eval/exec."""
    clean = expression.strip()
    clean = clean.replace("^", "**").replace("×", "*").replace("÷", "/")
    clean = clean.lstrip("=").strip()
    if not clean:
        return "Error: Empty expression"

    try:
        tree = ast.parse(clean, mode="eval")
        result = _eval_node(tree.body)
        if isinstance(result, float):
            result = round(result, 8)
            if result.is_integer():
                result = int(result)
        return str(result)
    except Exception as e:
        return f"Error: {e}"
