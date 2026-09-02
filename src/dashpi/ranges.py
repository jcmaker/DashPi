from collections.abc import Iterator
import hashlib
import hmac
import os
from pathlib import Path
import stat
from typing import BinaryIO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None:
        return None
    if size <= 0 or not header.startswith("bytes=") or "," in header:
        raise ValueError("unsupported range")
    start_text, end_text = header[6:].split("-", 1)
    if not start_text:
        length = int(end_text)
        if length <= 0:
            raise ValueError("invalid suffix")
        return max(0, size - length), size - 1
    start = int(start_text)
    end = int(end_text) if end_text else size - 1
    if start < 0 or start >= size or end < start:
        raise ValueError("range outside file")
    return start, min(end, size - 1)


def range_response(
    path: Path, header: str | None, media_type: str, digest: str, byte_length: int
) -> StreamingResponse:
    source, size = _open_verified_file(path, byte_length, digest)
    try:
        selected = parse_range(header, size)
    except (TypeError, ValueError):
        source.close()
        raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"}) from None
    start, end = selected or (0, size - 1)

    def body() -> Iterator[bytes]:
        try:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            source.close()

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "ETag": f'"sha256:{digest}"',
    }
    if selected:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(
        body(), status_code=206 if selected else 200, media_type=media_type, headers=headers
    )


def _open_verified_file(path: Path, byte_length: int, digest: str) -> tuple[BinaryIO, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        expected = os.lstat(path)
        if not stat.S_ISREG(expected.st_mode):
            raise OSError("non-regular clip")
        descriptor = os.open(path, flags)
        source = os.fdopen(descriptor, "rb")
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        raise HTTPException(409) from None
    try:
        details = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
            or (details.st_dev, details.st_ino) != (expected.st_dev, expected.st_ino)
            or details.st_size <= 0
            or details.st_size != byte_length
            or not hmac.compare_digest(_sha256_descriptor(source), digest)
        ):
            raise ValueError("invalid clip artifact")
        return source, details.st_size
    except (OSError, TypeError, ValueError):
        source.close()
        raise HTTPException(409) from None


def _sha256_descriptor(source: BinaryIO) -> str:
    digest = hashlib.sha256()
    source.seek(0)
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()
