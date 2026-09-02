"""Bounded file container for optical transfer."""

from dataclasses import dataclass
import hashlib
from pathlib import PurePath
import struct
import zlib


MAX_PAYLOAD = 16 * 1024 * 1024
MAX_TEXT_FIELD = 255
HEADER = struct.Struct("<4sBHHII32s")


@dataclass(frozen=True)
class OpticalFile:
    name: str
    media_type: str
    payload: bytes
    sha256: str


def _metadata(value: str) -> bytes:
    try:
        encoded = value.encode("utf-8")
    except (AttributeError, UnicodeEncodeError) as error:
        raise ValueError("invalid container metadata") from error
    if not encoded or len(encoded) > MAX_TEXT_FIELD:
        raise ValueError("invalid container metadata")
    return encoded


def _safe_name(name: str) -> str:
    try:
        safe_name = PurePath(name.replace("\\", "/")).name
    except AttributeError as error:
        raise ValueError("invalid container metadata") from error
    if not safe_name or safe_name in {".", ".."} or "\0" in safe_name:
        raise ValueError("invalid container metadata")
    return safe_name


def pack_container(name: str, media_type: str, payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload exceeds 16 MiB")
    safe_name = _metadata(_safe_name(name))
    media = _metadata(media_type)
    compressed = zlib.compress(payload)
    body, flags = (compressed, 1) if len(compressed) < len(payload) else (payload, 0)
    digest = hashlib.sha256(payload).digest()
    return HEADER.pack(b"DPC1", flags, len(safe_name), len(media), len(payload), len(body), digest) + safe_name + media + body


def _decode_metadata(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("invalid container metadata") from error


def unpack_container(data: bytes) -> OpticalFile:
    if len(data) < HEADER.size:
        raise ValueError("truncated container")
    magic, flags, name_len, media_len, original_len, body_len, digest = HEADER.unpack_from(data)
    if magic != b"DPC1" or flags & ~1 or not name_len or not media_len:
        raise ValueError("unsupported container")
    if name_len > MAX_TEXT_FIELD or media_len > MAX_TEXT_FIELD:
        raise ValueError("unsupported container")
    if original_len > MAX_PAYLOAD or body_len > original_len or (flags and body_len >= original_len):
        raise ValueError("invalid container length")

    offset = HEADER.size
    end = offset + name_len + media_len + body_len
    if end != len(data):
        raise ValueError("invalid container length")
    name = _decode_metadata(data[offset : offset + name_len])
    offset += name_len
    media_type = _decode_metadata(data[offset : offset + media_len])
    offset += media_len
    if name != _safe_name(name) or not _metadata(media_type):
        raise ValueError("invalid container metadata")

    body = data[offset:end]
    if flags:
        decoder = zlib.decompressobj()
        try:
            payload = decoder.decompress(body, original_len + 1)
            if len(payload) > original_len or decoder.unconsumed_tail:
                raise ValueError("compressed payload exceeds declared length")
            tail = decoder.flush(original_len + 1 - len(payload))
        except zlib.error as error:
            raise ValueError("invalid compressed payload") from error
        if len(tail) > original_len - len(payload) or not decoder.eof or decoder.unused_data:
            raise ValueError("invalid compressed payload")
        payload += tail
    else:
        payload = body
    if len(payload) != original_len:
        raise ValueError("invalid container length")
    if hashlib.sha256(payload).digest() != digest:
        raise ValueError("sha256 mismatch")
    return OpticalFile(name, media_type, payload, digest.hex())
