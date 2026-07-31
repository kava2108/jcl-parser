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


def _cond_tokens(value: object) -> List[str]:
    """Flatten a parsed COND value into its leaf string tokens (EVEN, ONLY, RC codes, ...)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        tokens: List[str] = []
        for v in value:
            tokens.extend(_cond_tokens(v))
        return tokens
    return []


def _cond_value(stmt: Dict[str, object]) -> object:
    if stmt.get("type") != "EXEC":
        return None
    return stmt.get("params", {}).get("COND")  # type: ignore[union-attr]


def _is_only_guarded(stmt: Dict[str, object]) -> bool:
    """True if COND=ONLY appears anywhere in this step's COND (bare or combined
    with an RC test, e.g. COND=((4,LT),ONLY)).

    ONLY means "run this step only after an earlier step ABENDed." This tool
    assumes normal completion throughout (no ABEND modeling), so under that
    assumption such a step deterministically never runs - it's excluded from
    analysis entirely rather than turned into a SKIP/RUN branch.
    """
    cond = _cond_value(stmt)
    if not cond:
        return False
    return any(tok.upper() == "ONLY" for tok in _cond_tokens(cond))


def _has_branchable_cond(stmt: Dict[str, object]) -> bool:
    """True for a COND= that should become a SKIP/RUN branch.

    A bare COND=EVEN is excluded: under the no-ABEND assumption it behaves
    like an unconditional step (EVEN only matters when a prior step actually
    ABENDed), so there's no useful skip/run branch to model. COND=ONLY is
    handled separately by `_is_only_guarded` (full exclusion, not a branch).
    """
    cond = _cond_value(stmt)
    if not cond:
        return False
    if isinstance(cond, str) and cond.upper() == "EVEN":
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
    statements: List[Dict[str, object]],
    idx: int,
    wrap_cond: bool,
    excluded_only_steps: List[str],
) -> Tuple[List[Node], int]:
    """Recursive-descent parse into a node tree.

    `// IF ... THEN / ELSE / ENDIF` markers are always turned into IfNodes (and
    consumed as control structure, not present in the output). A COND=ONLY step
    is dropped entirely (see `_is_only_guarded`) and its name recorded. When
    `wrap_cond` is True, any other EXEC step carrying a branchable COND= is
    turned into an implicit IfNode: COND test true -> the step is bypassed
    (empty branch), false -> the step (and its DDs) run. We can never know
    which at analysis time, so both are modeled as scenarios, same as an
    explicit IF.
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
            then_nodes, idx = _parse_sequence(statements, idx, wrap_cond, excluded_only_steps)

            else_nodes: List[Node] = []
            if idx < n and statements[idx]["type"] == "ELSE":
                idx += 1
                else_nodes, idx = _parse_sequence(statements, idx, wrap_cond, excluded_only_steps)

            if idx < n and statements[idx]["type"] == "ENDIF":
                idx += 1

            nodes.append(IfNode(condition=condition, then_branch=then_nodes, else_branch=else_nodes))
            continue

        if stmt["type"] == "EXEC" and _is_only_guarded(stmt):
            excluded_only_steps.append(str(stmt.get("name")))
            _, idx = _consume_step_group(statements, idx)
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

    A COND=ONLY step is excluded from analysis entirely (see `_is_only_guarded`)
    and reported in the returned warnings.

    COND= steps can be numerous in legacy JCL (a COND guarding nearly every
    step is a common pattern), and each one doubles the scenario count. If
    modeling all of them would exceed `max_scenarios`, COND-driven branching is
    disabled for this job (explicit IF/THEN/ELSE is still modeled in full) and
    a warning is returned instead.
    """
    warnings: List[str] = []
    excluded_only_steps: List[str] = []

    nodes, _ = _parse_sequence(statements, 0, wrap_cond=True, excluded_only_steps=excluded_only_steps)
    if _count_variants(nodes) > max_scenarios:
        cond_count = sum(1 for s in statements if _has_branchable_cond(s))
        warnings.append(
            f"COND-based branching disabled: {cond_count} COND-bearing steps would "
            f"produce more than {max_scenarios} scenarios; their DSN usages are only "
            "flagged as conditional, not split into separate scenarios"
        )
        excluded_only_steps = []
        nodes, _ = _parse_sequence(
            statements, 0, wrap_cond=False, excluded_only_steps=excluded_only_steps
        )

    if excluded_only_steps:
        warnings.append(
            f"excluded {len(excluded_only_steps)} COND=ONLY step(s) from analysis "
            "(they only run after an earlier step ABENDs, which this tool assumes "
            "doesn't happen): " + ", ".join(excluded_only_steps)
        )

    flattened = _flatten(nodes)

    if len(flattened) == 1 and not flattened[0][0]:
        return [Scenario(label="default", statements=flattened[0][1])], warnings

    return [
        Scenario(label=" & ".join(labels), statements=stmts) for labels, stmts in flattened
    ], warnings
