from collections.abc import Iterator
import hashlib
import hmac
import os
import stat
from typing import BinaryIO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from dashpi.storage import open_regular_file_at


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
    source: BinaryIO, size: int, header: str | None, media_type: str, digest: str
) -> StreamingResponse:
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
    try:
        return StreamingResponse(
            body(), status_code=206 if selected else 200, media_type=media_type, headers=headers
        )
    except BaseException:
        source.close()
        raise


def _open_verified_file(
    directory_descriptor: int, basename: str, byte_length: int, digest: str
) -> tuple[BinaryIO, int]:
    try:
        source = open_regular_file_at(directory_descriptor, basename)
    except OSError:
        raise HTTPException(409) from None
    try:
        details = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(details.st_mode)
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
