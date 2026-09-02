import json
from pathlib import Path

import pytest

from dashpi.optical.protocol import OpticalFrame, pack_frame, parse_frame, stream_identity


def frame(**changes):
    values = {
        "session_id": 0x01020304,
        "sequence": 5,
        "block_count": 3,
        "block_size": 4,
        "total_length": 10,
        "indices": (0, 2),
        "symbol": b"abcd",
    }
    values.update(changes)
    return OpticalFrame(**values)


def test_frame_header_is_little_endian_and_round_trips():
    value = frame()
    wire = pack_frame(value)

    assert wire[:4] == b"DPQ1"
    assert wire[4] == 1
    assert wire[6:10] == bytes.fromhex("04030201")
    assert parse_frame(wire) == value
    assert stream_identity(value) == (0x01020304, 3, 4, 10)


def test_python_wire_matches_committed_vector():
    vector = json.loads(Path("tests/fixtures/optical-v1.json").read_text())
    assert pack_frame(frame()).hex() == vector["wire_hex"]


def test_crc_rejects_corruption():
    wire = bytearray(pack_frame(frame()))
    wire[-1] ^= 1
    with pytest.raises(ValueError, match="crc"):
        parse_frame(bytes(wire))


@pytest.mark.parametrize(
    "changes",
    [
        {"session_id": -1},
        {"session_id": 2**32},
        {"sequence": -1},
        {"sequence": 2**32},
        {"block_count": 0},
        {"block_count": 2**16},
        {"block_size": 0},
        {"block_size": 2**16},
        {"total_length": 0},
        {"total_length": 2**32},
        {"total_length": 13},
        {"indices": ()},
        {"indices": (0, 0)},
        {"indices": (3,)},
        {"indices": tuple(range(256)), "block_count": 300},
        {"symbol": b"abc"},
    ],
)
def test_pack_rejects_out_of_domain_frames(changes):
    with pytest.raises(ValueError):
        pack_frame(frame(**changes))


@pytest.mark.parametrize(
    "offset,value",
    [
        (0, b"NOPE"),
        (4, bytes([2])),
        (5, bytes([1])),
        (22, bytes([0])),
    ],
)
def test_parser_rejects_foreign_or_unsupported_headers(offset, value):
    wire = bytearray(pack_frame(frame()))
    wire[offset : offset + len(value)] = value
    import zlib

    wire[-4:] = zlib.crc32(wire[:-4]).to_bytes(4, "little")
    with pytest.raises(ValueError):
        parse_frame(bytes(wire))


def test_parser_rejects_truncation_and_trailing_bytes():
    wire = pack_frame(frame())
    for malformed in (wire[:-1], wire + b"x"):
        with pytest.raises(ValueError):
            parse_frame(malformed)
