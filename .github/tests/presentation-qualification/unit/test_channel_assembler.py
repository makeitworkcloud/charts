import base64
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import framing  # noqa: E402

PARENT = "exec-msg-id-1"
OTHER = "some-other-parent"


def feed_lines(asm, lines, parent=PARENT):
    for line in lines:
        asm.feed(parent, line + "\n")


class EncodeDecodeRoundtrip(unittest.TestCase):
    def test_two_files_roundtrip(self):
        pptx = b"PK\x03\x04" + os.urandom(70000)
        png = b"\x89PNG\r\n\x1a\n" + os.urandom(40000)
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpptx", pptx))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        feed_lines(asm, framing.encode_file("deckpng", png))
        feed_lines(asm, [framing.encode_done("deckpng")])
        artifacts = asm.finish()
        self.assertEqual(artifacts["deckpptx"].data, pptx)
        self.assertEqual(artifacts["deckpng"].data, png)
        self.assertEqual(artifacts["deckpptx"].sha256, hashlib.sha256(pptx).hexdigest())
        self.assertEqual(asm.build_exit_code, 0)
        self.assertEqual(asm.ignored_parent, 0)

    def test_empty_file_roundtrip(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpptx", b""))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        artifacts = asm.finish()
        self.assertEqual(artifacts["deckpptx"].data, b"")
        self.assertEqual(artifacts["deckpptx"].total_chunks, 1)

    def test_split_stream_buffers_lines(self):
        payload = b"PK\x03\x04" + b"x" * 100
        lines = framing.encode_file("deckpptx", payload)
        asm = framing.Assembler(PARENT)
        blob = framing.encode_build_status(0) + "\n" + "\n".join(lines) + "\n" + framing.encode_done("deckpptx") + "\n"
        for i in range(0, len(blob), 7):
            asm.feed(PARENT, blob[i : i + 7])
        self.assertEqual(asm.finish()["deckpptx"].data, payload)


class WrongParentFiltering(unittest.TestCase):
    def test_other_parent_ignored(self):
        payload = b"PK\x03\x04data"
        asm = framing.Assembler(PARENT)
        asm.feed(OTHER, framing.encode_build_status(0) + "\n")
        feed_lines(asm, framing.encode_file("deckpptx", payload))
        asm.feed(OTHER, "PQB1|evil|1|4|" + "0" * 64 + "|0|AAAA\n")
        feed_lines(asm, [framing.encode_done("deckpptx")])
        asm.feed(OTHER, framing.encode_done("evil") + "\n")
        artifacts = asm.finish()
        self.assertEqual(artifacts["deckpptx"].data, payload)
        self.assertEqual(asm.ignored_parent, 3)
        self.assertNotIn("evil", artifacts)


class ProtocolErrors(unittest.TestCase):
    # Delivery order is not constrained by the protocol: chunks may arrive in
    # any order as long as every index arrives exactly once.
    def test_out_of_order_delivery_accepted(self):
        payload = b"PK\x03\x04" + b"0123456789abcdef"
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        lines = framing.encode_file("deckpptx", payload, chunk_bytes=4)
        for index in reversed(range(len(lines))):
            feed_lines(asm, [lines[index]])
        feed_lines(asm, [framing.encode_done("deckpptx")])
        self.assertEqual(asm.finish()["deckpptx"].data, payload)

    def test_duplicate_chunk_rejected(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        lines = framing.encode_file("deckpptx", b"0123456789abcdef", chunk_bytes=4)
        feed_lines(asm, [lines[0]])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [lines[0]])

    def test_gap_rejected_at_finish(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        lines = framing.encode_file("deckpptx", b"0123456789abcdef", chunk_bytes=4)
        feed_lines(asm, [lines[0]])
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.IncompleteError):
            asm.finish()

    def test_done_before_header(self):
        asm = framing.Assembler(PARENT)
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_done("deckpptx")])

    def test_duplicate_done(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpptx", b"abc"))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_done("deckpptx")])

    def test_chunk_after_done(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        lines = framing.encode_file("deckpptx", b"0123456789abcdef", chunk_bytes=4)
        feed_lines(asm, lines[:1])
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, lines[1:])

    def test_inconsistent_redeclared_header(self):
        import base64
        import hashlib

        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        good = framing.encode_file("deckpptx", b"0123456789", chunk_bytes=5)
        feed_lines(asm, good[:1])
        forged = "|".join(
            [
                framing.VERSION,
                "deckpptx",
                "9",
                "10",
                hashlib.sha256(b"other").hexdigest(),
                "1",
                base64.b64encode(b"56789").decode(),
            ]
        )
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [forged])

    def test_duplicate_build_status(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_build_status(0)])

    def test_bad_file_id(self):
        asm = framing.Assembler(PARENT)
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, ["PQB1|../etc/passwd|1|1|" + "0" * 64 + "|0|QQ=="])

    def test_invalid_base64(self):
        asm = framing.Assembler(PARENT)
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, ["PQB1|deckpptx|1|1|" + "0" * 64 + "|0|!!!not-base64!!!"])


class LimitEnforcement(unittest.TestCase):
    def make(self, **kwargs):
        limits = framing.Limits(**kwargs)
        return framing.Assembler(PARENT, limits), limits

    def test_file_count_limit(self):
        asm, limits = self.make(max_files=1)
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpptx", b"abc"))
        with self.assertRaises(framing.ChannelLimitError):
            feed_lines(asm, framing.encode_file("deckpng", b"def"))

    def test_file_size_limit_encode(self):
        limits = framing.Limits(max_file_bytes=8)
        with self.assertRaises(framing.ChannelLimitError):
            framing.encode_file("deckpptx", b"123456789", limits=limits)

    def test_file_size_limit_declared(self):
        asm, _ = self.make(max_file_bytes=8)
        feed_lines(asm, [framing.encode_build_status(0)])
        with self.assertRaises(framing.ChannelLimitError):
            feed_lines(asm, ["PQB1|deckpptx|1|9|" + "0" * 64 + "|0|QQ=="])

    def test_chunk_count_limit(self):
        limits = framing.Limits(max_chunks=2)
        with self.assertRaises(framing.ChannelLimitError):
            framing.encode_file("deckpptx", b"0123456789abcdef", chunk_bytes=4, limits=limits)

    def test_chunk_payload_limit(self):
        asm, _ = self.make(max_chunk_bytes=4)
        feed_lines(asm, [framing.encode_build_status(0)])
        import base64
        import hashlib

        data = b"0123456789"
        line = "|".join(
            [
                framing.VERSION,
                "deckpptx",
                "1",
                str(len(data)),
                hashlib.sha256(data).hexdigest(),
                "0",
                base64.b64encode(data).decode(),
            ]
        )
        with self.assertRaises(framing.ChannelLimitError):
            feed_lines(asm, [line])

    def test_total_bytes_limit(self):
        asm, _ = self.make(max_total_bytes=4)
        feed_lines(asm, [framing.encode_build_status(0)])
        with self.assertRaises(framing.ChannelLimitError):
            feed_lines(asm, framing.encode_file("deckpptx", b"0123456789"))

    def test_line_count_limit(self):
        asm, _ = self.make(max_lines=3)
        for _ in range(3):
            asm.feed(PARENT, "noise\n")
        with self.assertRaises(framing.ChannelLimitError):
            asm.feed(PARENT, "noise\n")

    def test_noise_limit(self):
        asm, _ = self.make(max_noise_lines=2)
        asm.feed(PARENT, "noise\n")
        asm.feed(PARENT, "noise\n")
        with self.assertRaises(framing.ChannelLimitError):
            asm.feed(PARENT, "noise\n")

    def test_unterminated_line_length(self):
        asm, _ = self.make(max_line_chars=16)
        with self.assertRaises(framing.ChannelLimitError):
            asm.feed(PARENT, "x" * 17)


class BuildAndDigest(unittest.TestCase):
    def test_nonzero_build_fails_even_with_blocks(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(3)])
        feed_lines(asm, framing.encode_file("deckpptx", b"PK\x03\x04abc"))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.BuildError):
            asm.finish()

    def test_missing_build_status(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, framing.encode_file("deckpptx", b"abc"))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.IncompleteError):
            asm.finish()

    def test_digest_mismatch(self):
        import base64
        import hashlib

        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        data = b"PK\x03\x04corrupt-me"
        wrong = hashlib.sha256(b"different").hexdigest()
        for idx, chunk in enumerate([data]):
            feed_lines(
                asm,
                [
                    "|".join(
                        [
                            framing.VERSION,
                            "deckpptx",
                            "1",
                            str(len(data)),
                            wrong,
                            str(idx),
                            base64.b64encode(chunk).decode(),
                        ]
                    )
                ],
            )
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.DigestError):
            asm.finish()

    def test_size_mismatch_vs_digest_declared(self):
        import base64
        import hashlib

        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        data = b"0123456789"
        feed_lines(
            asm,
            [
                "|".join(
                    [
                        framing.VERSION,
                        "deckpptx",
                        "1",
                        "4",
                        hashlib.sha256(data).hexdigest(),
                        "0",
                        base64.b64encode(data).decode(),
                    ]
                )
            ],
        )
        feed_lines(asm, [framing.encode_done("deckpptx")])
        with self.assertRaises(framing.DigestError):
            asm.finish()

    def test_feed_after_finish(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpptx", b"abc"))
        feed_lines(asm, [framing.encode_done("deckpptx")])
        asm.finish()
        with self.assertRaises(framing.ProtocolError):
            asm.feed(PARENT, "x\n")


class NoiseTolerance(unittest.TestCase):
    def test_interleaved_noise_lines_ignored(self):
        payload = b"PK\x03\x04payload"
        asm = framing.Assembler(PARENT)
        asm.feed(PARENT, "stdout noise\n")
        feed_lines(asm, [framing.encode_build_status(0)])
        lines = framing.encode_file("deckpptx", payload)
        for i, line in enumerate(lines):
            asm.feed(PARENT, "interleaved %d\n" % i)
            asm.feed(PARENT, line + "\n")
        asm.feed(PARENT, "trailing noise\n")
        feed_lines(asm, [framing.encode_done("deckpptx")])
        artifacts = asm.finish()
        self.assertEqual(artifacts["deckpptx"].data, payload)
        self.assertEqual(asm.noise_lines, len(lines) + 2)


class KeyValueFraming(unittest.TestCase):
    def test_kv_recorded_and_not_noise(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_kv("preexisting_deckpptx", "false")])
        feed_lines(asm, [framing.encode_kv("render_digest_ok", "true")])
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpng", b"\x89PNG\r\n\x1a\nabc"))
        feed_lines(asm, [framing.encode_done("deckpng")])
        asm.finish()
        self.assertEqual(
            asm.kv, {"preexisting_deckpptx": "false", "render_digest_ok": "true"}
        )
        self.assertEqual(asm.noise_lines, 0)

    def test_wrong_parent_kv_ignored(self):
        asm = framing.Assembler(PARENT)
        asm.feed(OTHER, framing.encode_kv("evil", "true") + "\n")
        feed_lines(asm, [framing.encode_build_status(0)])
        feed_lines(asm, framing.encode_file("deckpng", b"abc"))
        feed_lines(asm, [framing.encode_done("deckpng")])
        asm.finish()
        self.assertEqual(asm.kv, {})
        self.assertEqual(asm.ignored_parent, 1)

    def test_duplicate_kv_rejected(self):
        asm = framing.Assembler(PARENT)
        feed_lines(asm, [framing.encode_kv("preexisting_deckpptx", "false")])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_kv("preexisting_deckpptx", "true")])

    def test_kv_bad_key_and_value_rejected(self):
        asm = framing.Assembler(PARENT)
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_kv("UPPER", "false")])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, [framing.encode_kv("ok", "has spaces")])

    def test_kv_bad_arity_rejected(self):
        asm = framing.Assembler(PARENT)
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, ["PQKV|onlykey"])
        with self.assertRaises(framing.ProtocolError):
            feed_lines(asm, ["PQKV|key|value|extra"])

    def test_kv_entry_limit(self):
        asm = framing.Assembler(PARENT, framing.Limits(max_kv_entries=2))
        feed_lines(asm, [framing.encode_kv("k1", "v1")])
        feed_lines(asm, [framing.encode_kv("k2", "v2")])
        with self.assertRaises(framing.ChannelLimitError):
            feed_lines(asm, [framing.encode_kv("k3", "v3")])


if __name__ == "__main__":
    unittest.main()
