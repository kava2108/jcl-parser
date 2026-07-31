from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Union

Node = Union[Dict[str, object], "IfNode"]

DEFAULT_MAX_SCENARIOS = 64


@dataclass
class IfNode:
    condition: str
    then_branch: List[Node] = field(default_factory=list)
    else_branch: List[Node] = field(default_factory=list)
    then_tag: str = "THEN"
    else_tag: str = "ELSE"


@dataclass
class Scenario:
    label: str
    statements: List[Dict[str, object]]


def _cond_to_str(value: object) -> str:
    if isinstance(value, list):
        if value and isinstance(value[0], list):
            return " OR ".join(_cond_to_str(v) for v in value)
        return "(" + ",".join(str(v) for v in value) + ")"
    return str(value)


def _has_branchable_cond(stmt: Dict[str, object]) -> bool:
    """True for a normal COND=(code,op[,step]) test on an EXEC step.

    COND=EVEN/COND=ONLY are excluded: they don't compare an RC, they change
    whether this step runs after an earlier ABEND, which is a different kind
    of uncertainty than a skip/run branch and isn't modeled here.
    """
    if stmt.get("type") != "EXEC":
        return False
    cond = stmt.get("params", {}).get("COND")  # type: ignore[union-attr]
    if not cond:
        return False
    if isinstance(cond, str) and cond.upper() in ("EVEN", "ONLY"):
        return False
    return True


def _consume_step_group(
    statements: List[Dict[str, object]], idx: int
) -> Tuple[List[Dict[str, object]], int]:
    """Collect an EXEC statement plus the DD statements that belong to it."""
    group = [statements[idx]]
    idx += 1
    n = len(statements)
    while idx < n and statements[idx]["type"] == "DD":
        group.append(statements[idx])
        idx += 1
    return group, idx


def _parse_sequence(
    statements: List[Dict[str, object]], idx: int, wrap_cond: bool
) -> Tuple[List[Node], int]:
    """Recursive-descent parse into a node tree.

    `// IF ... THEN / ELSE / ENDIF` markers are always turned into IfNodes (and
    consumed as control structure, not present in the output). When `wrap_cond`
    is True, an EXEC step carrying a branchable COND= is *also* turned into an
    implicit IfNode: COND tests true -> the step is bypassed (empty branch),
    tests false -> the step (and its DDs) run. We can never know which at
    analysis time, so both are modeled as scenarios, same as an explicit IF.
    """
    nodes: List[Node] = []
    n = len(statements)

    while idx < n:
        stmt = statements[idx]
        if stmt["type"] in ("ELSE", "ENDIF"):
            return nodes, idx

        if stmt["type"] == "IF":
            condition = str(stmt.get("condition", ""))
            idx += 1
            then_nodes, idx = _parse_sequence(statements, idx, wrap_cond)

            else_nodes: List[Node] = []
            if idx < n and statements[idx]["type"] == "ELSE":
                idx += 1
                else_nodes, idx = _parse_sequence(statements, idx, wrap_cond)

            if idx < n and statements[idx]["type"] == "ENDIF":
                idx += 1

            nodes.append(IfNode(condition=condition, then_branch=then_nodes, else_branch=else_nodes))
            continue

        if wrap_cond and _has_branchable_cond(stmt):
            cond_label = f"COND={_cond_to_str(stmt['params']['COND'])}"  # type: ignore[index]
            step_group, idx = _consume_step_group(statements, idx)
            nodes.append(
                IfNode(
                    condition=cond_label,
                    then_branch=[],
                    else_branch=step_group,
                    then_tag="SKIP",
                    else_tag="RUN",
                )
            )
            continue

        nodes.append(stmt)
        idx += 1

    return nodes, idx


def _flatten(nodes: List[Node]) -> List[Tuple[List[str], List[Dict[str, object]]]]:
    """Expand a node list into mutually-exclusive (labels, statements) variants.

    Every IfNode doubles the variant count (cartesian product across sequential
    or nested branch points) since its two branches are structurally exclusive.
    """
    results: List[Tuple[List[str], List[Dict[str, object]]]] = [([], [])]

    for node in nodes:
        if isinstance(node, IfNode):
            branch_variants: List[Tuple[List[str], List[Dict[str, object]]]] = []
            for labels, stmts in _flatten(node.then_branch):
                branch_variants.append(([f"{node.condition}:{node.then_tag}", *labels], stmts))
            for labels, stmts in _flatten(node.else_branch):
                branch_variants.append(([f"{node.condition}:{node.else_tag}", *labels], stmts))

            results = [
                (base_labels + extra_labels, base_stmts + extra_stmts)
                for base_labels, base_stmts in results
                for extra_labels, extra_stmts in branch_variants
            ]
        else:
            results = [(labels, stmts + [node]) for labels, stmts in results]

    return results


def _count_variants(nodes: List[Node]) -> int:
    """Cheaply estimate how many scenarios `_flatten` would produce, without
    materializing them."""
    total = 1
    for node in nodes:
        if isinstance(node, IfNode):
            total *= _count_variants(node.then_branch) + _count_variants(node.else_branch)
    return total


def build_scenarios(
    statements: List[Dict[str, object]], max_scenarios: int = DEFAULT_MAX_SCENARIOS
) -> Tuple[List[Scenario], List[str]]:
    """Split a flat (PROC-expanded) statement list into mutually-exclusive scenarios
    driven by `// IF ... THEN / ELSE / ENDIF` and by branchable `COND=` tests on
    individual EXEC steps. Statements outside any branch are present in every
    scenario. Input with no branching at all yields a single "default" scenario.

    COND= steps can be numerous in legacy JCL (a COND guarding nearly every
    step is a common pattern), and each one doubles the scenario count. If
    modeling all of them would exceed `max_scenarios`, COND-driven branching is
    disabled for this job (explicit IF/THEN/ELSE is still modeled in full) and
    a warning is returned instead.
    """
    warnings: List[str] = []

    nodes, _ = _parse_sequence(statements, 0, wrap_cond=True)
    if _count_variants(nodes) > max_scenarios:
        cond_count = sum(1 for s in statements if _has_branchable_cond(s))
        warnings.append(
            f"COND-based branching disabled: {cond_count} COND-bearing steps would "
            f"produce more than {max_scenarios} scenarios; their DSN usages are only "
            "flagged as conditional, not split into separate scenarios"
        )
        nodes, _ = _parse_sequence(statements, 0, wrap_cond=False)

    flattened = _flatten(nodes)

    if len(flattened) == 1 and not flattened[0][0]:
        return [Scenario(label="default", statements=flattened[0][1])], warnings

    return [
        Scenario(label=" & ".join(labels), statements=stmts) for labels, stmts in flattened
    ], warnings
