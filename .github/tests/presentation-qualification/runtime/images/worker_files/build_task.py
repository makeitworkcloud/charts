import os
import subprocess
import sys

sys.path.insert(0, "/opt/presentation")
import framing  # noqa: E402

OUT_DIR = "/job/out"
DECK = OUT_DIR + "/deck.pptx"


def child_env():
    env = dict(os.environ)
    # extend_pod_env (EG 0344929cbca688440ba1bc8f5faa074fe54bd595) overwrites
    # templated HOME with the gateway's HOME; re-pin writable dirs.
    env["HOME"] = "/job/home"
    env["TMPDIR"] = "/job/tmp"
    return env


def main():
    for path in ("/job/home", "/job/tmp", OUT_DIR):
        os.makedirs(path, exist_ok=True)

    code = subprocess.run(
        ["node", "/opt/presentation/build_deck.js", DECK],
        env=child_env(),
        cwd="/opt/presentation",
        timeout=180,
    ).returncode

    print(framing.encode_build_status(code), flush=True)

    if code == 0:
        with open(DECK, "rb") as handle:
            for line in framing.encode_file("deckpptx", handle.read()):
                print(line, flush=True)
        print(framing.encode_done("deckpptx"), flush=True)


if __name__ == "__main__":
    main()
