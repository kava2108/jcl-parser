from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import List, Tuple

from jcl_disp_check import check_disp_conflicts
from jcl_dsn import DsnUsage, build_dsn_graph, collect_dsn_usages
from jcl_models import JobAST, to_model
from jcl_parser import build_ast, parse_jcl
from jcl_proc import expand_procs, extract_procs


def analyze_file(path: str) -> Tuple[JobAST, List[str]]:
    with open(path, encoding="utf-8") as handle:
        statements = parse_jcl(handle.readlines())
    remaining, proc_defs = extract_procs(statements)
    expanded, warnings = expand_procs(remaining, proc_defs)
    model = to_model(build_ast(expanded))
    return model, warnings


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python jcl_analyze.py <jcl-file> [<jcl-file> ...]")
        return 1

    all_warnings: List[str] = []
    all_usages: List[DsnUsage] = []

    for path in sys.argv[1:]:
        model, warnings = analyze_file(path)
        all_warnings.extend(warnings)
        all_usages.extend(collect_dsn_usages(model))

    graph = build_dsn_graph(all_usages)
    conflicts = check_disp_conflicts(graph)

    report = {
        "warnings": all_warnings,
        "dsn_usages": [asdict(usage) for usage in all_usages],
        "conflicts": [asdict(conflict) for conflict in conflicts],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
