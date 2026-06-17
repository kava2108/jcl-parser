import json
import re
import sys
from typing import Dict, List, Optional, Union

LINE_RE = re.compile(r"^//(\S+)\s+(JOB|EXEC|DD)\b(.*)$")

ParamValue = Union[str, List, Dict]


def split_params(text: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    quote: Optional[str] = None
    paren_depth = 0

    for char in text:
        if quote is None:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
        if char in ('"', "'"):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        if char == "," and quote is None and paren_depth == 0:
            token = "".join(current).strip()
            if token:
                parts.append(token)
            current = []
            continue
        current.append(char)

    token = "".join(current).strip()
    if token:
        parts.append(token)

    return parts


def parse_grouped_value(inner: str) -> ParamValue:
    tokens = split_params(inner)
    if any("=" in t for t in tokens):
        result: Dict[str, ParamValue] = {}
        for t in tokens:
            if "=" in t:
                k, v = t.split("=", 1)
                result[k.strip()] = parse_value(v.strip())
        return result
    return [parse_value(t) for t in tokens]


def parse_value(raw: str) -> ParamValue:
    v = raw.strip()
    if v.startswith("(") and v.endswith(")"):
        return parse_grouped_value(v[1:-1])
    if len(v) >= 2 and v[0] in ("'", '"') and v[-1] == v[0]:
        return v[1:-1]
    return v


def parse_params(text: str) -> Dict[str, ParamValue]:
    params: Dict[str, ParamValue] = {}
    for token in split_params(text):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[key.strip()] = parse_value(value.strip())
    return params


def parse_jcl(lines: List[str]) -> List[Dict[str, object]]:
    result: List[Dict[str, object]] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line or line.startswith("//*"):
            continue

        match = LINE_RE.match(line)
        if not match:
            continue

        name, statement_type, remainder = match.groups()
        result.append(
            {
                "type": statement_type,
                "name": name,
                "params": parse_params(remainder),
            }
        )

    return result


def build_ast(statements: List[Dict[str, object]]) -> Dict[str, object]:
    steps: List[Dict[str, object]] = []
    current_step: Optional[Dict[str, object]] = None
    job: Dict[str, object] = {"type": "JOB", "name": None, "params": {}, "steps": steps}

    for stmt in statements:
        if stmt["type"] == "JOB":
            job = {**stmt, "steps": steps}
        elif stmt["type"] == "EXEC":
            current_step = {**stmt, "dds": []}
            steps.append(current_step)
        elif stmt["type"] == "DD" and current_step is not None:
            current_step["dds"].append(stmt)  # type: ignore[union-attr]

    return job


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--schema":
        from jcl_models import JobAST
        print(json.dumps(JobAST.model_json_schema(), indent=2, ensure_ascii=False))
        return 0

    if len(sys.argv) != 2:
        print("Usage: python jcl_parser.py <jcl-file>")
        print("       python jcl_parser.py --schema")
        return 1

    with open(sys.argv[1], encoding="utf-8") as handle:
        statements = parse_jcl(handle.readlines())

    print(json.dumps(build_ast(statements), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
