"""The typed formula language.

A signal is one expression such as::

    cs_rank(-delta(log(close), 5))
    neutralize(cs_rank(accr_quality) * (filing_lag <= 45), sector)

The compiler parses it with Python's own parser, accepts only a small set of
node types (no attribute access, no imports, no strings) and tracks for every
sub-expression how many rows after t its value becomes known. A signal that
would need anything known after t does not compile.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field

import numpy as np

from . import ops

_BINOPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: np.divide}
_CMP = {ast.Lt: np.less, ast.LtE: np.less_equal, ast.Gt: np.greater, ast.GtE: np.greater_equal}


class CompileError(ValueError):
    pass


class LookAheadError(CompileError):
    pass


@dataclass
class Node:
    kind: str                 # field | const | op | binop | neg | cmp
    name: str = ""
    value: float = 0.0
    args: list = field(default_factory=list)
    nums: list = field(default_factory=list)
    avail: float = float("-inf")  # rows after t when the value is known
    lookback: int = 0

    def canon(self) -> str:
        if self.kind == "field":
            return self.name
        if self.kind == "const":
            return repr(self.value)
        if self.kind == "neg":
            return f"neg({self.args[0].canon()})"
        if self.kind in ("binop", "cmp"):
            return f"{self.name}({self.args[0].canon()},{self.args[1].canon()})"
        inner = ",".join([a.canon() for a in self.args] + [repr(n) for n in self.nums])
        return f"{self.name}({inner})"

    def fields(self) -> set:
        if self.kind == "field":
            return {self.name}
        s = set()
        for a in self.args:
            s |= a.fields()
        return s

    def walk(self):
        yield self
        for a in self.args:
            yield from a.walk()


@dataclass
class Signal:
    expr: str
    root: Node

    @property
    def canon(self) -> str:
        return self.root.canon()

    @property
    def fields(self) -> set:
        return self.root.fields()

    @property
    def lookback(self) -> int:
        return self.root.lookback

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.canon.encode()).hexdigest()[:10]

    def evaluate(self, panel, upto: int | None = None) -> np.ndarray:
        return _eval(self.root, panel, upto)


def compile_signal(expr: str, panel) -> Signal:
    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        raise CompileError(f"not a valid formula: {e.msg}") from None
    root = _build(tree.body, panel)
    if root.kind == "const" or not root.fields():
        raise CompileError("a signal must read at least one field")
    if root.avail > 0:
        late = [n for n in root.walk() if n.kind == "field" and n.avail > 0]
        f = late[0] if late else None
        hint = f" Wrap it in delay({f.name}, {int(f.avail)})." if f else ""
        who = f"`{f.name}`" if f else "part of it"
        raise LookAheadError(
            f"this formula reads {who} at row t, but that value is only known "
            f"{int(root.avail)} row(s) later.{hint}"
        )
    return Signal(expr=expr.strip(), root=root)


def _num(node) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_num(node.operand)
    raise CompileError("expected a number")


def _build(node, panel) -> Node:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CompileError("only numbers are allowed as constants")
        return Node("const", value=float(node.value))

    if isinstance(node, ast.Name):
        if node.id not in panel.fields:
            known = ", ".join(sorted(panel.fields))
            raise CompileError(f"unknown field `{node.id}`. Fields: {known}")
        f = panel.fields[node.id]
        return Node("field", name=node.id, avail=float(f.known_at))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        a = _build(node.operand, panel)
        if a.kind == "const":
            return Node("const", value=-a.value)
        return Node("neg", name="neg", args=[a], avail=a.avail, lookback=a.lookback)

    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        a, b = _build(node.left, panel), _build(node.right, panel)
        name = type(node.op).__name__.lower()
        return Node("binop", name=name, args=[a, b], avail=max(a.avail, b.avail),
                    lookback=max(a.lookback, b.lookback))

    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
        a, b = _build(node.left, panel), _build(node.comparators[0], panel)
        name = type(node.ops[0]).__name__.lower()
        return Node("cmp", name=name, args=[a, b], avail=max(a.avail, b.avail),
                    lookback=max(a.lookback, b.lookback))

    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name not in ops.OPERATORS:
            raise CompileError(f"unknown operator `{name}`. Operators: {', '.join(sorted(ops.OPERATORS))}")
        if node.keywords:
            raise CompileError("keyword arguments are not allowed")
        _, n_arr, n_num = ops.OPERATORS[name]
        if len(node.args) != n_arr + n_num:
            raise CompileError(f"`{name}` takes {n_arr} series and {n_num} number(s)")
        args = [_build(a, panel) for a in node.args[:n_arr]]
        for a in args:
            if a.kind == "const":
                raise CompileError(f"`{name}` needs a series, got a number")
        nums = [_num(a) for a in node.args[n_arr:]]
        avail = max(a.avail for a in args)
        lookback = max(a.lookback for a in args)
        if name in ops.LOOKBACK_OPS:
            k = nums[0]
            if not float(k).is_integer() or k < (0 if name == "delay" else 1):
                if name == "delay" and k < 0:
                    raise LookAheadError("delay(x, k) with k < 0 reads the future")
                raise CompileError(f"`{name}` needs a positive whole number of rows, got {k}")
            if name == "delay":
                avail -= k
            lookback += int(k)
        return Node("op", name=name, args=args, nums=nums, avail=avail, lookback=lookback)

    raise CompileError(f"`{ast.unparse(node)}` is not allowed in a formula")


def _eval(n: Node, panel, upto):
    if n.kind == "field":
        return panel.get(n.name, upto)
    if n.kind == "const":
        return n.value
    if n.kind == "neg":
        return -_eval(n.args[0], panel, upto)
    if n.kind == "binop":
        a, b = _eval(n.args[0], panel, upto), _eval(n.args[1], panel, upto)
        fn = {"add": np.add, "sub": np.subtract, "mult": np.multiply, "div": np.divide}[n.name]
        with np.errstate(all="ignore"):
            out = fn(a, b)
        if n.name == "div":
            out = np.where(np.isfinite(out), out, np.nan)
        return out
    if n.kind == "cmp":
        a, b = _eval(n.args[0], panel, upto), _eval(n.args[1], panel, upto)
        fn = {"lt": np.less, "lte": np.less_equal, "gt": np.greater, "gte": np.greater_equal}[n.name]
        with np.errstate(all="ignore"):
            out = fn(a, b).astype(float)
        nan = np.isnan(a) if isinstance(a, np.ndarray) else False
        return np.where(nan, np.nan, out)
    fn = ops.OPERATORS[n.name][0]
    arrs = [_eval(a, panel, upto) for a in n.args]
    return fn(*arrs, *n.nums)


def ast_similarity(a: Signal, b: Signal) -> float:
    """Jaccard similarity of the sub-tree sets of two signals (0..1)."""
    sa = {x.canon() for x in a.root.walk() if x.kind != "const"}
    sb = {x.canon() for x in b.root.walk() if x.kind != "const"}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
