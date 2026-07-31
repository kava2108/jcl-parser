from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from jcl_parser import ParamValue, parse_jcl

SYMBOL_RE = re.compile(r"&([A-Za-z0-9$#@]+)\.?")


@dataclass
class ProcDef:
    name: str
    params: Dict[str, ParamValue]
    statements: List[Dict[str, object]] = field(default_factory=list)


def substitute_symbols(value: object, symtab: Dict[str, str], unresolved: Set[str]) -> object:
    """Recursively replace &VAR / &VAR. tokens using symtab; records names it couldn't resolve."""
    if isinstance(value, str):
        def repl(match: "re.Match[str]") -> str:
            key = match.group(1)
            if key in symtab:
                return str(symtab[key])
            unresolved.add(key)
            return match.group(0)

        return SYMBOL_RE.sub(repl, value)
    if isinstance(value, list):
        return [substitute_symbols(v, symtab, unresolved) for v in value]
    if isinstance(value, dict):
        return {k: substitute_symbols(v, symtab, unresolved) for k, v in value.items()}
    return value


def extract_procs(
    statements: List[Dict[str, object]],
) -> Tuple[List[Dict[str, object]], Dict[str, ProcDef]]:
    """Split inline `//name PROC ... //name PEND` blocks out of a flat statement list."""
    remaining: List[Dict[str, object]] = []
    proc_defs: Dict[str, ProcDef] = {}
    current: Optional[ProcDef] = None

    for stmt in statements:
        if stmt["type"] == "PROC":
            current = ProcDef(name=stmt["name"], params=dict(stmt["params"]))  # type: ignore[arg-type]
            continue
        if stmt["type"] == "PEND":
            if current is not None:
                proc_defs[current.name] = current
                current = None
            continue
        if current is not None:
            current.statements.append(stmt)
            continue
        remaining.append(stmt)

    return remaining, proc_defs


def load_proc_library(paths: List[str]) -> Dict[str, ProcDef]:
    """Load cataloged PROCLIB members from a search-ordered list of directories.

    Each file's name is the member/proc name (uppercased, matching JCL naming).
    A member may contain an explicit `//name PROC ... PEND` block (its defaults
    and body come from that), or just bare EXEC/DD statements with no PROC
    statement (PEND is optional in real PROCLIBs; treated here as the whole
    body with no default symbolics). On a name collision, the first directory
    in `paths` wins, mirroring PROCLIB concatenation search order.
    """
    library: Dict[str, ProcDef] = {}

    for directory in paths:
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            full_path = os.path.join(directory, filename)
            if not os.path.isfile(full_path):
                continue

            with open(full_path, encoding="utf-8") as handle:
                statements = parse_jcl(handle.readlines())
            remaining, proc_defs = extract_procs(statements)

            if proc_defs:
                for name, proc_def in proc_defs.items():
                    if name not in library:
                        library[name] = proc_def
            elif remaining:
                fallback_name = filename.upper()
                if fallback_name not in library:
                    library[fallback_name] = ProcDef(name=fallback_name, params={}, statements=remaining)

    return library


def _proc_reference(params: Dict[str, ParamValue]) -> Tuple[Optional[str], Dict[str, ParamValue]]:
    """Return (proc_name, override_params) if an EXEC statement calls a PROC, else (None, {})."""
    proc = params.get("PROC")
    if isinstance(proc, str):
        overrides = {k: v for k, v in params.items() if k not in ("PROC", "_POSITIONAL")}
        return proc, overrides

    if "PGM" not in params:
        positional = params.get("_POSITIONAL")
        if isinstance(positional, str):
            overrides = {k: v for k, v in params.items() if k != "_POSITIONAL"}
            return positional, overrides

    return None, {}


def _collect_dd_overrides(
    statements: List[Dict[str, object]], start: int, calling_step: str
) -> Tuple[Dict[str, Dict[str, ParamValue]], int]:
    """Gather `//callingstep[.procstep].ddname DD ...` overrides that follow an EXEC-of-proc call."""
    overrides: Dict[str, Dict[str, ParamValue]] = {}
    idx = start
    n = len(statements)

    while idx < n:
        stmt = statements[idx]
        if stmt["type"] != "DD" or not stmt.get("name"):
            break
        name = stmt["name"]
        if "." not in name or name.split(".", 1)[0] != calling_step:
            break
        _, dd_path = name.split(".", 1)
        overrides[dd_path] = stmt["params"]  # type: ignore[assignment]
        idx += 1

    return overrides, idx


def expand_procs(
    statements: List[Dict[str, object]], proc_defs: Dict[str, ProcDef]
) -> Tuple[List[Dict[str, object]], List[str]]:
    """Inline every top-level `EXEC <proc>` call, substituting symbolic parameters."""
    expanded: List[Dict[str, object]] = []
    warnings: List[str] = []
    global_symtab: Dict[str, str] = {}

    i = 0
    n = len(statements)
    while i < n:
        stmt = statements[i]
        i += 1

        if stmt["type"] == "SET":
            for key, value in stmt["params"].items():  # type: ignore[union-attr]
                if isinstance(value, str):
                    global_symtab[key] = value
            continue

        if stmt["type"] != "EXEC":
            expanded.append(stmt)
            continue

        proc_name, overrides = _proc_reference(stmt["params"])  # type: ignore[arg-type]
        if proc_name is None:
            expanded.append(stmt)
            continue
        if proc_name not in proc_defs:
            warnings.append(f"unresolved PROC reference: {proc_name}")
            expanded.append(stmt)
            continue

        calling_step = stmt["name"]
        proc_def = proc_defs[proc_name]

        symtab: Dict[str, str] = dict(global_symtab)
        for key, value in proc_def.params.items():
            if isinstance(value, str):
                symtab[key] = value
        for key, value in overrides.items():
            if isinstance(value, str):
                symtab[key] = value

        dd_overrides, i = _collect_dd_overrides(statements, i, calling_step)

        proc_exec_steps = [s for s in proc_def.statements if s["type"] == "EXEC"]
        single_step = len(proc_exec_steps) == 1

        unresolved: Set[str] = set()
        current_proc_step_name: Optional[str] = None

        for inner in proc_def.statements:
            cloned: Dict[str, object] = {
                "type": inner["type"],
                "name": inner["name"],
                "params": substitute_symbols(inner["params"], symtab, unresolved),
            }
            if "condition" in inner:
                cloned["condition"] = substitute_symbols(inner["condition"], symtab, unresolved)
            if inner["type"] == "EXEC":
                current_proc_step_name = inner["name"]  # type: ignore[assignment]
                cloned["name"] = f"{calling_step}.{inner['name']}"
                expanded.append(cloned)
            elif inner["type"] == "DD":
                if inner.get("concatenated"):
                    cloned["concatenated"] = True
                if "instream" in inner:
                    cloned["instream"] = inner["instream"]

                dd_name = inner.get("name") or ""
                override_params = None
                if single_step and dd_name in dd_overrides:
                    override_params = dd_overrides[dd_name]
                elif not single_step and current_proc_step_name:
                    qualified = f"{current_proc_step_name}.{dd_name}"
                    if qualified in dd_overrides:
                        override_params = dd_overrides[qualified]
                if override_params:
                    cloned["params"] = {**cloned["params"], **override_params}  # type: ignore[dict-item]

                expanded.append(cloned)
            else:
                expanded.append(cloned)

        if unresolved:
            warnings.append(
                f"unresolved symbols in {proc_name} (called as {calling_step}): "
                + ",".join(sorted(unresolved))
            )

    return expanded, warnings
