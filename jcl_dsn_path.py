from __future__ import annotations

DEFAULT_BASE_DIR = "data"


def dsn_to_path(dsn: str, base_dir: str = DEFAULT_BASE_DIR) -> str:
    """Map an MVS dataset name to a filesystem path under `base_dir`.

    Each qualifier (dot-separated segment) becomes a directory level, e.g.
    `HLQ.MID.LOW` -> `data/HLQ/MID/LOW`. A parenthesized suffix - a PDS
    member (`HLQ.PDS(MEMBER)`) or a GDG relative generation
    (`HLQ.GDG(+1)`) - becomes one extra path segment: `data/HLQ/PDS/MEMBER`,
    `data/HLQ/GDG/+1`.
    """
    name = dsn
    qualifier = None
    if "(" in dsn and dsn.endswith(")"):
        idx = dsn.index("(")
        name, qualifier = dsn[:idx], dsn[idx + 1 : -1]

    segments = name.split(".")
    if qualifier:
        segments.append(qualifier)

    return "/".join([base_dir, *segments])
