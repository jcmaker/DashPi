from collections.abc import Iterator
from pathlib import Path

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
    path: Path, header: str | None, media_type: str, digest: str
) -> StreamingResponse:
    size = path.stat().st_size
    try:
        selected = parse_range(header, size)
    except (TypeError, ValueError):
        raise HTTPException(416, headers={"Content-Range": f"bytes */{size}"}) from None
    start, end = selected or (0, size - 1)

    def body() -> Iterator[bytes]:
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

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
