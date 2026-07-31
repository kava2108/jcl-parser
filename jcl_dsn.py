from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from jcl_models import JobAST


@dataclass
class DsnUsage:
    dsn: str
    step_name: str
    dd_name: Optional[str]
    disp_status: Optional[str]
    disp_normal: Optional[str]
    disp_abnormal: Optional[str]
    order: int
    job_name: Optional[str] = None
    scenario: Optional[str] = None
    conditional: bool = False


def _disp_parts(disp: object) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if isinstance(disp, str):
        return disp, None, None
    if isinstance(disp, list):
        values = [v if isinstance(v, str) else None for v in disp]
        values += [None] * (3 - len(values))
        return values[0], values[1], values[2]
    return None, None, None


def _normalize_dsn(dsn: str) -> str:
    """Strip a GDG relative generation reference, e.g. HLQ.GDG(+1) -> HLQ.GDG."""
    if "(" in dsn and dsn.endswith(")"):
        return dsn[: dsn.index("(")]
    return dsn


def collect_dsn_usages(model: JobAST, scenario: Optional[str] = None) -> List[DsnUsage]:
    """Flatten DSN+DISP info from every DD across an (expanded) job's steps, in step order.

    `scenario` tags every usage with the branch (IF/THEN/ELSE) it came from, if any
    (see jcl_branch.py). A step whose EXEC carries a non-empty COND= is marked
    `conditional=True`: COND depends on a runtime RC value we can't know statically,
    so its DDs are flagged as uncertain rather than split into separate scenarios.
    """
    usages: List[DsnUsage] = []
    order = 0
    for step in model.steps:
        conditional = bool(step.params.get("COND"))
        for dd in step.dds:
            dsn = dd.params.get("DSN")
            if not isinstance(dsn, str) or not dsn:
                continue
            status, normal, abnormal = _disp_parts(dd.params.get("DISP"))
            usages.append(
                DsnUsage(
                    dsn=_normalize_dsn(dsn),
                    step_name=step.name,
                    dd_name=dd.name,
                    disp_status=status,
                    disp_normal=normal,
                    disp_abnormal=abnormal,
                    order=order,
                    job_name=model.name,
                    scenario=scenario,
                    conditional=conditional,
                )
            )
            order += 1
    return usages


def build_dsn_graph(usages: List[DsnUsage]) -> Dict[str, List[DsnUsage]]:
    """Group usages by DSN, preserving access order — a per-dataset read/write timeline."""
    graph: Dict[str, List[DsnUsage]] = {}
    for usage in sorted(usages, key=lambda u: u.order):
        graph.setdefault(usage.dsn, []).append(usage)
    return graph
