from dataclasses import dataclass
import struct
import zlib


MAGIC = b"DPQ1"
VERSION = 1
HEADER = struct.Struct("<4sBBIIHHIB")
CRC = struct.Struct("<I")


@dataclass(frozen=True)
class OpticalFrame:
    session_id: int
    sequence: int
    block_count: int
    block_size: int
    total_length: int
    indices: tuple[int, ...]
    symbol: bytes


def _validate(frame: OpticalFrame) -> None:
    integer_fields = (
        frame.session_id,
        frame.sequence,
        frame.block_count,
        frame.block_size,
        frame.total_length,
    )
    if any(type(value) is not int for value in integer_fields) or any(
        type(index) is not int for index in frame.indices
    ):
        raise ValueError("integer fields and indices must be integers")
    if not 0 <= frame.session_id < 2**32 or not 0 <= frame.sequence < 2**32:
        raise ValueError("invalid frame identifier")
    if not 1 <= frame.block_count < 2**16 or not 1 <= frame.block_size < 2**16:
        raise ValueError("invalid block geometry")
    if not (frame.block_count - 1) * frame.block_size < frame.total_length <= (
        frame.block_count * frame.block_size
    ) or frame.total_length >= 2**32:
        raise ValueError("invalid total length")
    if (
        not frame.indices
        or len(frame.indices) > min(255, frame.block_count)
        or len(set(frame.indices)) != len(frame.indices)
        or any(index < 0 or index >= frame.block_count for index in frame.indices)
    ):
        raise ValueError("invalid block index")
    if len(frame.symbol) != frame.block_size:
        raise ValueError("invalid symbol")


def pack_frame(frame: OpticalFrame) -> bytes:
    _validate(frame)
    prefix = HEADER.pack(
        MAGIC,
        VERSION,
        0,
        frame.session_id,
        frame.sequence,
        frame.block_count,
        frame.block_size,
        frame.total_length,
        len(frame.indices),
    )
    body = struct.pack(f"<{len(frame.indices)}H", *frame.indices) + frame.symbol
    wire = prefix + body
    return wire + CRC.pack(zlib.crc32(wire))


def parse_frame(data: bytes) -> OpticalFrame:
    if len(data) < HEADER.size + CRC.size:
        raise ValueError("truncated frame")
    expected_crc = CRC.unpack_from(data, len(data) - CRC.size)[0]
    if zlib.crc32(data[:-CRC.size]) != expected_crc:
        raise ValueError("crc mismatch")
    magic, version, flags, session, sequence, count, size, total, degree = (
        HEADER.unpack_from(data)
    )
    if magic != MAGIC:
        raise ValueError("foreign frame")
    if version != VERSION or flags:
        raise ValueError("unsupported protocol")
    expected_length = HEADER.size + degree * 2 + size + CRC.size
    if expected_length != len(data):
        raise ValueError("malformed frame")
    indices = struct.unpack_from(f"<{degree}H", data, HEADER.size) if degree else ()
    symbol_offset = HEADER.size + degree * 2
    frame = OpticalFrame(
        session,
        sequence,
        count,
        size,
        total,
        indices,
        data[symbol_offset:-CRC.size],
    )
    _validate(frame)
    return frame


def stream_identity(frame: OpticalFrame) -> tuple[int, int, int, int]:
    return frame.session_id, frame.block_count, frame.block_size, frame.total_length
