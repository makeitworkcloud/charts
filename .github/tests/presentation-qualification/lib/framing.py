"""Bounded file transport framing for the qualification kernel channel.

The worker prints framed base64 blocks on stdout; the Jupyter channel turns
them into stream messages that carry the client's execute_request msg_id as
their parent. The assembler accepts only lines matching that parent id and
enforces hard size/count/chunk limits, so a runaway kernel cannot exhaust the
client. Digests are verified over the reassembled bytes.
"""

import base64
import hashlib
import re

VERSION = "PQB1"
BUILD_PREFIX = "PQBUILD"
DONE_PREFIX = "PQBDONE"
KV_PREFIX = "PQKV"
FILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
KV_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
KV_VALUE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class FramingError(Exception):
    pass


class ProtocolError(FramingError):
    pass


class ChannelLimitError(FramingError):
    pass


class BuildError(FramingError):
    pass


class DigestError(FramingError):
    pass


class IncompleteError(FramingError):
    pass


class Limits:
    def __init__(
        self,
        max_files=2,
        max_chunks=512,
        max_chunk_bytes=32768,
        max_file_bytes=8 * 1024 * 1024,
        max_total_bytes=12 * 1024 * 1024,
        max_lines=8192,
        max_noise_lines=4096,
        max_line_chars=100000,
        max_kv_entries=16,
    ):
        self.max_files = max_files
        self.max_chunks = max_chunks
        self.max_chunk_bytes = max_chunk_bytes
        self.max_file_bytes = max_file_bytes
        self.max_total_bytes = max_total_bytes
        self.max_lines = max_lines
        self.max_noise_lines = max_noise_lines
        self.max_line_chars = max_line_chars
        self.max_kv_entries = max_kv_entries


DEFAULT_LIMITS = Limits()


def _check_file_id(file_id):
    if not FILE_ID_RE.match(file_id or ""):
        raise ProtocolError("invalid file id")


def encode_file(file_id, data, chunk_bytes=None, limits=DEFAULT_LIMITS):
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("data must be bytes")
    data = bytes(data)
    _check_file_id(file_id)
    if chunk_bytes is None:
        chunk_bytes = limits.max_chunk_bytes
    if chunk_bytes <= 0 or chunk_bytes > limits.max_chunk_bytes:
        raise ChannelLimitError("chunk size out of bounds")
    if len(data) > limits.max_file_bytes:
        raise ChannelLimitError("file exceeds size limit")
    digest = hashlib.sha256(data).hexdigest()
    chunks = [data[i : i + chunk_bytes] for i in range(0, len(data), chunk_bytes)] or [b""]
    if len(chunks) > limits.max_chunks:
        raise ChannelLimitError("chunk count exceeds limit")
    lines = []
    for idx, chunk in enumerate(chunks):
        lines.append(
            "|".join(
                [
                    VERSION,
                    file_id,
                    str(len(chunks)),
                    str(len(data)),
                    digest,
                    str(idx),
                    base64.b64encode(chunk).decode("ascii"),
                ]
            )
        )
    return lines


def encode_build_status(code):
    return "%s|%d" % (BUILD_PREFIX, int(code))


def encode_kv(key, value):
    if not KV_KEY_RE.match(key or ""):
        raise ProtocolError("invalid kv key")
    if not KV_VALUE_RE.match(value or ""):
        raise ProtocolError("invalid kv value")
    return "%s|%s|%s" % (KV_PREFIX, key, value)


def encode_done(file_id):
    _check_file_id(file_id)
    return "%s|%s" % (DONE_PREFIX, file_id)


class Artifact:
    def __init__(self, file_id, total_chunks, total_bytes, expected_digest):
        self.file_id = file_id
        self.total_chunks = total_chunks
        self.total_bytes = total_bytes
        self.expected_digest = expected_digest
        self.chunks = {}
        self.done = False

    @property
    def data(self):
        return b"".join(self.chunks[i] for i in range(self.total_chunks))

    @property
    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()


class Assembler:
    def __init__(self, parent_msg_id, limits=None):
        self.parent_msg_id = parent_msg_id
        self.limits = limits or DEFAULT_LIMITS
        self._buffer = ""
        self._started = {}
        self._order = []
        self._bytes_seen = 0
        self.kv = {}
        self.build_exit_code = None
        self.total_lines = 0
        self.noise_lines = 0
        self.ignored_parent = 0
        self._finished = False

    def feed(self, parent_msg_id, text):
        if self._finished:
            raise ProtocolError("feed after finish")
        if parent_msg_id != self.parent_msg_id:
            self.ignored_parent += 1
            return
        if isinstance(text, (bytes, bytearray)):
            text = bytes(text).decode("utf-8")
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._handle_line(line)
        if len(self._buffer) > self.limits.max_line_chars:
            raise ChannelLimitError("unterminated line exceeds length limit")

    def _handle_line(self, line):
        self.total_lines += 1
        if self.total_lines > self.limits.max_lines:
            raise ChannelLimitError("line count limit")
        if len(line) > self.limits.max_line_chars:
            raise ChannelLimitError("line length limit")
        if not line.startswith((VERSION + "|", BUILD_PREFIX + "|", DONE_PREFIX + "|", KV_PREFIX + "|")):
            self.noise_lines += 1
            if self.noise_lines > self.limits.max_noise_lines:
                raise ChannelLimitError("noise line limit")
            return
        parts = line.split("|")
        if line.startswith(VERSION + "|"):
            self._handle_block(parts)
        elif line.startswith(BUILD_PREFIX + "|"):
            self._handle_build(parts)
        elif line.startswith(KV_PREFIX + "|"):
            self._handle_kv(parts)
        else:
            self._handle_done(parts)

    def _handle_block(self, parts):
        if len(parts) != 7:
            raise ProtocolError("block arity")
        _, file_id, total_chunks, total_bytes, digest, idx, b64 = parts
        _check_file_id(file_id)
        if not (total_chunks.isdigit() and total_bytes.isdigit() and idx.isdigit()):
            raise ProtocolError("non-numeric block fields")
        if not SHA256_HEX_RE.match(digest):
            raise ProtocolError("digest format")
        if file_id not in self._started:
            if len(self._started) >= self.limits.max_files:
                raise ChannelLimitError("file count limit")
            total_chunks_i = int(total_chunks)
            total_bytes_i = int(total_bytes)
            if total_chunks_i < 1 or total_chunks_i > self.limits.max_chunks:
                raise ChannelLimitError("declared chunk count out of bounds")
            if total_bytes_i > self.limits.max_file_bytes:
                raise ChannelLimitError("declared file size out of bounds")
            self._started[file_id] = Artifact(file_id, total_chunks_i, total_bytes_i, digest)
            self._order.append(file_id)
        art = self._started[file_id]
        if str(art.total_chunks) != total_chunks or str(art.total_bytes) != total_bytes or art.expected_digest != digest:
            raise ProtocolError("inconsistent redeclared header")
        if art.done:
            raise ProtocolError("chunk after done")
        idx_i = int(idx)
        if not 0 <= idx_i < art.total_chunks:
            raise ProtocolError("chunk index out of bounds")
        if idx_i in art.chunks:
            raise ProtocolError("duplicate chunk")
        try:
            payload = base64.b64decode(b64, validate=True)
        except Exception as exc:
            raise ProtocolError("invalid base64 payload") from exc
        if len(payload) > self.limits.max_chunk_bytes:
            raise ChannelLimitError("chunk payload exceeds limit")
        art.chunks[idx_i] = payload
        self._bytes_seen += len(payload)
        if self._bytes_seen > self.limits.max_total_bytes:
            raise ChannelLimitError("total transported bytes limit")

    def _handle_build(self, parts):
        if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
            raise ProtocolError("build status arity")
        if self.build_exit_code is not None:
            raise ProtocolError("duplicate build status")
        self.build_exit_code = int(parts[1])

    def _handle_kv(self, parts):
        if len(parts) != 3:
            raise ProtocolError("kv arity")
        key, value = parts[1], parts[2]
        if not KV_KEY_RE.match(key):
            raise ProtocolError("kv key format")
        if not KV_VALUE_RE.match(value):
            raise ProtocolError("kv value format")
        if key in self.kv:
            raise ProtocolError("duplicate kv key")
        if len(self.kv) >= self.limits.max_kv_entries:
            raise ChannelLimitError("kv entry limit")
        self.kv[key] = value

    def _handle_done(self, parts):
        if len(parts) != 2:
            raise ProtocolError("done arity")
        file_id = parts[1]
        _check_file_id(file_id)
        if file_id not in self._started:
            raise ProtocolError("done before header")
        if self._started[file_id].done:
            raise ProtocolError("duplicate done")
        self._started[file_id].done = True

    def finish(self):
        self._finished = True
        if self.build_exit_code is None:
            raise IncompleteError("no build status received")
        if self.build_exit_code != 0:
            raise BuildError("worker build exited with code %d" % self.build_exit_code)
        if not self._started:
            raise IncompleteError("no files received")
        artifacts = {}
        for file_id in self._order:
            art = self._started[file_id]
            if not art.done:
                raise IncompleteError("%s missing done marker" % file_id)
            if len(art.chunks) != art.total_chunks:
                raise IncompleteError("%s missing chunks" % file_id)
            if len(art.data) != art.total_bytes:
                raise DigestError("%s reassembled size mismatch" % file_id)
            if art.sha256 != art.expected_digest:
                raise DigestError("%s digest mismatch" % file_id)
            artifacts[file_id] = art
        return artifacts
