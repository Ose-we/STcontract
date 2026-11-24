#!/usr/bin/env python3
"""Check that README references to contract functions match lib.rs.

- Every `name(...)` mention in README.md must have the same number of
  arguments as the public function `name` in lib.rs. A mismatch fails the
  check, since the README would show a call that no longer compiles.
- A public contract function that README.md never mentions is reported as a
  warning. It does not fail the check, so new functions do not block CI until
  the README catches up.

The `env` parameter is not counted, because callers never pass it.

Usage: python3 scripts/check_readme_api.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB_RS = ROOT / "contracts" / "sorobanlard" / "src" / "lib.rs"
README = ROOT / "README.md"

CONTRACT_IMPL_RE = re.compile(r"^(?P<indent> *)impl SorobanLardContract\s*\{")
PUB_FN_RE = re.compile(r"^(?P<indent> *)pub fn ([a-z_][a-z0-9_]*)\(")


def public_functions(source):
    """Return {name: arg_count} for each `pub fn` in the contract impl block."""
    functions = {}
    lines = source.splitlines()
    index = 0
    depth = 0
    contract_impl_depth = None
    contract_impl_indent = None
    inside_contract_impl = False
    while index < len(lines):
        line = lines[index]
        impl_match = CONTRACT_IMPL_RE.match(line)
        if impl_match and contract_impl_depth is None:
            contract_impl_depth = depth + 1
            contract_impl_indent = len(impl_match.group("indent")) + 4
            inside_contract_impl = True

        match = PUB_FN_RE.match(line)
        if (
            match
            and inside_contract_impl
            and depth == contract_impl_depth
            and len(match.group("indent")) == contract_impl_indent
        ):
            name = match.group(2)
            header = []
            cursor = index
            while cursor < len(lines):
                header.append(lines[cursor])
                if lines[cursor].rstrip().endswith("{"):
                    break
                cursor += 1
            signature = " ".join(header)
            params = signature[signature.index("(") + 1 : signature.rindex(")")]

            names = [
                p.split(":")[0].strip()
                for p in split_top_level(params)
                if p.strip()
            ]
            names = [n for n in names if n.lstrip("&") != "env"]
            functions[name] = len(names)

        depth += line.count("{") - line.count("}")
        if contract_impl_depth is not None and depth < contract_impl_depth:
            inside_contract_impl = False
        index += 1
    return functions


def split_top_level(text):
    """Split on commas that are not nested inside <>, (), or []."""
    parts, depth, current = [], 0, ""
    for char in text:
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)
    return parts


def mentions(readme, name):
    """Yield the argument count of every `name(...)` mention in README.

    Empty parentheses (`approve_course()`) are prose shorthand, not a
    signature, so they are skipped.
    """
    for match in re.finditer(rf"\b{name}\(", readme):
        start = match.end()
        depth, cursor = 1, start
        while cursor < len(readme) and depth:
            if readme[cursor] == "(":
                depth += 1
            elif readme[cursor] == ")":
                depth -= 1
            cursor += 1
        inner = readme[start : cursor - 1].strip()
        if not inner:
            continue
        arg_count = len([p for p in split_top_level(inner) if p.strip()])
        yield arg_count, readme.count("\n", 0, match.start()) + 1


def main():
    functions = public_functions(LIB_RS.read_text(encoding="utf-8"))
    readme = README.read_text(encoding="utf-8")

    errors = []
    undocumented = []

    for name, expected in sorted(functions.items()):
        found = list(mentions(readme, name))
        if not found:
            undocumented.append(name)
            continue
        for arg_count, line in found:
            if arg_count != expected:
                errors.append(
                    f"README.md:{line}: `{name}` is documented with {arg_count} "
                    f"argument(s) but lib.rs takes {expected}"
                )

    for message in errors:
        print(f"::error file=README.md::{message}")
    if undocumented:
        names = ", ".join(f"`{name}`" for name in undocumented)
        print(f"::warning file=README.md::{len(undocumented)} public function(s) not mentioned "
              f"in README.md: {names}")

    print(f"Checked {len(functions)} public functions: "
          f"{len(errors)} mismatch(es), {len(undocumented)} undocumented.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
