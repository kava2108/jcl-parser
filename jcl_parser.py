import json
import re
import sys
from typing import Dict, List, Optional, Union

LINE_RE = re.compile(r"^//(\S+)\s+(JOB|EXEC|DD|PROC|PEND)\b(.*)$")
ANON_RE = re.compile(r"^//\s+(DD|SET|PEND)\b(.*)$")
CONT_RE = re.compile(r"^//\s+(\S.*)$")

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
            if "_POSITIONAL" not in params:
                params["_POSITIONAL"] = token
            continue
        key, value = token.split("=", 1)
        params[key.strip()] = parse_value(value.strip())
    return params


def _needs_continuation(text: str) -> bool:
    """True if the operand field ends with an unclosed paren or a trailing comma."""
    depth = 0
    quote: Optional[str] = None
    stripped = text.rstrip()

    for char in stripped:
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1

    return depth > 0 or stripped.endswith(",")


def merge_continuations(lines: List[str]) -> List[str]:
    """Join JCL continuation lines (trailing comma / unclosed paren) into one logical line."""
    merged: List[str] = []
    buffer: Optional[str] = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")

        if line.startswith("//*"):
            if buffer is not None:
                merged.append(buffer)
                buffer = None
            merged.append(line)
            continue

        if buffer is not None and _needs_continuation(buffer):
            cont_match = CONT_RE.match(line)
            if cont_match:
                buffer = buffer.rstrip() + cont_match.group(1)
                continue

        if buffer is not None:
            merged.append(buffer)
        buffer = line

    if buffer is not None:
        merged.append(buffer)

    return merged


def _is_instream(remainder: str) -> bool:
    tokens = split_params(remainder.strip())
    return bool(tokens) and tokens[0] in ("*", "DATA")


def _instream_delimiter(params: Dict[str, ParamValue]) -> str:
    dlm = params.get("DLM")
    if isinstance(dlm, str) and dlm:
        return dlm
    return "/*"


def parse_jcl(lines: List[str]) -> List[Dict[str, object]]:
    result: List[Dict[str, object]] = []
    merged_lines = merge_continuations(lines)

    idx = 0
    while idx < len(merged_lines):
        line = merged_lines[idx].rstrip()
        idx += 1

        if not line or line.startswith("//*"):
            continue

        match = LINE_RE.match(line)
        concatenated = False

        if match:
            name, statement_type, remainder = match.groups()
        else:
            anon_match = ANON_RE.match(line)
            if not anon_match:
                continue
            name = None
            statement_type = anon_match.group(1)
            remainder = anon_match.group(2)
            if statement_type == "DD":
                concatenated = True

        params = parse_params(remainder)
        statement: Dict[str, object] = {
            "type": statement_type,
            "name": name,
            "params": params,
        }
        if concatenated:
            statement["concatenated"] = True

        if statement_type == "DD" and _is_instream(remainder):
            delimiter = _instream_delimiter(params)
            data_lines: List[str] = []
            while idx < len(merged_lines):
                candidate = merged_lines[idx].rstrip("\n")
                if candidate.rstrip() == delimiter or candidate.startswith(delimiter):
                    idx += 1
                    break
                data_lines.append(candidate)
                idx += 1
            statement["instream"] = data_lines

        result.append(statement)

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
