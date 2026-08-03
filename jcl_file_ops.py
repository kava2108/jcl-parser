from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from jcl_dsn import disp_parts
from jcl_dsn_path import DEFAULT_BASE_DIR, dsn_to_path
from jcl_models import DDStatement, ExecStep, JobAST

CREATE_STATUSES = {"NEW"}
EXISTING_STATUSES = {"OLD", "SHR", "MOD"}


@dataclass
class DDFileOp:
    """Filesystem plan for one DD: the path its DSN resolves to, plus the
    shell commands needed before/after the step to realize its DISP.
    """

    dd_name: str
    dsn: str
    path: str
    disp_status: Optional[str]
    disp_normal: Optional[str]
    disp_abnormal: Optional[str]
    pre_ops: List[str] = field(default_factory=list)
    post_ops: List[str] = field(default_factory=list)


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _dirname(path: str) -> str:
    return path.rsplit("/", 1)[0] if "/" in path else "."


def plan_dd_file_op(dd: DDStatement, base_dir: str = DEFAULT_BASE_DIR) -> Optional[DDFileOp]:
    """Translate one DD's DSN/DISP into filesystem operations.

    NEW allocates the file (mkdir -p its directory, then create it empty);
    OLD/SHR/MOD expect it to already exist, so a `test -e` guard is emitted.
    Only the normal-completion disposition (2nd DISP subparam) drives
    post-step behavior, matching the "all steps complete normally"
    assumption used by the rest of this tool (see jcl_disp_check.py): DELETE
    removes the file, CATLG/KEEP leave it in place, and PASS is a no-op
    since a later step in the same job resolves the same DSN to the same
    path anyway.
    """
    dsn = dd.params.get("DSN")
    if not isinstance(dsn, str) or not dsn:
        return None

    status, normal, abnormal = disp_parts(dd.params.get("DISP"))
    status = (status or "").upper()
    normal = (normal or "").upper()
    abnormal = (abnormal or "").upper()
    path = dsn_to_path(dsn, base_dir)

    pre_ops: List[str] = []
    post_ops: List[str] = []

    if status in CREATE_STATUSES:
        pre_ops.append(f"mkdir -p {_shell_quote(_dirname(path))}")
        pre_ops.append(f": > {_shell_quote(path)}")
    elif status in EXISTING_STATUSES:
        pre_ops.append(f"test -e {_shell_quote(path)}")

    if normal == "DELETE":
        post_ops.append(f"rm -f {_shell_quote(path)}")

    return DDFileOp(
        dd_name=dd.name or "",
        dsn=dsn,
        path=path,
        disp_status=status or None,
        disp_normal=normal or None,
        disp_abnormal=abnormal or None,
        pre_ops=pre_ops,
        post_ops=post_ops,
    )


def plan_step_file_ops(step: ExecStep, base_dir: str = DEFAULT_BASE_DIR) -> List[DDFileOp]:
    ops = []
    for dd in step.dds:
        op = plan_dd_file_op(dd, base_dir)
        if op is not None:
            ops.append(op)
    return ops


def plan_job_file_ops(model: JobAST, base_dir: str = DEFAULT_BASE_DIR) -> List[List[DDFileOp]]:
    return [plan_step_file_ops(step, base_dir) for step in model.steps]
