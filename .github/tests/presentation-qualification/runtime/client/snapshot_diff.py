#!/usr/bin/env python3
"""Compare projected namespace/name/UID snapshots without retaining pod specs.

Zero mode rejects all endpoint differences; scope mode rejects differences
outside the fixture namespace. Neither mode observes between-snapshot churn.
"""

import re
import sys


def load(path):
    result = set()
    with open(path, "r", encoding="utf-8") as handle:
        for row in handle:
            fields = row.rstrip("\n").split("\t")
            if len(fields) != 3 or not all(re.fullmatch(r"[a-z0-9.-]+", field) for field in fields):
                raise ValueError("malformed pod metadata snapshot")
            pod = tuple(fields)
            if pod in result:
                raise ValueError("duplicate pod metadata snapshot row")
            result.add(pod)
    return result


def violations(before, after, fixed_namespace, mode):
    delta = before ^ after
    if mode == "zero":
        return delta
    if mode == "scope":
        return {pod for pod in delta if pod[0] != fixed_namespace}
    raise ValueError("invalid snapshot comparison mode")


def main():
    if len(sys.argv) != 5:
        print("usage: snapshot_diff.py <before.tsv> <after.tsv> <fixed-namespace> <zero|scope>", file=sys.stderr)
        sys.exit(6)
    before_path, after_path, fixed_namespace, mode = sys.argv[1:5]
    before = load(before_path)
    after = load(after_path)
    delta = (after - before) | (before - after)
    for pod in sorted(delta):
        print("POD_DELTA %s/%s" % (pod[0], pod[1]))
    invalid = sorted(violations(before, after, fixed_namespace, mode))
    if invalid:
        print(
            "POD_SNAPSHOT_VIOLATION count=%d first=%s/%s"
            % (len(invalid), invalid[0][0], invalid[0][1]),
            file=sys.stderr,
        )
        sys.exit(6)
    print("POD_SNAPSHOT_OK delta=%d mode=%s" % (len(delta), mode))


if __name__ == "__main__":
    main()
