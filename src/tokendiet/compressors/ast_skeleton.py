"""Python AST skeletonizer: preserves imports, signatures, docstrings & focus functions; elides boilerplate bodies."""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass

from tokendiet.compressors import estimate_tokens
from tokendiet.types import SkeletonReport


@dataclass(frozen=True)
class _ElisionSpan:
    start_line: int  # 1-indexed inclusive
    end_line: int  # 1-indexed inclusive
    indent: str
    elided_lines: int
    digest: str
    symbol_name: str


def _docstring_end_offset(body: list[ast.stmt]) -> int:
    if body and isinstance(body[0], ast.Expr):
        val = body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            return 1
    return 0


def _collect_elisions(
    stmts: list[ast.stmt],
    lines: list[str],
    focus_symbols: set[str],
    min_elide_lines: int,
    prefix: str,
    elisions: list[_ElisionSpan],
    preserved_symbols: list[str],
) -> None:
    for node in stmts:
        if isinstance(node, ast.ClassDef):
            cls_name = f"{prefix}{node.name}" if prefix else node.name
            preserved_symbols.append(cls_name)
            _collect_elisions(
                node.body,
                lines,
                focus_symbols,
                min_elide_lines,
                f"{cls_name}.",
                elisions,
                preserved_symbols,
            )
            continue

        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        full_name = f"{prefix}{node.name}" if prefix else node.name
        if node.name in focus_symbols or full_name in focus_symbols:
            preserved_symbols.append(full_name)
            continue

        offset = _docstring_end_offset(node.body)
        if offset >= len(node.body):
            preserved_symbols.append(full_name)
            continue

        first_body = node.body[offset]
        decs = getattr(first_body, "decorator_list", [])
        start_line = min([first_body.lineno, *(d.lineno for d in decs)])
        end_line = node.end_lineno or node.body[-1].end_lineno or start_line

        if start_line <= node.lineno or end_line < start_line:
            preserved_symbols.append(full_name)
            continue

        first_text = lines[start_line - 1]
        prefix_ws = first_text[: len(first_text) - len(first_text.lstrip(" \t"))]
        if first_text[: first_body.col_offset].strip():
            # Inline body after ':' — leave untouched to preserve valid syntax.
            preserved_symbols.append(full_name)
            continue

        span_len = end_line - start_line + 1
        if span_len < min_elide_lines:
            preserved_symbols.append(full_name)
            continue

        body_chunk = "\n".join(lines[start_line - 1 : end_line])
        digest = hashlib.sha256(body_chunk.encode("utf-8")).hexdigest()[:8]
        elisions.append(
            _ElisionSpan(
                start_line=start_line,
                end_line=end_line,
                indent=prefix_ws or " " * (node.col_offset + 4),
                elided_lines=span_len,
                digest=digest,
                symbol_name=full_name,
            )
        )


def skeletonize_python_source(
    source: str,
    focus_symbols: set[str] | None = None,
    min_elide_lines: int = 5,
) -> SkeletonReport:
    """Compress Python source by replacing non-focus function bodies with verifiable AST stubs."""
    if not source.strip():
        return SkeletonReport(
            original_lines=0,
            compressed_lines=0,
            original_tokens=0,
            compressed_tokens=0,
            savings_pct=0.0,
            syntax_valid=True,
            preserved_symbols=[],
            elided_symbols=[],
            compressed_source=source,
        )

    lines = source.splitlines()
    orig_tokens = estimate_tokens(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return SkeletonReport(
            original_lines=len(lines),
            compressed_lines=len(lines),
            original_tokens=orig_tokens,
            compressed_tokens=orig_tokens,
            savings_pct=0.0,
            syntax_valid=False,
            preserved_symbols=[],
            elided_symbols=[],
            compressed_source=source,
        )

    focus = focus_symbols or set()
    elisions: list[_ElisionSpan] = []
    preserved_symbols: list[str] = []
    _collect_elisions(
        tree.body,
        lines,
        focus,
        max(1, min_elide_lines),
        "",
        elisions,
        preserved_symbols,
    )

    if not elisions:
        return SkeletonReport(
            original_lines=len(lines),
            compressed_lines=len(lines),
            original_tokens=orig_tokens,
            compressed_tokens=orig_tokens,
            savings_pct=0.0,
            syntax_valid=True,
            preserved_symbols=preserved_symbols,
            elided_symbols=[],
            compressed_source=source,
        )

    elisions.sort(key=lambda sp: sp.start_line)
    out_lines: list[str] = []
    cursor = 1
    elided_symbols: list[str] = []
    for sp in elisions:
        if sp.start_line < cursor:
            continue
        out_lines.extend(lines[cursor - 1 : sp.start_line - 1])
        out_lines.append(
            f"{sp.indent}pass  # [tokendiet: elided {sp.elided_lines} lines sha256={sp.digest}]"
        )
        elided_symbols.append(sp.symbol_name)
        cursor = sp.end_line + 1

    if cursor <= len(lines):
        out_lines.extend(lines[cursor - 1 :])

    compressed_source = "\n".join(out_lines)
    if source.endswith("\n") and not compressed_source.endswith("\n"):
        compressed_source += "\n"

    try:
        ast.parse(compressed_source)
    except SyntaxError:
        return SkeletonReport(
            original_lines=len(lines),
            compressed_lines=len(lines),
            original_tokens=orig_tokens,
            compressed_tokens=orig_tokens,
            savings_pct=0.0,
            syntax_valid=True,
            preserved_symbols=preserved_symbols + elided_symbols,
            elided_symbols=[],
            compressed_source=source,
        )

    comp_tokens = estimate_tokens(compressed_source)
    savings = round(max(0.0, (1.0 - comp_tokens / max(1, orig_tokens)) * 100.0), 2)
    return SkeletonReport(
        original_lines=len(lines),
        compressed_lines=len(out_lines),
        original_tokens=orig_tokens,
        compressed_tokens=comp_tokens,
        savings_pct=savings,
        syntax_valid=True,
        preserved_symbols=preserved_symbols,
        elided_symbols=elided_symbols,
        compressed_source=compressed_source,
    )
