"""Safe, JSON-friendly rule condition evaluator.

The evaluator accepts a deliberately small subset of Python expressions so that
rules can be configured in JSON without embedding Python or calling ``eval``.
Only AST node types listed in ``_ALLOWED_NODES`` are executed; names are looked
up exclusively against the supplied fact context, and calls are limited to the
whitelisted helper functions in ``FUNCTIONS``.

Supported expressions include:

* field comparisons: ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``, ``in``
* boolean logic: ``and``, ``or``, ``not``
* basic arithmetic: ``+``, ``-``, ``*``, ``/``, ``//``, ``%``
* literals: numbers, quoted strings, ``true``/``false``/``null``
* helper calls such as ``contains(product_description, 'military')``,
  ``strip(str(ultimate_end_user)) != ''`` or ``len(text) > 3``

Dotted attribute access, indexing, imports, lambdas and arbitrary function
calls are rejected.
"""

from __future__ import annotations

import ast
import operator as _operator
from typing import Any

_MISSING = object()


class RuleExpressionError(ValueError):
    """Raised when a JSON rule expression is invalid or references an unknown field."""


def _lower(value: Any) -> str:
    return value.lower() if isinstance(value, str) else ""


def _upper(value: Any) -> str:
    return value.upper() if isinstance(value, str) else ""


def _strip(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _title(value: Any) -> str:
    return value.title() if isinstance(value, str) else ""


def _contains(haystack: Any, needle: Any) -> bool:
    if haystack is None or needle is None:
        return False
    if isinstance(haystack, (list, tuple, set)):
        return needle in haystack
    return str(needle).casefold() in str(haystack).casefold()


def _startswith(value: Any, prefix: Any) -> bool:
    if value is None or prefix is None:
        return False
    return str(value).casefold().startswith(str(prefix).casefold())


def _endswith(value: Any, suffix: Any) -> bool:
    if value is None or suffix is None:
        return False
    return str(value).casefold().endswith(str(suffix).casefold())


def _isin(item: Any, collection: Any) -> bool:
    try:
        return item in collection
    except TypeError:
        return False


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _num(value: Any) -> Any:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


FUNCTIONS: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "num": _num,
    "len": len,
    "lower": _lower,
    "upper": _upper,
    "strip": _strip,
    "title": _title,
    "contains": _contains,
    "startswith": _startswith,
    "endswith": _endswith,
    "isin": _isin,
    "coalesce": _coalesce,
}

_RESERVED_NAMES: dict[str, Any] = {
    "true": True,
    "True": True,
    "false": False,
    "False": False,
    "null": None,
    "None": None,
}

_COMPARE_OPERATORS: dict[type[ast.cmpop], Any] = {
    ast.Eq: _operator.eq,
    ast.NotEq: _operator.ne,
    ast.Lt: _operator.lt,
    ast.LtE: _operator.le,
    ast.Gt: _operator.gt,
    ast.GtE: _operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_BIN_OPERATORS: dict[type[ast.operator], Any] = {
    ast.Add: _operator.add,
    ast.Sub: _operator.sub,
    ast.Mult: _operator.mul,
    ast.Div: _operator.truediv,
    ast.FloorDiv: _operator.floordiv,
    ast.Mod: _operator.mod,
}

_ALLOWED_NODES: set[type[ast.AST]] = {
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.List,
    ast.Tuple,
    ast.Compare,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.BinOp,
    ast.Call,
    ast.keyword,
    # Comparison operators
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    # Binary operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
}


def _safe_binary(operator_fn: Any, left: Any, right: Any) -> Any:
    if left is None or right is None:
        return None
    if operator_fn in (_operator.add, _operator.sub, _operator.mul) and (
        isinstance(left, str) and isinstance(right, str) and operator_fn is not _operator.add
    ):
        return None
    try:
        return operator_fn(left, right)
    except (TypeError, ZeroDivisionError, ValueError):
        return None


class _Evaluator(ast.NodeVisitor):
    def __init__(self, context: dict[str, Any]):
        self.context = context

    def evaluate(self, expression: str) -> Any:
        try:
            tree = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise RuleExpressionError(f"Invalid rule expression: {exc}") from exc
        self._validate(tree)
        return self.visit(tree.body)

    def _validate(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute):
                raise RuleExpressionError(
                    "Attribute access is not supported; use flat fact names such as product_description"
                )
            if isinstance(child, ast.Subscript):
                raise RuleExpressionError("Indexing is not supported in rule expressions")
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                raise RuleExpressionError("Assignments and deletions are not supported in rule expressions")
            if type(child) not in _ALLOWED_NODES:
                raise RuleExpressionError(f"Expression element {type(child).__name__} is not allowed")
        for node_ in ast.walk(node):
            if isinstance(node_, ast.Call):
                if not isinstance(node_.func, ast.Name) or node_.func.id not in FUNCTIONS:
                    raise RuleExpressionError("Only whitelisted helper functions may be called in rules")
                if node_.keywords:
                    raise RuleExpressionError("Keyword arguments are not supported in rules")
        # Ensure every referenced Name resolves against the context or reserved names.
        for node_ in ast.walk(node):
            if isinstance(node_, ast.Name) and not isinstance(node_, ast.arg):
                if node_.id not in self.context and node_.id not in _RESERVED_NAMES and node_.id not in FUNCTIONS:
                    raise RuleExpressionError(
                        f"Unknown field or function '{node_.id}' in rule expression; "
                        f"available fields: {', '.join(sorted(self.context))}"
                    )

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        value = self.context.get(node.id, _MISSING)
        if value is not _MISSING:
            return value
        if node.id in _RESERVED_NAMES:
            return _RESERVED_NAMES[node.id]
        return None

    def visit_List(self, node: ast.List) -> list[Any]:
        return [self.visit(elt) for elt in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple[Any, ...]:
        return tuple(self.visit(elt) for elt in node.elts)

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for operator_node, comparator_node in zip(node.ops, node.comparators):
            right = self.visit(comparator_node)
            compare_fn = _COMPARE_OPERATORS[type(operator_node)]
            try:
                result = compare_fn(left, right)
            except TypeError:
                result = False
            if not result:
                return False
            left = right
        return True

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        values = [self.visit(value) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        value = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not value
        if isinstance(node.op, ast.USub):
            return -value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if isinstance(node.op, ast.UAdd):
            return +value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        return None

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        operator_fn = _BIN_OPERATORS[type(node.op)]
        return _safe_binary(operator_fn, left, right)

    def visit_Call(self, node: ast.Call) -> Any:
        function = FUNCTIONS[node.func.id]
        args = [self.visit(arg) for arg in node.args]
        try:
            return function(*args)
        except (TypeError, ValueError, ZeroDivisionError):
            return None


def evaluate_condition(condition: str, context: dict[str, Any]) -> bool:
    """Evaluate one JSON rule condition against a flat fact context.

    A condition is expected to resolve to a boolean. Non-boolean results are
    coerced with Python truthiness so empty strings and ``None`` count as false.
    """

    result = _Evaluator(dict(context)).evaluate(condition)
    return bool(result)


def available_functions() -> dict[str, str]:
    """Return the whitelisted helper functions for documentation purposes."""

    return {
        "str(v)", "int(v)", "float(v)", "num(v)", "len(v)", "lower(v)", "upper(v)",
        "strip(v)", "title(v)", "contains(haystack, needle)", "startswith(v, prefix)",
        "endswith(v, suffix)", "isin(item, collection)", "coalesce(*values)",
    }
