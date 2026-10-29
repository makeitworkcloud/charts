import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib import verify_artifacts  # noqa: E402


def make_png(width=640, height=480):
    sig = verify_artifacts.PNG_SIGNATURE
    ihdr_payload = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_payload)) + b"IHDR" + ihdr_payload
    ihdr += struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_payload) & 0xFFFFFFFF)
    return sig + ihdr + b"IDAT-body-not-parsed" + b"IEND-placeholder"


class PptxSignature(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(verify_artifacts.pptx_signature_ok(b"PK\x03\x04rest-of-zip"))

    def test_invalid(self):
        self.assertFalse(verify_artifacts.pptx_signature_ok(b"MZ\x90\x00"))
        self.assertFalse(verify_artifacts.pptx_signature_ok(b""))
        self.assertFalse(verify_artifacts.pptx_signature_ok(b"PK\x05\x06empty"))


class PngChecks(unittest.TestCase):
    def test_valid_ihdr(self):
        info = verify_artifacts.parse_ihdr(make_png(1920, 1080))
        self.assertEqual(info["width"], 1920)
        self.assertEqual(info["height"], 1080)
        self.assertEqual(info["bit_depth"], 8)
        self.assertEqual(info["color_type"], 2)

    def test_signature_ok_helper(self):
        self.assertTrue(verify_artifacts.png_signature_ok(make_png()))
        self.assertFalse(verify_artifacts.png_signature_ok(b"\x89PNX"))

    def test_bad_signature(self):
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(b"\x89PNX\r\n\x1a\n" + make_png()[8:])

    def test_truncated(self):
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(make_png()[:20])

    def test_crc_mismatch(self):
        png = bytearray(make_png())
        png[29] ^= 0xFF
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(bytes(png))

    def test_zero_dimensions(self):
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(make_png(0, 480))
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(make_png(640, 0))

    def test_bad_bit_depth_and_color_type(self):
        bad = bytearray(make_png())
        bad[24] = 3
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(bytes(bad))
        bad2 = bytearray(make_png())
        bad2[25] = 5
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(bytes(bad2))

    def test_first_chunk_not_ihdr(self):
        png = bytearray(make_png())
        png[12:16] = b"IDAT"
        with self.assertRaises(verify_artifacts.ArtifactVerifyError):
            verify_artifacts.parse_ihdr(bytes(png))


if __name__ == "__main__":
    unittest.main()
