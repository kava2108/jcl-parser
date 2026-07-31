from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from jcl_dsn import DsnUsage

Severity = Literal["error", "warning", "info"]

EXCLUSIVE_STATUSES = {"OLD", "NEW"}


@dataclass
class DispConflict:
    dsn: str
    severity: Severity
    reason: str
    usages: List[DsnUsage]


def _by_job(usages: List[DsnUsage]) -> Dict[Optional[str], List[DsnUsage]]:
    grouped: Dict[Optional[str], List[DsnUsage]] = {}
    for usage in usages:
        grouped.setdefault(usage.job_name, []).append(usage)
    return grouped


def _check_single_job_rules(dsn: str, usages: List[DsnUsage]) -> List[DispConflict]:
    """R1 (duplicate NEW), R2 (read before create), R3 (use after delete),
    R5 (PASS never reclaimed).

    Assumes `usages` are already in the sequential step order of a single job.
    """
    conflicts: List[DispConflict] = []
    created = False
    deleted = False
    read_before_create_flagged = False
    last_index = len(usages) - 1

    for index, usage in enumerate(usages):
        status = (usage.disp_status or "").upper()
        normal = (usage.disp_normal or "").upper()

        if deleted:
            conflicts.append(
                DispConflict(
                    dsn=dsn,
                    severity="error",
                    reason=(
                        f"{usage.step_name}.{usage.dd_name} references {dsn} "
                        "after it was deleted by an earlier step"
                    ),
                    usages=[usage],
                )
            )

        if status == "NEW":
            if created:
                conflicts.append(
                    DispConflict(
                        dsn=dsn,
                        severity="error",
                        reason=(
                            f"{usage.step_name}.{usage.dd_name} allocates {dsn} as NEW "
                            "but an earlier step already created it without freeing it"
                        ),
                        usages=[usage],
                    )
                )
            created = True
        elif status in ("OLD", "SHR", "MOD") and not created and not read_before_create_flagged:
            conflicts.append(
                DispConflict(
                    dsn=dsn,
                    severity="info",
                    reason=(
                        f"{usage.step_name}.{usage.dd_name} reads {dsn} with DISP={status} "
                        "without an earlier step creating it in this job - "
                        "possibly an external/pre-existing dataset"
                    ),
                    usages=[usage],
                )
            )
            read_before_create_flagged = True

        if normal == "DELETE":
            # Only the normal-completion disposition matters here: static analysis
            # assumes steps run to normal completion (default COND behavior), so an
            # abnormal-termination DELETE never actually happens on the path being walked.
            deleted = True

        if normal == "PASS" and index == last_index:
            # PASS only carries a dataset forward to a later step in the same job;
            # if this is the last usage of the DSN in the job, nothing ever claims
            # it, so the system deletes it at job end.
            conflicts.append(
                DispConflict(
                    dsn=dsn,
                    severity="warning",
                    reason=(
                        f"{usage.step_name}.{usage.dd_name} passes {dsn} with DISP=(...,PASS) "
                        "but no later step in this job references it - it will be "
                        "deleted at job end"
                    ),
                    usages=[usage],
                )
            )

    return conflicts


def _check_cross_job_rule(
    dsn: str, by_job: Dict[Optional[str], List[DsnUsage]]
) -> List[DispConflict]:
    """R4: two or more jobs both hold an exclusive DISP on the same DSN.

    JCL alone can't prove whether these jobs run concurrently, so this is a
    heuristic warning, not a hard error.
    """
    if len(by_job) < 2:
        return []

    exclusive_by_job: Dict[Optional[str], List[DsnUsage]] = {}
    for job_name, usages in by_job.items():
        exclusive = [u for u in usages if (u.disp_status or "").upper() in EXCLUSIVE_STATUSES]
        if exclusive:
            exclusive_by_job[job_name] = exclusive

    if len(exclusive_by_job) < 2:
        return []

    involved = [u for usages in exclusive_by_job.values() for u in usages]
    job_labels = ", ".join(str(job_name) for job_name in exclusive_by_job.keys())
    return [
        DispConflict(
            dsn=dsn,
            severity="warning",
            reason=(
                f"multiple jobs ({job_labels}) hold exclusive DISP (OLD/NEW) on {dsn}; "
                "execution order between them is unknown from JCL alone"
            ),
            usages=involved,
        )
    ]


def check_disp_conflicts(dsn_graph: Dict[str, List[DsnUsage]]) -> List[DispConflict]:
    conflicts: List[DispConflict] = []
    for dsn, usages in dsn_graph.items():
        by_job = _by_job(usages)
        for job_usages in by_job.values():
            conflicts.extend(_check_single_job_rules(dsn, job_usages))
        conflicts.extend(_check_cross_job_rule(dsn, by_job))
    return conflicts
