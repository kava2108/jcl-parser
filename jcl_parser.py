import json
import re
import sys
from typing import Dict, List

LINE_RE = re.compile(r"^//(\S+)\s+(JOB|EXEC|DD)\b(.*)$")


def split_params(text: str) -> List[str]:
    parts: List[str] = []
    current: List[str] = []
    quote = None

    for char in text:
        if char in ('"', "'"):
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
        if char == "," and quote is None:
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


def parse_params(text: str) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for token in split_params(text):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        params[key.strip()] = value.strip().strip("'").strip('"')
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


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python jcl_parser.py <jcl-file>")
        return 1

    with open(sys.argv[1], encoding="utf-8") as handle:
        parsed = parse_jcl(handle.readlines())

    print(json.dumps(parsed, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
