from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Dict, List, Tuple

from jcl_disp_check import check_disp_conflicts
from jcl_dsn import DsnUsage, build_dsn_graph, collect_dsn_usages
from jcl_models import JobAST, to_model
from jcl_parser import build_ast, parse_jcl
from jcl_proc import ProcDef, expand_procs, extract_procs, load_proc_library


def analyze_file(path: str, external_procs: Dict[str, ProcDef]) -> Tuple[JobAST, List[str]]:
    with open(path, encoding="utf-8") as handle:
        statements = parse_jcl(handle.readlines())
    remaining, inline_procs = extract_procs(statements)
    proc_defs = {**external_procs, **inline_procs}
    expanded, warnings = expand_procs(remaining, proc_defs)
    model = to_model(build_ast(expanded))
    return model, warnings


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="JCL static analysis: PROC expansion, DSN dependency graph, DISP/ENQ conflict detection"
    )
    parser.add_argument("jcl_files", nargs="+", help="JCL files to analyze")
    parser.add_argument(
        "--proclib",
        action="append",
        default=[],
        metavar="DIR",
        help="Directory to search for external PROC members (repeatable; first match in order wins)",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    external_procs = load_proc_library(args.proclib)

    all_warnings: List[str] = []
    all_usages: List[DsnUsage] = []

    for path in args.jcl_files:
        model, warnings = analyze_file(path, external_procs)
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
