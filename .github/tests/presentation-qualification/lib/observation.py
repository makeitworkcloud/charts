"""Bounded, kernel-bound rendezvous for the disposable qualification fixture."""

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

MAX_BYTES = 256


class ObservationError(RuntimeError):
    pass


def validate_id(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ObservationError("invalid observation identifier") from None
    return value


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_message(raw):
    try:
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise ValueError
        doc = json.loads(raw.decode("ascii"), object_pairs_hook=_unique_pairs)
        if not isinstance(doc, dict) or set(doc) != {"version", "kernel_id"}:
            raise ValueError
        if type(doc["version"]) is not int or doc["version"] != 1:
            raise ValueError
        return validate_id(doc["kernel_id"])
    except (ValueError, UnicodeError):
        raise ObservationError("invalid observation message") from None


def read_message(path):
    try:
        with open(path, "rb") as handle:
            return parse_message(handle.read(MAX_BYTES + 1))
    except FileNotFoundError:
        return None
    except OSError:
        raise ObservationError("observation read failed") from None


def publish(path, kernel_id):
    kernel_id = validate_id(kernel_id)
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    if path.exists():
        raise ObservationError("observation message already exists")
    payload = json.dumps({"version": 1, "kernel_id": kernel_id}).encode("ascii")
    try:
        with open(temporary, "xb") as handle:
            handle.write(payload)
        os.replace(temporary, path)
    except OSError:
        raise ObservationError("observation publish failed") from None


def wait_release(directory, kernel_id, timeout=120):
    kernel_id = validate_id(kernel_id)
    if not 0 < timeout <= 120:
        raise ObservationError("invalid observation timeout")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        released_id = read_message(Path(directory) / "release.json")
        if released_id is not None:
            if released_id != kernel_id:
                raise ObservationError("observation release mismatch")
            return
        time.sleep(0.05)
    raise ObservationError("observation release deadline")


def rendezvous(directory, kernel_id):
    directory = Path(directory)
    if (directory / "release.json").exists():
        raise ObservationError("stale observation release")
    publish(directory / "ready.json", kernel_id)
    wait_release(directory, kernel_id)


def release(directory, kernel_id):
    kernel_id = validate_id(kernel_id)
    directory = Path(directory)
    if read_message(directory / "ready.json") != kernel_id:
        raise ObservationError("observation ready mismatch")
    publish(directory / "release.json", kernel_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("read", "release"))
    parser.add_argument("directory")
    parser.add_argument("kernel_id", nargs="?")
    args = parser.parse_args()
    try:
        if args.command == "read":
            kernel_id = read_message(Path(args.directory) / "ready.json")
            if kernel_id is None:
                return 2
            print(kernel_id)
        else:
            release(args.directory, args.kernel_id)
        return 0
    except ObservationError:
        print("OBSERVATION_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
