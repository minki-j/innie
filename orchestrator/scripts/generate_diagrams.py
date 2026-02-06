"""
Generate Mermaid diagrams for all Prefect flow files.

One .mmd file per flow file, containing every flow defined in that file.

Usage:
    uv run generate-diagrams
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOWS_DIR = PROJECT_ROOT / "flows"
EXT = ".mmd"
_IGNORE_DIRS = {".venv", "venv", "__pycache__", "node_modules", ".git"}


# ── AST helpers ───────────────────────────────────────────────


def _dec_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
        return dec.func.id
    return None


def _dec_kwarg(dec: ast.expr, key: str) -> str | None:
    if isinstance(dec, ast.Call):
        for kw in dec.keywords:
            if kw.arg == key and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


# ── Data ──────────────────────────────────────────────────────


@dataclass
class FlowInfo:
    name: str
    func_name: str
    node: ast.FunctionDef


@dataclass
class TaskInfo:
    name: str
    func_name: str


@dataclass
class CallInfo:
    display_name: str
    kind: str  # "task" | "flow"
    in_loop: bool = False


# ── Discovery ─────────────────────────────────────────────────


def discover(root: Path):
    """Return (flows_by_file, all_flows, all_tasks)."""
    flows_by_file: dict[Path, list[FlowInfo]] = {}
    all_flows: dict[str, FlowInfo] = {}
    all_tasks: dict[str, TaskInfo] = {}

    for py in sorted(root.rglob("*.py")):
        if any(p in _IGNORE_DIRS for p in py.relative_to(root).parts):
            continue
        try:
            tree = ast.parse(py.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for dec in node.decorator_list:
                dn = _dec_name(dec)
                if dn == "flow":
                    name = _dec_kwarg(dec, "name") or node.name
                    info = FlowInfo(name, node.name, node)
                    all_flows[node.name] = info
                    flows_by_file.setdefault(py, []).append(info)
                elif dn == "task":
                    name = _dec_kwarg(dec, "name") or node.name
                    all_tasks[node.name] = TaskInfo(name, node.name)

    return flows_by_file, all_flows, all_tasks


# ── Call extraction ───────────────────────────────────────────


def extract_calls(
    flow: FlowInfo,
    flows: dict[str, FlowInfo],
    tasks: dict[str, TaskInfo],
) -> list[CallInfo]:
    calls: list[CallInfo] = []

    def _visit(stmts: list[ast.stmt], in_loop: bool = False):
        for s in stmts:
            if isinstance(s, (ast.For, ast.While, ast.AsyncFor)):
                _visit(s.body, in_loop=True)
            elif isinstance(s, ast.If):
                for child in ast.walk(s.test):
                    if isinstance(child, ast.Call):
                        fn = _call_name(child)
                        if fn in flows:
                            calls.append(CallInfo(flows[fn].name, "flow", in_loop))
                        elif fn in tasks:
                            calls.append(CallInfo(tasks[fn].name, "task", in_loop))
                _visit(s.body, in_loop)
                _visit(s.orelse, in_loop)
            elif isinstance(s, ast.Try):
                _visit(s.body, in_loop)
                for h in s.handlers:
                    _visit(h.body, in_loop)
                _visit(s.orelse, in_loop)
                _visit(s.finalbody, in_loop)
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                _visit(s.body, in_loop)
            else:
                for child in ast.walk(s):
                    if isinstance(child, ast.Call):
                        fn = _call_name(child)
                        if fn in flows:
                            calls.append(CallInfo(flows[fn].name, "flow", in_loop))
                        elif fn in tasks:
                            calls.append(CallInfo(tasks[fn].name, "task", in_loop))

    _visit(flow.node.body)
    return calls


# ── Mermaid rendering ─────────────────────────────────────────


def _node_shape(kind: str, label: str) -> str:
    """task → rounded box, flow → stadium shape."""
    if kind == "flow":
        return f"([{label}])"
    return f"({label})"


def render_mermaid(
    flow_file: Path,
    flow_list: list[FlowInfo],
    all_flows: dict[str, FlowInfo],
    all_tasks: dict[str, TaskInfo],
) -> str:
    lines = ["flowchart TD"]

    for flow in flow_list:
        calls = extract_calls(flow, all_flows, all_tasks)
        prefix = flow.func_name[:8]  # short unique prefix for node ids

        lines.append(f"    subgraph {flow.name}")
        prev = f"{prefix}_start"
        lines.append(f"        {prev}([Start])")

        for i, c in enumerate(calls):
            nid = f"{prefix}_{i}"
            label = c.display_name
            if c.in_loop:
                label += " ♻"
            shape = _node_shape(c.kind, label)
            lines.append(f"        {nid}{shape}")
            arrow = "-.->" if c.in_loop else "-->"
            lines.append(f"        {prev} {arrow} {nid}")
            prev = nid

        end = f"{prefix}_end"
        lines.append(f"        {end}([End])")
        lines.append(f"        {prev} --> {end}")
        lines.append("    end")

    return "\n".join(lines) + "\n"


# ── Cleanup & main ────────────────────────────────────────────


def cleanup(valid_stems: set[str]):
    for f in FLOWS_DIR.glob(f"*{EXT}"):
        if f.stem not in valid_stems:
            print(f"  Removed stale: {f.name}")
            f.unlink()


def main() -> None:
    flows_by_file, all_flows, all_tasks = discover(PROJECT_ROOT)

    if not flows_by_file:
        print("No flows found.")
        return

    valid_stems: set[str] = set()
    for py_file, flow_list in flows_by_file.items():
        mmd = render_mermaid(py_file, flow_list, all_flows, all_tasks)
        out = py_file.with_suffix(EXT)
        out.write_text(mmd)
        valid_stems.add(out.stem)
        print(f"  {out.relative_to(PROJECT_ROOT)}")

    cleanup(valid_stems)
    print(f"Done — {len(valid_stems)} diagram(s)")


if __name__ == "__main__":
    main()
