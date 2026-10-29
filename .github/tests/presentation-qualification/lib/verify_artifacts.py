"""Stdlib artifact signature checks: PPTX zip magic and PNG signature + IHDR."""

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PPTX_MAGIC = b"PK\x03\x04"


class ArtifactVerifyError(Exception):
    pass


def pptx_signature_ok(data):
    return bytes(data[:4]) == PPTX_MAGIC


def png_signature_ok(data):
    return bytes(data[:8]) == PNG_SIGNATURE


def parse_ihdr(data):
    data = bytes(data)
    if not png_signature_ok(data):
        raise ArtifactVerifyError("png signature mismatch")
    if len(data) < 8 + 4 + 4 + 13 + 4:
        raise ArtifactVerifyError("png truncated before IHDR")
    length = struct.unpack(">I", data[8:12])[0]
    chunk_type = data[12:16]
    if length != 13 or chunk_type != b"IHDR":
        raise ArtifactVerifyError("first chunk is not IHDR")
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", data[16:29]
    )
    stored_crc = struct.unpack(">I", data[29:33])[0]
    if zlib.crc32(data[12:29]) & 0xFFFFFFFF != stored_crc:
        raise ArtifactVerifyError("IHDR crc mismatch")
    if not 0 < width <= 100000:
        raise ArtifactVerifyError("IHDR width out of range")
    if not 0 < height <= 100000:
        raise ArtifactVerifyError("IHDR height out of range")
    if bit_depth not in (1, 2, 4, 8, 16):
        raise ArtifactVerifyError("IHDR bit depth invalid")
    if color_type not in (0, 2, 3, 4, 6):
        raise ArtifactVerifyError("IHDR color type invalid")
    if compression != 0 or filter_method != 0 or interlace not in (0, 1):
        raise ArtifactVerifyError("IHDR coding fields invalid")
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
    }
