from __future__ import annotations

from dataclasses import replace
from typing import Protocol, TypeVar

_LOCAL_RECEIVER_NAMES = {"self", "cls", "this"}


class _GraphSpec(Protocol):
    symbolName: str | None
    qualifiedSymbolName: str | None
    parentSymbol: str | None
    callers: tuple[str, ...]
    callees: tuple[str, ...]


TGraphSpec = TypeVar("TGraphSpec", bound=_GraphSpec)


def attach_call_graph(specs: list[TGraphSpec]) -> list[TGraphSpec]:
    qualified_symbols = {
        spec.qualifiedSymbolName
        for spec in specs
        if spec.qualifiedSymbolName
    }
    symbols_by_name: dict[str, list[str]] = {}
    for spec in specs:
        if not spec.symbolName or not spec.qualifiedSymbolName:
            continue
        qualified_names = symbols_by_name.setdefault(spec.symbolName, [])
        if spec.qualifiedSymbolName not in qualified_names:
            qualified_names.append(spec.qualifiedSymbolName)

    resolved_specs: list[TGraphSpec] = []
    for spec in specs:
        resolved_callees = _resolve_callees(
            raw_callees=spec.callees,
            parent_symbol=spec.parentSymbol,
            qualified_symbol_name=spec.qualifiedSymbolName,
            qualified_symbols=qualified_symbols,
            symbols_by_name=symbols_by_name,
        )
        resolved_specs.append(
            replace(
                spec,
                callers=(),
                callees=resolved_callees,
            )
        )

    callers_by_target: dict[str, list[str]] = {}
    for spec in resolved_specs:
        if not spec.qualifiedSymbolName:
            continue
        caller_name = spec.qualifiedSymbolName
        for callee in spec.callees:
            if callee not in qualified_symbols or callee == caller_name:
                continue
            target_callers = callers_by_target.setdefault(callee, [])
            if caller_name not in target_callers:
                target_callers.append(caller_name)

    return [
        replace(
            spec,
            callers=tuple(callers_by_target.get(spec.qualifiedSymbolName or "", ())),
        )
        for spec in resolved_specs
    ]


def _resolve_callees(
    *,
    raw_callees: tuple[str, ...],
    parent_symbol: str | None,
    qualified_symbol_name: str | None,
    qualified_symbols: set[str],
    symbols_by_name: dict[str, list[str]],
) -> tuple[str, ...]:
    resolved: list[str] = []
    for raw_callee in raw_callees:
        candidate = _resolve_callee(
            raw_callee=raw_callee,
            parent_symbol=parent_symbol,
            qualified_symbol_name=qualified_symbol_name,
            qualified_symbols=qualified_symbols,
            symbols_by_name=symbols_by_name,
        )
        if candidate not in resolved:
            resolved.append(candidate)
    return tuple(resolved)


def _resolve_callee(
    *,
    raw_callee: str,
    parent_symbol: str | None,
    qualified_symbol_name: str | None,
    qualified_symbols: set[str],
    symbols_by_name: dict[str, list[str]],
) -> str:
    if raw_callee in qualified_symbols:
        return raw_callee

    if "." in raw_callee:
        receiver, attribute = raw_callee.split(".", 1)
        owner_symbol = parent_symbol or qualified_symbol_name
        if owner_symbol and receiver in _LOCAL_RECEIVER_NAMES and "." not in attribute:
            candidate = f"{owner_symbol}.{attribute}"
            if candidate in qualified_symbols:
                return candidate
        return raw_callee

    matching_symbols = symbols_by_name.get(raw_callee, [])
    if len(matching_symbols) == 1:
        return matching_symbols[0]

    return raw_callee
