#!/usr/bin/env python3
"""
Generate a flow diagram (Mermaid flowchart) from a Python function.

Usage examples:
  uv run python orchestrator/scripts/flow_diagram.py \
    --file orchestrator/flows/video_pipeline.py \
    --function video_pipeline

  uv run python orchestrator/scripts/flow_diagram.py \
    --file orchestrator/flows/video_pipeline.py \
    --lines 216-254
"""

from __future__ import annotations

import argparse
import ast
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class Edge:
    src: str
    dst: str
    label: str | None = None


@dataclass
class EndRef:
    node_id: str
    label: str | None = None
    kind: str = "normal"  # normal | break


@dataclass
class Graph:
    nodes: dict[str, str] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    _counter: int = 0

    def add_node(self, label: str) -> str:
        node_id = f"N{self._counter}"
        self._counter += 1
        self.nodes[node_id] = label
        return node_id

    def add_edge(self, src: str, dst: str, label: str | None = None) -> None:
        self.edges.append(Edge(src=src, dst=dst, label=label))


@dataclass
class LoopContext:
    header_id: str


@dataclass
class BuildContext:
    task_names: set[str]
    flow_names: set[str]
    local_functions: dict[str, ast.FunctionDef]
    max_depth: int
    call_stack: list[str] = field(default_factory=list)


def _short(text: str, max_len: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return node.__class__.__name__


def _label_stmt(stmt: ast.stmt) -> str:
    if isinstance(stmt, ast.If):
        return _short(f"if {_unparse(stmt.test)}")
    if isinstance(stmt, ast.For):
        return _short(f"for {_unparse(stmt.target)} in {_unparse(stmt.iter)}")
    if isinstance(stmt, ast.While):
        return _short(f"while {_unparse(stmt.test)}")
    if isinstance(stmt, ast.Assign):
        targets = ", ".join(_unparse(t) for t in stmt.targets)
        return _short(f"{targets} = {_unparse(stmt.value)}")
    if isinstance(stmt, ast.AugAssign):
        return _short(f"{_unparse(stmt.target)} {_unparse(stmt.op)}= {_unparse(stmt.value)}")
    if isinstance(stmt, ast.Expr):
        return _short(_unparse(stmt.value))
    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            return "return"
        return _short(f"return {_unparse(stmt.value)}")
    if isinstance(stmt, ast.With):
        return _short(f"with {_unparse(stmt.items[0])}" if stmt.items else "with")
    if isinstance(stmt, ast.Try):
        return "try"
    if isinstance(stmt, ast.Raise):
        return _short("raise" if stmt.exc is None else f"raise {_unparse(stmt.exc)}")
    if isinstance(stmt, ast.Break):
        return "break"
    if isinstance(stmt, ast.Continue):
        return "continue"
    if isinstance(stmt, ast.Pass):
        return "pass"
    return _short(stmt.__class__.__name__)


def _decorator_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return None


def _collect_decorated_functions(
    tree: ast.Module, decorator_names: set[str]
) -> set[str]:
    results: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                name = _decorator_name(dec)
                if name in decorator_names:
                    results.add(node.name)
                    break
    return results


def _find_flow_by_name(
    root: Path, flow_name: str, decorator_names: set[str]
) -> tuple[Path, ast.FunctionDef] | None:
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == flow_name:
                for dec in node.decorator_list:
                    name = _decorator_name(dec)
                    if name in decorator_names:
                        return py_file, node
    return None


def _task_call_label(
    stmt: ast.stmt, task_names: set[str], flow_names: set[str]
) -> str | None:
    def call_label(call: ast.Call) -> str | None:
        if isinstance(call.func, ast.Name):
            fn = call.func.id
            if fn in task_names:
                return f"task {fn}"
            if fn in flow_names:
                return f"flow {fn}"
        if isinstance(call.func, ast.Attribute):
            attr = call.func.attr
            value = call.func.value
            if isinstance(value, ast.Name):
                fn = value.id
                if fn in task_names:
                    return f"task {fn}.{attr}"
                if fn in flow_names:
                    return f"flow {fn}.{attr}"
        return None

    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return call_label(stmt.value)

    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
        return call_label(stmt.value)

    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call):
        return call_label(stmt.value)

    return None


def _call_target_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _inline_call_block(
    graph: Graph,
    call: ast.Call,
    context: BuildContext,
) -> tuple[str | None, list[EndRef]]:
    target = _call_target_name(call)
    if target is None:
        return None, []
    if target in context.task_names or target in context.flow_names:
        return None, []
    fn = context.local_functions.get(target)
    if fn is None:
        return None, []
    if target in context.call_stack:
        return None, []
    if len(context.call_stack) >= context.max_depth:
        return None, []

    context.call_stack.append(target)
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    start, ends = _build_block(graph, body, [], context)
    context.call_stack.pop()
    return start, ends


def _build_block(
    graph: Graph,
    stmts: Iterable[ast.stmt],
    loop_stack: list[LoopContext],
    context: BuildContext,
) -> tuple[str | None, list[EndRef]]:
    start_id: str | None = None
    end_refs: list[EndRef] = []

    for stmt in stmts:
        stmt_start, stmt_ends = _build_stmt(graph, stmt, loop_stack, context)
        if stmt_start is None:
            continue
        if start_id is None:
            start_id = stmt_start
        for end_ref in end_refs:
            if end_ref.kind == "normal":
                graph.add_edge(end_ref.node_id, stmt_start, end_ref.label)
        end_refs = stmt_ends

        if not end_refs:
            # Control flow ended (return/continue); stop chaining.
            break

    return start_id, end_refs


def _build_stmt(
    graph: Graph,
    stmt: ast.stmt,
    loop_stack: list[LoopContext],
    context: BuildContext,
) -> tuple[str | None, list[EndRef]]:
    if isinstance(stmt, ast.If):
        cond_id = graph.add_node(_label_stmt(stmt))

        body_start, body_ends = _build_block(
            graph, stmt.body, loop_stack, context
        )
        orelse_start, orelse_ends = _build_block(
            graph, stmt.orelse, loop_stack, context
        )

        if body_start is not None:
            graph.add_edge(cond_id, body_start, "true")
        else:
            body_ends = [EndRef(cond_id)]

        if orelse_start is not None:
            graph.add_edge(cond_id, orelse_start, "false")
            ends = body_ends + orelse_ends
        else:
            ends = body_ends + [EndRef(cond_id, label="false")]

        return cond_id, ends

    if isinstance(stmt, (ast.For, ast.While)):
        header_id = graph.add_node(_label_stmt(stmt))
        loop_stack.append(LoopContext(header_id=header_id))
        body_start, body_ends = _build_block(
            graph, stmt.body, loop_stack, context
        )
        loop_stack.pop()

        if body_start is not None:
            graph.add_edge(header_id, body_start, "loop")
        break_ends: list[EndRef] = []
        for end_ref in body_ends:
            if end_ref.kind == "break":
                break_ends.append(end_ref)
            else:
                graph.add_edge(end_ref.node_id, header_id, "back")

        if stmt.orelse:
            orelse_start, orelse_ends = _build_block(
                graph, stmt.orelse, loop_stack, context
            )
            if orelse_start is not None:
                graph.add_edge(header_id, orelse_start, "exit")
            return header_id, break_ends + orelse_ends

        return header_id, break_ends + [EndRef(header_id, label="exit")]

    if isinstance(stmt, ast.Try):
        try_id = graph.add_node(_label_stmt(stmt))
        body_start, body_ends = _build_block(
            graph, stmt.body, loop_stack, context
        )
        if body_start is not None:
            graph.add_edge(try_id, body_start, "try")
        ends = body_ends

        for handler in stmt.handlers:
            exc_label = _unparse(handler.type) if handler.type is not None else ""
            handler_id = graph.add_node(_short(f"except {exc_label}".strip()))
            graph.add_edge(try_id, handler_id, "except")
            h_start, h_ends = _build_block(
                graph, handler.body, loop_stack, context
            )
            if h_start is not None:
                graph.add_edge(handler_id, h_start)
                ends += h_ends
            else:
                ends.append(EndRef(handler_id))

        if stmt.finalbody:
            final_id = graph.add_node("finally")
            for end_ref in ends:
                graph.add_edge(end_ref.node_id, final_id)
            f_start, f_ends = _build_block(
                graph, stmt.finalbody, loop_stack, context
            )
            if f_start is not None:
                graph.add_edge(final_id, f_start)
                ends = f_ends
            else:
                ends = [EndRef(final_id)]

        return try_id, ends

    if isinstance(stmt, ast.Return):
        node_id = graph.add_node(_label_stmt(stmt))
        return node_id, []

    if isinstance(stmt, ast.Break):
        node_id = graph.add_node(_label_stmt(stmt))
        return node_id, [EndRef(node_id, label="break", kind="break")]

    if isinstance(stmt, ast.Continue):
        node_id = graph.add_node(_label_stmt(stmt))
        if loop_stack:
            graph.add_edge(node_id, loop_stack[-1].header_id, "continue")
        return node_id, []

    task_label = _task_call_label(stmt, context.task_names, context.flow_names)
    if task_label:
        node_id = graph.add_node(task_label)
        return node_id, [EndRef(node_id)]

    if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)) and isinstance(
        getattr(stmt, "value", None), ast.Call
    ):
        start, ends = _inline_call_block(graph, stmt.value, context)
        if start is not None:
            return start, ends

    # Ignore non-control, non-task statements.
    return None, []

    node_id = graph.add_node(_label_stmt(stmt))
    return node_id, [EndRef(node_id)]


def _find_function_by_name(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _find_function_by_lines(tree: ast.Module, start: int, end: int) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and hasattr(node, "lineno"):
            node_start = node.lineno
            node_end = getattr(node, "end_lineno", node.lineno)
            if node_start <= start and node_end >= end:
                return node
    return None


def build_graph_for_function(
    fn: ast.FunctionDef,
    task_names: set[str],
    flow_names: set[str],
    local_functions: dict[str, ast.FunctionDef],
    max_depth: int,
) -> Graph:
    graph = Graph()
    context = BuildContext(
        task_names=task_names,
        flow_names=flow_names,
        local_functions=local_functions,
        max_depth=max_depth,
    )
    start_id = graph.add_node("Start")
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        if isinstance(body[0].value.value, str):
            body = body[1:]
    block_start, block_ends = _build_block(graph, body, [], context)
    if block_start is not None:
        graph.add_edge(start_id, block_start)

    end_id = graph.add_node("End")
    for end_ref in block_ends:
        graph.add_edge(end_ref.node_id, end_id, end_ref.label)
    if not block_ends:
        graph.add_edge(start_id, end_id)

    return graph


def graph_to_mermaid(graph: Graph) -> str:
    lines = ["flowchart TD"]
    for node_id, label in graph.nodes.items():
        lines.append(f"  {node_id}[\"{label}\"]")
    for edge in graph.edges:
        if edge.label:
            lines.append(f"  {edge.src} -- \"{edge.label}\" --> {edge.dst}")
        else:
            lines.append(f"  {edge.src} --> {edge.dst}")
    return "\n".join(lines)


def graph_to_dot(graph: Graph) -> str:
    lines = ["digraph flow {", "  rankdir=TB;"]
    for node_id, label in graph.nodes.items():
        safe = label.replace('"', '\\"')
        lines.append(f'  {node_id} [label="{safe}"];')
    for edge in graph.edges:
        if edge.label:
            safe_label = edge.label.replace('"', '\\"')
            lines.append(f'  {edge.src} -> {edge.dst} [label="{safe_label}"];')
        else:
            lines.append(f"  {edge.src} -> {edge.dst};")
    lines.append("}")
    return "\n".join(lines)


def render_png(graph: Graph, output_path: Path) -> None:
    target = output_path
    if target.suffix != ".png":
        target = target.with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    dot_text = graph_to_dot(graph)
    subprocess.run(
        ["dot", "-Tpng", "-o", target.as_posix()],
        input=dot_text,
        text=True,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Mermaid flowchart from Python code.")
    parser.add_argument("--file", help="Path to the Python file.")
    parser.add_argument("--function", help="Function name to diagram.")
    parser.add_argument("--lines", help="Line range (e.g. 216-254) to locate a function.")
    parser.add_argument("--flow", help="Flow function name to diagram.")
    parser.add_argument("--output", help="Write Mermaid output to this file.")
    parser.add_argument("--png", help="Write a PNG diagram to this file.")
    parser.add_argument(
        "--task-decorator",
        action="append",
        default=["task"],
        help="Decorator name to treat as task (repeatable).",
    )
    parser.add_argument(
        "--flow-decorator",
        action="append",
        default=["flow"],
        help="Decorator name to treat as flow (repeatable).",
    )
    parser.add_argument(
        "--root",
        help="Root directory to scan for task/flow decorators.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Max inline depth for local helper functions.",
    )
    args = parser.parse_args()

    if not args.flow and not args.file:
        raise SystemExit("Provide --flow or --file.")
    if args.flow and args.file:
        raise SystemExit("Use only one of --flow or --file.")

    default_root = Path.cwd() / "orchestrator"
    if not default_root.exists():
        default_root = Path.cwd()
    root = Path(args.root) if args.root else default_root

    file_path: Path | None = None
    tree: ast.Module | None = None
    fn: ast.FunctionDef | None = None

    if args.flow:
        match = _find_flow_by_name(root, args.flow, set(args.flow_decorator))
        if match is None:
            raise SystemExit(f"Flow '{args.flow}' not found under {root}.")
        file_path, fn = match
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    else:
        file_path = Path(args.file)
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    all_task_names: set[str] = set()
    all_flow_names: set[str] = set()
    for py_file in root.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
            py_tree = ast.parse(text)
        except Exception:
            continue
        all_task_names.update(_collect_decorated_functions(py_tree, set(args.task_decorator)))
        all_flow_names.update(_collect_decorated_functions(py_tree, set(args.flow_decorator)))

    local_functions = {}
    if tree is not None:
        local_functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        }

    if fn is None:
        if args.function:
            fn = _find_function_by_name(tree, args.function)
        elif args.lines:
            start_str, end_str = args.lines.split("-")
            fn = _find_function_by_lines(tree, int(start_str), int(end_str))
        else:
            raise SystemExit("Provide --flow, --function, or --lines.")

    if fn is None:
        raise SystemExit("Function not found.")

    graph = build_graph_for_function(
        fn, all_task_names, all_flow_names, local_functions, args.max_depth
    )
    mermaid = graph_to_mermaid(graph)

    if args.output:
        Path(args.output).write_text(mermaid, encoding="utf-8")

    if args.png:
        render_png(graph, Path(args.png))
    elif args.flow and file_path is not None:
        render_png(graph, file_path.with_name(f"{args.flow}.png"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
