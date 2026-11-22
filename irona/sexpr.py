"""Minimal reader for KiCad's s-expression files (.kicad_sch, .kicad_pcb)."""

import re
from typing import Any, Iterator, List, Optional, Union

Node = Union[str, List[Any]]

_TOKEN = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')


def parse(text: str) -> List[Any]:
    """Parses one top-level expression into nested lists of strings (quotes removed)."""
    stack: List[List[Any]] = [[]]
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        if tok == "(":
            stack.append([])
        elif tok == ")":
            if len(stack) == 1:
                raise ValueError("Unbalanced ')' in s-expression")
            done = stack.pop()
            stack[-1].append(done)
        elif tok[0] == '"':
            stack[-1].append(tok[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(tok)
    if len(stack) != 1 or not stack[0]:
        raise ValueError("Unbalanced or empty s-expression")
    return stack[0][0]


def children(node: List[Any], name: str) -> Iterator[List[Any]]:
    """Direct child lists whose head is `name`."""
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == name:
            yield c


def child(node: List[Any], name: str) -> Optional[List[Any]]:
    return next(children(node, name), None)


def value(node: Optional[List[Any]], index: int = 1, default: Any = None) -> Any:
    """`(name a b)` -> a (index 1) or b (index 2)."""
    if node is None or len(node) <= index or isinstance(node[index], list):
        return default
    return node[index]


def properties(node: List[Any]) -> dict:
    """`(property "Name" "Value" ...)` children as {Name: Value}."""
    return {p[1]: p[2] for p in children(node, "property") if len(p) > 2 and isinstance(p[2], str)}
