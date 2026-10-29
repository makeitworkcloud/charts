import base64
import binascii
import hashlib
import os
import subprocess
import sys

sys.path.insert(0, "/opt/presentation")
import framing  # noqa: E402

IN_DIR = "/job/in"
OUT_DIR = "/job/out"
B64_PATH = IN_DIR + "/deck.b64"
DIGEST_PATH = IN_DIR + "/deck.sha256"
DECK = OUT_DIR + "/deck.pptx"
PDF = OUT_DIR + "/deck.pdf"
PNG = OUT_DIR + "/deck.png"
MAX_B64_CHARS = 6 * 1024 * 1024
MAX_DECK_BYTES = 4 * 1024 * 1024
PPTX_MAGIC = b"PK\x03\x04"


def child_env():
    env = dict(os.environ)
    env["HOME"] = "/job/home"
    env["TMPDIR"] = "/job/tmp"
    return env


def run_stage(argv, timeout):
    return subprocess.run(argv, env=child_env(), timeout=timeout).returncode


def load_upload():
    with open(B64_PATH, "r", encoding="ascii") as handle:
        b64 = handle.read().strip()
    with open(DIGEST_PATH, "r", encoding="ascii") as handle:
        expected = handle.read().strip()
    if not 64 == len(expected):
        raise ValueError("digest length")
    if len(b64) > MAX_B64_CHARS:
        raise ValueError("upload bound")
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("base64") from exc
    if len(data) > MAX_DECK_BYTES or not data.startswith(PPTX_MAGIC):
        raise ValueError("deck bound or signature")
    return data, expected


def main():
    for path in ("/job/home", "/job/tmp", IN_DIR, OUT_DIR):
        os.makedirs(path, exist_ok=True)

    # Freshness evidence: reported before any write of DECK in this pod.
    print(
        framing.encode_kv("preexisting_deckpptx", "true" if os.path.exists(DECK) else "false"),
        flush=True,
    )

    code = 3
    try:
        data, expected = load_upload()
        digest_ok = hashlib.sha256(data).hexdigest() == expected
        print(framing.encode_kv("render_digest_ok", "true" if digest_ok else "false"), flush=True)
        if not digest_ok:
            raise ValueError("digest mismatch")
        with open(DECK, "wb") as handle:
            handle.write(data)
        for stale in (PDF, PNG):
            try:
                os.remove(stale)
            except FileNotFoundError:
                pass
        code = run_stage(
            [
                "soffice",
                "--headless",
                "--norestore",
                "--nolockcheck",
                "-env:UserInstallation=file:///job/home/loprofile",
                "--convert-to",
                "pdf",
                "--outdir",
                OUT_DIR,
                DECK,
            ],
            300,
        )
        if code == 0:
            code = run_stage(
                ["pdftoppm", "-png", "-r", "96", "-singlefile", PDF, PNG[:-4]],
                120,
            )
    except (OSError, ValueError):
        code = code or 3

    print(framing.encode_build_status(code), flush=True)

    if code == 0:
        with open(PNG, "rb") as handle:
            for line in framing.encode_file("deckpng", handle.read()):
                print(line, flush=True)
        print(framing.encode_done("deckpng"), flush=True)


if __name__ == "__main__":
    main()
