import hashlib
import struct
import zlib

import pytest

from dashpi.optical.container import MAX_PAYLOAD, pack_container, unpack_container


HEADER = struct.Struct("<4sBHHII32s")


def _container(name: bytes, media_type: bytes, payload: bytes, *, flags: int = 0, body: bytes | None = None) -> bytes:
    body = payload if body is None else body
    return HEADER.pack(
        b"DPC1", flags, len(name), len(media_type), len(payload), len(body), hashlib.sha256(payload).digest()
    ) + name + media_type + body


def test_container_round_trip_and_safe_name():
    decoded = unpack_container(pack_container("../report.html", "text/html", b"incident"))
    assert decoded.name == "report.html"
    assert decoded.media_type == "text/html"
    assert decoded.payload == b"incident"
    assert decoded.sha256 == hashlib.sha256(b"incident").hexdigest()


def test_container_rejects_corruption():
    packed = bytearray(pack_container("a.bin", "application/octet-stream", b"abc"))
    packed[-1] ^= 1
    with pytest.raises(ValueError, match="sha256"):
        unpack_container(bytes(packed))


def test_container_rejects_oversize_payload():
    with pytest.raises(ValueError, match="16 MiB"):
        pack_container("a.bin", "application/octet-stream", b"x" * (MAX_PAYLOAD + 1))


@pytest.mark.parametrize("name", [b"../report.html", b"folder/report.html", b"..\\report.html", b"", b".", b"..", b"\x00report.html"])
def test_container_rejects_unsafe_received_name(name):
    with pytest.raises(ValueError, match="container|metadata"):
        unpack_container(_container(name, b"text/plain", b"report"))


@pytest.mark.parametrize("name, media_type", [(b"\xff", b"text/plain"), (b"report.txt", b"\xff")])
def test_container_rejects_non_utf8_metadata(name, media_type):
    with pytest.raises(ValueError, match="metadata"):
        unpack_container(_container(name, media_type, b"report"))


def test_container_rejects_truncated_or_trailing_container_bytes():
    packed = pack_container("a.txt", "text/plain", b"abc")
    with pytest.raises(ValueError, match="length|truncated"):
        unpack_container(packed[:-1])
    with pytest.raises(ValueError, match="length"):
        unpack_container(packed + b"extra")


def test_container_rejects_oversized_declared_fields():
    oversized_payload = HEADER.pack(
        b"DPC1", 0, 1, 1, MAX_PAYLOAD + 1, 0, hashlib.sha256(b"").digest()
    ) + b"a" + b"b"
    with pytest.raises(ValueError, match="length"):
        unpack_container(oversized_payload)

    oversized_metadata = HEADER.pack(
        b"DPC1", 0, 256, 1, 0, 0, hashlib.sha256(b"").digest()
    )
    with pytest.raises(ValueError, match="container"):
        unpack_container(oversized_metadata)


def test_container_rejects_incomplete_compressed_stream():
    payload = b"a" * 100
    compressed = zlib.compress(payload)[:-1]
    with pytest.raises(ValueError, match="compressed"):
        unpack_container(_container(b"a.txt", b"text/plain", payload, flags=1, body=compressed))


def test_container_rejects_trailing_compressed_data():
    payload = b"a" * 100
    compressed = zlib.compress(payload) + b"trailing"
    with pytest.raises(ValueError, match="compressed"):
        unpack_container(_container(b"a.txt", b"text/plain", payload, flags=1, body=compressed))


def test_container_rejects_compressed_payload_that_expands_past_limit():
    payload = b"a" * (MAX_PAYLOAD + 1)
    compressed = zlib.compress(payload)
    packed = HEADER.pack(
        b"DPC1", 1, 1, 1, MAX_PAYLOAD, len(compressed), hashlib.sha256(payload).digest()
    ) + b"a" + b"b" + compressed
    with pytest.raises(ValueError, match="payload"):
        unpack_container(packed)
