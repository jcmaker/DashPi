from pathlib import Path
import hashlib
import json
import random

from dashpi.optical.session import OpticalSession


payload = random.Random(9).randbytes(1024 * 1024)
session = OpticalSession.from_bytes(
    "source.bin", payload, "application/octet-stream", 1024, 11
)
frames = [
    session.frame(sequence)
    for sequence in range(session.encoder.block_count * 2)
    if sequence % 20 not in {1, 7, 13}
]
frames += frames[:20]
random.Random(5).shuffle(frames)
manifest = {
    "payload_sha256": hashlib.sha256(payload).hexdigest(),
    "frames_hex": [frame.hex() for frame in frames],
}
encoded = json.dumps(manifest, separators=(",", ":"))
if len(encoded.encode()) > 8 * 1024 * 1024:
    raise RuntimeError("optical fixture exceeds 8 MiB")
Path(__file__).resolve().parents[1].joinpath(
    "tests/fixtures/optical-e2e.json"
).write_text(encoded, encoding="utf-8")
