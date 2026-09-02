# Optical Transfer Proof-of-Concept Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transfer a report or file up to 16 MiB from the DashPi display to an offline phone browser using independently implemented fountain-coded animated QR frames and final SHA-256 verification.

**Architecture:** Python packages a file, emits versioned LT-style XOR symbols, and exposes binary frames through the existing local API. A small TypeScript bundle renders those bytes as QR codes on DashPi; the offline receiver PWA decodes raw QR bytes, peels equations into source blocks, validates the container, and offers the verified result.

**Tech Stack:** Python 3.11+ standard library, FastAPI, pytest; Node.js 22+, TypeScript, esbuild, qrcode, @zxing/browser, Node test runner via tsx

## Global Constraints

- Complete the core incident and local web transfer plans first.
- Do not copy Decimen source, wire bytes, golden vectors, WASM, or build artifacts; do not claim Decimen compatibility.
- Protocol name is `DashPi Optical v1`; magic is ASCII `DPQ1`; all multi-byte integers are unsigned little-endian.
- Payload limit is exactly 16 MiB before container overhead.
- The channel is not encrypted; sender UI must show a line-of-sight confidentiality warning before start.
- Receiver exposes bytes only after SHA-256 verification.
- QR payload bytes/frame, display scale, and frames/second remain calibration controls.
- Tests must recover a 1 MiB payload with deterministic 15% dropped frames plus duplicate and reordered frames.
- No hotspot control, camera hardware, native app, cloud request, analytics, or background upload belongs in this plan.

---

## File Map

- `src/dashpi/optical/container.py` — bounded file container and SHA-256 validation
- `src/dashpi/optical/fountain.py` — independent systematic LT-style encoder and peeling decoder
- `src/dashpi/optical/protocol.py` — DashPi Optical v1 frame packing, parsing, CRC, and stream identity
- `src/dashpi/optical/session.py` — deterministic sequence-to-symbol production for API/UI
- `src/dashpi/api.py` — optical metadata and binary-frame endpoints
- `tests/fixtures/optical-v1.json` — committed Python/TypeScript interoperability vectors
- `web/package.json`, `web/tsconfig.json`, `web/build.mjs` — smallest offline web build
- `web/src/optical/protocol.ts` — binary parser matching Python vectors
- `web/src/optical/fountain.ts` — browser peeling decoder
- `web/src/optical/container.ts` — bounded decompression and final SHA-256 verification
- `web/src/sender.ts` — DashPi display QR animation and calibration controls
- `web/src/receiver.ts` — camera scanning, progress, verification, and save action
- `web/public/manifest.webmanifest`, `web/public/sw.js` — installable offline receiver shell
- Python and TypeScript tests mirror each protocol boundary

### Task 1: Bounded, Integrity-Checked Container

**Files:**
- Create: `src/dashpi/optical/__init__.py`
- Create: `src/dashpi/optical/container.py`
- Test: `tests/test_optical_container.py`

**Interfaces:**
- Produces: `pack_container(name, media_type, payload) -> bytes`, `unpack_container(data) -> OpticalFile`
- `OpticalFile`: frozen dataclass with `name: str`, `media_type: str`, `payload: bytes`, `sha256: str`

- [ ] **Step 1: Write round-trip, traversal-name, corruption, and size-limit tests**

```python
import pytest
from dashpi.optical.container import MAX_PAYLOAD, pack_container, unpack_container

def test_container_round_trip_and_safe_name():
    decoded = unpack_container(pack_container("../report.html", "text/html", b"incident"))
    assert decoded.name == "report.html"
    assert decoded.media_type == "text/html"
    assert decoded.payload == b"incident"

def test_container_rejects_corruption():
    packed = bytearray(pack_container("a.bin", "application/octet-stream", b"abc")); packed[-1] ^= 1
    with pytest.raises(ValueError, match="sha256"): unpack_container(bytes(packed))

def test_container_rejects_oversize_payload():
    with pytest.raises(ValueError, match="16 MiB"): pack_container("a.bin", "application/octet-stream", b"x" * (MAX_PAYLOAD + 1))
```

- [ ] **Step 2: Run and verify missing implementation**

Run: `python3 -m pytest tests/test_optical_container.py -q`

Expected: FAIL because `dashpi.optical.container` does not exist.

- [ ] **Step 3: Implement the explicit binary container**

```python
# src/dashpi/optical/container.py
from dataclasses import dataclass
import hashlib, struct, zlib
from pathlib import PurePath

MAX_PAYLOAD = 16 * 1024 * 1024
MAX_TEXT_FIELD = 255
HEADER = struct.Struct("<4sBHHII32s")

@dataclass(frozen=True)
class OpticalFile:
    name: str
    media_type: str
    payload: bytes
    sha256: str

def pack_container(name: str, media_type: str, payload: bytes) -> bytes:
    if len(payload) > MAX_PAYLOAD: raise ValueError("payload exceeds 16 MiB")
    safe_name = PurePath(name.replace("\\", "/")).name.encode("utf-8")
    media = media_type.encode("utf-8")
    if not safe_name or not media or len(safe_name) > MAX_TEXT_FIELD or len(media) > MAX_TEXT_FIELD: raise ValueError("invalid container metadata")
    compressed = zlib.compress(payload)
    body, flags = (compressed, 1) if len(compressed) < len(payload) else (payload, 0)
    digest = hashlib.sha256(payload).digest()
    return HEADER.pack(b"DPC1", flags, len(safe_name), len(media), len(payload), len(body), digest) + safe_name + media + body

def unpack_container(data: bytes) -> OpticalFile:
    if len(data) < HEADER.size: raise ValueError("truncated container")
    magic, flags, name_len, media_len, original_len, body_len, digest = HEADER.unpack_from(data)
    if magic != b"DPC1" or flags & ~1 or not name_len or not media_len or name_len > MAX_TEXT_FIELD or media_len > MAX_TEXT_FIELD: raise ValueError("unsupported container")
    offset = HEADER.size; end = offset + name_len + media_len + body_len
    if end != len(data) or original_len > MAX_PAYLOAD: raise ValueError("invalid container length")
    name = data[offset:offset + name_len].decode(); offset += name_len
    media = data[offset:offset + media_len].decode(); offset += media_len
    if flags & 1:
        decoder = zlib.decompressobj(); payload = decoder.decompress(data[offset:end], MAX_PAYLOAD + 1)
        if decoder.unconsumed_tail or len(payload) > MAX_PAYLOAD: raise ValueError("compressed payload exceeds 16 MiB")
        payload += decoder.flush()
    else: payload = data[offset:end]
    if len(payload) != original_len or hashlib.sha256(payload).digest() != digest: raise ValueError("sha256 mismatch")
    return OpticalFile(PurePath(name).name, media, payload, digest.hex())
```

- [ ] **Step 4: Run container and full Python tests**

Run: `python3 -m pytest tests/test_optical_container.py -q && python3 -m pytest -q`

Expected: all cases pass.

- [ ] **Step 5: Commit the container**

```bash
git add src/dashpi/optical tests/test_optical_container.py
git commit -m "feat: define optical file container"
```

### Task 2: Versioned Frame Protocol and Golden Vector

**Files:**
- Create: `src/dashpi/optical/protocol.py`
- Create: `tests/fixtures/optical-v1.json`
- Test: `tests/test_optical_protocol.py`

**Interfaces:**
- Produces: `OpticalFrame`, `pack_frame(frame) -> bytes`, `parse_frame(data) -> OpticalFrame`, `stream_identity(frame) -> tuple`
- Frame fields: `session_id`, `sequence`, `block_count`, `block_size`, `total_length`, `indices`, `symbol`

- [ ] **Step 1: Write a byte-exact header and rejection test**

```python
import pytest
from dashpi.optical.protocol import OpticalFrame, pack_frame, parse_frame

def test_frame_header_is_little_endian_and_round_trips():
    frame = OpticalFrame(session_id=0x01020304, sequence=5, block_count=3, block_size=4, total_length=10, indices=(0, 2), symbol=b"abcd")
    wire = pack_frame(frame)
    assert wire[:4] == b"DPQ1"
    assert wire[4] == 1
    assert wire[6:10] == bytes.fromhex("04030201")
    assert parse_frame(wire) == frame

def test_crc_rejects_corruption():
    wire = bytearray(pack_frame(OpticalFrame(1, 0, 1, 3, 3, (0,), b"abc"))); wire[-1] ^= 1
    with pytest.raises(ValueError, match="crc"): parse_frame(bytes(wire))
```

- [ ] **Step 2: Run and verify missing protocol**

Run: `python3 -m pytest tests/test_optical_protocol.py -q`

Expected: FAIL because `dashpi.optical.protocol` does not exist.

- [ ] **Step 3: Implement one fixed v1 layout**

```python
# src/dashpi/optical/protocol.py
from dataclasses import dataclass
import struct, zlib

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

def pack_frame(frame: OpticalFrame) -> bytes:
    if not frame.indices or len(frame.indices) > 255 or len(frame.symbol) != frame.block_size: raise ValueError("invalid symbol")
    if len(set(frame.indices)) != len(frame.indices) or any(index < 0 or index >= frame.block_count for index in frame.indices): raise ValueError("invalid block index")
    prefix = HEADER.pack(b"DPQ1", 1, 0, frame.session_id, frame.sequence, frame.block_count, frame.block_size, frame.total_length, len(frame.indices))
    body = struct.pack(f"<{len(frame.indices)}H", *frame.indices) + frame.symbol
    wire = prefix + body
    return wire + CRC.pack(zlib.crc32(wire))

def parse_frame(data: bytes) -> OpticalFrame:
    if len(data) < HEADER.size + CRC.size: raise ValueError("truncated frame")
    if zlib.crc32(data[:-4]) != CRC.unpack(data[-4:])[0]: raise ValueError("crc mismatch")
    magic, version, flags, session, sequence, count, size, total, degree = HEADER.unpack_from(data)
    if magic != b"DPQ1": raise ValueError("foreign frame")
    if version != 1 or flags: raise ValueError("unsupported protocol")
    expected = HEADER.size + degree * 2 + size + CRC.size
    if degree == 0 or count == 0 or size == 0 or total == 0 or expected != len(data): raise ValueError("malformed frame")
    indices = struct.unpack_from(f"<{degree}H", data, HEADER.size)
    symbol = data[HEADER.size + degree * 2:-4]
    frame = OpticalFrame(session, sequence, count, size, total, indices, symbol)
    pack_frame(frame)
    return frame

def stream_identity(frame: OpticalFrame) -> tuple[int, int, int, int]:
    return frame.session_id, frame.block_count, frame.block_size, frame.total_length
```

- [ ] **Step 4: Pin the exact vector and rerun tests**

```json
{
  "fields": {
    "session_id": 16909060,
    "sequence": 5,
    "block_count": 3,
    "block_size": 4,
    "total_length": 10,
    "indices": [0, 2]
  },
  "wire_hex": "4450513101000403020105000000030004000a00000002000002006162636439137b7c"
}
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2023", "DOM"],
    "resolveJsonModule": true,
    "strict": true,
    "noEmit": true,
    "allowImportingTsExtensions": true
  },
  "include": ["src", "tests"]
}
```

Run: `python3 -m pytest tests/test_optical_protocol.py -q && python3 -m pytest -q`

Expected: protocol tests and full suite pass.

- [ ] **Step 5: Commit the protocol contract**

```bash
git add src/dashpi/optical/protocol.py tests/test_optical_protocol.py tests/fixtures/optical-v1.json
git commit -m "feat: define DashPi optical v1 frames"
```

### Task 3: Fountain Encoder and Peeling Decoder

**Files:**
- Create: `src/dashpi/optical/fountain.py`
- Test: `tests/test_optical_fountain.py`

**Interfaces:**
- Produces: `split_blocks(data, block_size)`, `FountainEncoder.symbol(sequence)`, `FountainDecoder.add(indices, symbol)`, `FountainDecoder.result() -> bytes | None`
- The encoded frame carries its block indices, so Python and TypeScript do not need identical floating-point soliton math.

- [ ] **Step 1: Write systematic, reordered, and 15%-loss tests**

```python
import random
from dashpi.optical.fountain import FountainDecoder, FountainEncoder

def test_systematic_symbols_recover_in_any_order():
    payload = bytes(range(251)) * 20
    encoder = FountainEncoder(payload, block_size=256, seed=7)
    symbols = [encoder.symbol(sequence) for sequence in range(encoder.block_count)]
    decoder = FountainDecoder(encoder.block_count, encoder.block_size, len(payload))
    for indices, data in reversed(symbols): decoder.add(indices, data)
    assert decoder.result() == payload

def test_one_megabyte_survives_loss_duplicates_and_reordering():
    payload = random.Random(9).randbytes(1024 * 1024)
    encoder = FountainEncoder(payload, block_size=1024, seed=11)
    frames = [encoder.symbol(sequence) for sequence in range(encoder.block_count * 2)]
    kept = [frame for index, frame in enumerate(frames) if index % 20 not in {1, 7, 13}]
    kept += kept[:20]; random.Random(5).shuffle(kept)
    decoder = FountainDecoder(encoder.block_count, encoder.block_size, len(payload))
    for indices, data in kept:
        decoder.add(indices, data)
        if decoder.result() is not None: break
    assert decoder.result() == payload
```

- [ ] **Step 2: Run and verify missing fountain module**

Run: `python3 -m pytest tests/test_optical_fountain.py -q`

Expected: FAIL because `dashpi.optical.fountain` does not exist.

- [ ] **Step 3: Implement systematic symbols plus bounded LT repair equations**

```python
# src/dashpi/optical/fountain.py
import random

def xor_into(target: bytearray, source: bytes) -> None:
    for index, value in enumerate(source): target[index] ^= value

def split_blocks(data: bytes, block_size: int) -> list[bytes]:
    return [data[offset:offset + block_size].ljust(block_size, b"\0") for offset in range(0, len(data), block_size)]

class FountainEncoder:
    def __init__(self, data: bytes, block_size: int, seed: int):
        self.data, self.block_size, self.seed = data, block_size, seed
        self.blocks = split_blocks(data, block_size); self.block_count = len(self.blocks)
    def symbol(self, sequence: int) -> tuple[tuple[int, ...], bytes]:
        if sequence < self.block_count: indices = (sequence,)
        else:
            rng = random.Random((self.seed << 32) | sequence)
            # ponytail: fixed repair degree favors reliable MVP recovery; use robust-soliton tuning when measured overhead matters.
            degree = min(self.block_count, 10)
            indices = tuple(sorted(rng.sample(range(self.block_count), degree)))
        symbol = bytearray(self.block_size)
        for index in indices: xor_into(symbol, self.blocks[index])
        return indices, bytes(symbol)

class FountainDecoder:
    def __init__(self, block_count: int, block_size: int, total_length: int):
        self.block_count, self.block_size, self.total_length = block_count, block_size, total_length
        self.blocks: dict[int, bytes] = {}; self.equations: list[tuple[set[int], bytearray]] = []
    def add(self, indices: tuple[int, ...], symbol: bytes) -> None:
        unknown, value = set(indices), bytearray(symbol)
        for index in tuple(unknown & self.blocks.keys()): xor_into(value, self.blocks[index]); unknown.remove(index)
        if unknown: self.equations.append((unknown, value))
        changed = True
        while changed:
            changed = False
            for equation_indices, equation_value in self.equations:
                if len(equation_indices) != 1: continue
                index = next(iter(equation_indices))
                if index in self.blocks: continue
                self.blocks[index] = bytes(equation_value); changed = True
                for other_indices, other_value in self.equations:
                    if other_indices is equation_indices or index not in other_indices: continue
                    xor_into(other_value, equation_value); other_indices.remove(index)
    def result(self) -> bytes | None:
        if len(self.blocks) != self.block_count: return None
        return b"".join(self.blocks[index] for index in range(self.block_count))[:self.total_length]
```

- [ ] **Step 4: Run the loss test repeatedly and full suite**

Run: `for run in 1 2 3; do python3 -m pytest tests/test_optical_fountain.py -q || exit 1; done`

Expected: every deterministic run reconstructs the payload.

Run: `python3 -m pytest -q`

Expected: full Python suite passes.

- [ ] **Step 5: Commit fountain coding**

```bash
git add src/dashpi/optical/fountain.py tests/test_optical_fountain.py
git commit -m "feat: add optical fountain recovery"
```

### Task 4: Optical Session and Binary Frame API

**Files:**
- Create: `src/dashpi/optical/session.py`
- Modify: `src/dashpi/api.py`
- Test: `tests/test_optical_session.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces: `OpticalSession.from_file(path, media_type, block_size, session_id)`, `session.frame(sequence) -> bytes`
- API: `POST /api/incidents/{id}/optical`, `GET /api/optical/{session_id}`, `GET /api/optical/{session_id}/frames/{sequence}`

- [ ] **Step 1: Write deterministic session and API limit tests**

```python
import pytest
from fastapi.testclient import TestClient
from dashpi.api import create_app
from dashpi.models import IncidentMetadata, IncidentState
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession
from dashpi.storage import IncidentStore, atomic_write

def test_session_repeats_sequence_exactly(tmp_path):
    path = tmp_path / "report.html"; path.write_bytes(b"report")
    session = OpticalSession.from_file(path, "text/html", block_size=64, session_id=7)
    assert session.frame(10) == session.frame(10)
    assert parse_frame(session.frame(10)).session_id == 7

@pytest.fixture
def client_with_oversized_incident(tmp_path):
    store = IncidentStore(tmp_path)
    item = IncidentMetadata.new("inc-big", "2026-09-02T00:00:00Z", 40.0, 15.0)
    item.state = IncidentState.READY
    item.clip = atomic_write(store.directory("inc-big") / "clip.mp4", b"x" * (MAX_PAYLOAD + 1))
    store.save(item)
    return TestClient(create_app(store))

def test_api_refuses_oversized_clip(client_with_oversized_incident):
    response = client_with_oversized_incident.post("/api/incidents/inc-big/optical", json={"artifact": "clip", "block_size": 512})
    assert response.status_code == 413
```

- [ ] **Step 2: Run and verify missing session/endpoints**

Run: `python3 -m pytest tests/test_optical_session.py tests/test_api.py::test_api_refuses_oversized_clip -q`

Expected: FAIL because sessions and endpoints do not exist.

- [ ] **Step 3: Implement in-memory active sessions with bounded input**

```python
# src/dashpi/optical/session.py
from dataclasses import dataclass
from pathlib import Path
from dashpi.optical.container import pack_container
from dashpi.optical.fountain import FountainEncoder
from dashpi.optical.protocol import OpticalFrame, pack_frame

@dataclass
class OpticalSession:
    session_id: int
    encoder: FountainEncoder
    total_length: int
    @classmethod
    def from_file(cls, path: Path, media_type: str, block_size: int, session_id: int):
        packed = pack_container(path.name, media_type, path.read_bytes())
        return cls(session_id, FountainEncoder(packed, block_size, session_id), len(packed))
    def frame(self, sequence: int) -> bytes:
        indices, symbol = self.encoder.symbol(sequence)
        return pack_frame(OpticalFrame(self.session_id, sequence, self.encoder.block_count, self.encoder.block_size, self.total_length, indices, symbol))
```

```python
# add inside create_app in src/dashpi/api.py
import secrets
from typing import Literal
from fastapi import HTTPException, Response
from pydantic import BaseModel, Field
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.optical.session import OpticalSession

class OpticalStart(BaseModel):
    artifact: Literal["clip", "report"]
    block_size: int = Field(ge=512, le=2048)

sessions: dict[int, OpticalSession] = {}

@app.post("/api/incidents/{incident_id}/optical")
def start_optical(incident_id: str, request: OpticalStart):
    try: item = store.load(incident_id)
    except (FileNotFoundError, KeyError): raise HTTPException(404)
    artifact = item.clip if request.artifact == "clip" else item.report_html
    if artifact is None: raise HTTPException(404)
    if artifact.byte_length > MAX_PAYLOAD: raise HTTPException(413, "optical payload exceeds 16 MiB")
    session_id = secrets.randbits(32)
    session = OpticalSession.from_file(artifact.path, "video/mp4" if request.artifact == "clip" else "text/html", request.block_size, session_id)
    sessions.clear(); sessions[session_id] = session
    return {"session_id": session_id, "block_count": session.encoder.block_count, "block_size": session.encoder.block_size, "total_length": session.total_length}

@app.get("/api/optical/{session_id}")
def optical_status(session_id: int):
    session = sessions.get(session_id)
    if session is None: raise HTTPException(404)
    return {"session_id": session_id, "block_count": session.encoder.block_count, "block_size": session.encoder.block_size, "total_length": session.total_length}

@app.get("/api/optical/{session_id}/frames/{sequence}")
def optical_frame(session_id: int, sequence: int):
    session = sessions.get(session_id)
    if session is None or sequence < 0: raise HTTPException(404)
    return Response(session.frame(sequence), media_type="application/octet-stream", headers={"Cache-Control": "no-store"})
```

- [ ] **Step 4: Run session, API, and full Python tests**

Run: `python3 -m pytest tests/test_optical_session.py tests/test_api.py -q && python3 -m pytest -q`

Expected: deterministic frame bytes, bounds, and API responses pass.

- [ ] **Step 5: Commit the sender API**

```bash
git add src/dashpi/optical/session.py src/dashpi/api.py tests/test_optical_session.py tests/test_api.py
git commit -m "feat: expose optical frame sessions"
```

### Task 5: TypeScript Protocol and Fountain Interoperability

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/src/optical/protocol.ts`
- Create: `web/src/optical/fountain.ts`
- Create: `web/tests/protocol.test.ts`
- Create: `web/tests/fountain.test.ts`

**Interfaces:**
- Consumes: `tests/fixtures/optical-v1.json` and Python-generated session vectors
- Produces: `parseFrame(Uint8Array)`, `FountainDecoder.add(frame)`, `FountainDecoder.result()`

- [ ] **Step 1: Create the web test command and failing vector test**

```json
{
  "name": "dashpi-web",
  "private": true,
  "type": "module",
  "scripts": {"test": "tsx --test tests/*.test.ts", "build": "node build.mjs"},
  "dependencies": {"@zxing/browser": "^0.1.5", "qrcode": "^1.5.4"},
  "devDependencies": {"@types/node": "^22.0.0", "@types/qrcode": "^1.5.5", "esbuild": "^0.25.0", "tsx": "^4.20.0", "typescript": "^5.9.0"}
}
```

```typescript
// web/tests/protocol.test.ts
import assert from 'node:assert/strict';
import test from 'node:test';
import vector from '../../tests/fixtures/optical-v1.json' with { type: 'json' };
import { parseFrame } from '../src/optical/protocol.ts';

test('parses the Python golden vector', () => {
  const frame = parseFrame(Uint8Array.from(vector.wire_hex.match(/../g)!.map(value => Number.parseInt(value, 16))));
  assert.equal(frame.sessionId, vector.fields.session_id);
  assert.deepEqual(frame.indices, vector.fields.indices);
});
```

- [ ] **Step 2: Install locked dependencies and verify failure**

Run: `cd web && npm install && npm test`

Expected: FAIL because the TypeScript parser does not exist; commit the generated `package-lock.json`.

- [ ] **Step 3: Implement DataView parsing and the same peeling algorithm**

```typescript
// web/src/optical/protocol.ts
export type OpticalFrame = {sessionId:number; sequence:number; blockCount:number; blockSize:number; totalLength:number; indices:number[]; symbol:Uint8Array};
function crc32(bytes:Uint8Array):number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit=0; bit<8; bit++) crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
  }
  return (crc ^ 0xffffffff) >>> 0;
}
export function parseFrame(bytes: Uint8Array): OpticalFrame {
  if (bytes.length < 27) throw new Error('truncated frame');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (crc32(bytes.subarray(0, -4)) !== view.getUint32(bytes.length - 4, true)) throw new Error('crc mismatch');
  if (new TextDecoder().decode(bytes.subarray(0, 4)) !== 'DPQ1') throw new Error('foreign frame');
  if (view.getUint8(4) !== 1 || view.getUint8(5) !== 0) throw new Error('unsupported protocol');
  const degree = view.getUint8(22), blockCount = view.getUint16(14, true), blockSize = view.getUint16(16, true), totalLength = view.getUint32(18, true);
  const expected = 23 + degree * 2 + blockSize + 4;
  if (!degree || !blockCount || !blockSize || !totalLength || expected !== bytes.length) throw new Error('malformed frame');
  const indices = Array.from({length: degree}, (_, index) => view.getUint16(23 + index * 2, true));
  if (new Set(indices).size !== indices.length || indices.some(index => index >= blockCount)) throw new Error('malformed frame');
  return {sessionId:view.getUint32(6,true), sequence:view.getUint32(10,true), blockCount, blockSize, totalLength, indices, symbol:bytes.slice(23 + degree * 2, -4)};
}
```

```typescript
// web/src/optical/fountain.ts
import type { OpticalFrame } from './protocol.ts';
function xorInto(target:Uint8Array, source:Uint8Array) { for (let index=0; index<target.length; index++) target[index] ^= source[index]; }

export class FountainDecoder {
  private blocks = new Map<number,Uint8Array>();
  private equations:{indices:Set<number>; value:Uint8Array}[] = [];
  constructor(private blockCount:number, private blockSize:number, private totalLength:number) {}
  add(frame:OpticalFrame) {
    if (frame.blockCount !== this.blockCount || frame.blockSize !== this.blockSize || frame.totalLength !== this.totalLength) throw new Error('stream changed');
    const indices = new Set(frame.indices), value = frame.symbol.slice();
    for (const index of [...indices]) { const block=this.blocks.get(index); if (block) { xorInto(value, block); indices.delete(index); } }
    if (indices.size) this.equations.push({indices,value});
    let changed = true;
    while (changed) {
      changed = false;
      for (const equation of this.equations) {
        if (equation.indices.size !== 1) continue;
        const index = equation.indices.values().next().value as number;
        if (this.blocks.has(index)) continue;
        this.blocks.set(index, equation.value.slice()); changed = true;
        for (const other of this.equations) if (other !== equation && other.indices.delete(index)) xorInto(other.value, equation.value);
      }
    }
  }
  result():Uint8Array|undefined {
    if (this.blocks.size !== this.blockCount) return undefined;
    const output = new Uint8Array(this.blockCount * this.blockSize);
    for (let index=0; index<this.blockCount; index++) output.set(this.blocks.get(index)!, index*this.blockSize);
    return output.slice(0, this.totalLength);
  }
}
```

```typescript
// web/tests/fountain.test.ts
import assert from 'node:assert/strict'; import test from 'node:test';
import { FountainDecoder } from '../src/optical/fountain.ts';
test('recovers carried equations without a shared PRNG', () => {
  const decoder = new FountainDecoder(2, 3, 6);
  decoder.add({sessionId:1,sequence:1,blockCount:2,blockSize:3,totalLength:6,indices:[1],symbol:Uint8Array.of(100,101,102)});
  decoder.add({sessionId:1,sequence:0,blockCount:2,blockSize:3,totalLength:6,indices:[0],symbol:Uint8Array.of(97,98,99)});
  assert.equal(new TextDecoder().decode(decoder.result()), 'abcdef');
});
```

- [ ] **Step 4: Run TypeScript and Python interoperability tests**

Run: `cd web && npm test && npx tsc --noEmit`

Expected: vector and recovery tests pass; TypeScript compiles.

Run: `python3 -m pytest tests/test_optical_protocol.py tests/test_optical_fountain.py -q`

Expected: Python contract remains green.

- [ ] **Step 5: Commit cross-language decoding**

```bash
git add web/package.json web/package-lock.json web/tsconfig.json web/src/optical web/tests tests/fixtures
git commit -m "feat: decode optical frames in the browser"
```

### Task 6: DashPi Sender Screen

**Files:**
- Create: `web/src/sender.ts`
- Create: `web/public/sender.html`
- Create: `web/build.mjs`
- Create: `web/tests/sender.test.ts`

**Interfaces:**
- Consumes: optical session/frame API
- Produces: start/stop sender with `bytes/frame`, QR scale, and FPS controls; mandatory confidentiality warning

- [ ] **Step 1: Write the sender contract test**

```typescript
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('sender requires warning acknowledgement and calibration controls', async () => {
  const html = await readFile(new URL('../public/sender.html', import.meta.url), 'utf8');
  for (const text of ['not encrypted', 'bytes/frame', 'QR scale', 'frames/second']) assert.ok(html.includes(text));
  assert.ok(html.includes('type="checkbox"'));
});
```

- [ ] **Step 2: Run and verify missing sender**

Run: `cd web && npm test`

Expected: FAIL because `sender.html` does not exist.

- [ ] **Step 3: Implement one canvas and a timer-driven fetch/render loop**

```typescript
// web/src/sender.ts
import QRCode from 'qrcode';
const canvas = document.querySelector('canvas')!;
const startButton = document.querySelector<HTMLButtonElement>('#start')!;
const warning = document.querySelector<HTMLInputElement>('#warning')!;
const sequenceLabel = document.querySelector('#sequence')!;
let timer:number|undefined, sequence = 0;
export async function start() {
  const incidentId = new URL(location.href).searchParams.get('incident');
  if (!incidentId || !warning.checked) return;
  const blockSize = Number((document.querySelector('#bytes') as HTMLSelectElement).value);
  const fps = Number((document.querySelector('#fps') as HTMLSelectElement).value);
  const created = await fetch(`/api/incidents/${encodeURIComponent(incidentId)}/optical`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({artifact:(document.querySelector('#artifact') as HTMLSelectElement).value,block_size:blockSize})});
  if (!created.ok) throw new Error(`session failed: ${created.status}`);
  const {session_id:sessionId} = await created.json();
  stop(); sequence = 0;
  timer = window.setInterval(async () => {
    const response = await fetch(`/api/optical/${sessionId}/frames/${sequence++}`, {cache:'no-store'});
    const bytes = new Uint8Array(await response.arrayBuffer());
    await QRCode.toCanvas(canvas, [{data:bytes, mode:'byte'}], {errorCorrectionLevel:'L', margin:1, scale:Number((document.querySelector('#scale') as HTMLInputElement).value)});
    sequenceLabel.textContent = String(sequence);
  }, 1000 / fps);
  await navigator.wakeLock?.request('screen');
}
export function stop() { if (timer !== undefined) window.clearInterval(timer); timer = undefined; }
warning.addEventListener('change', () => { startButton.disabled = !warning.checked; });
startButton.addEventListener('click', () => void start());
document.querySelector('#stop')!.addEventListener('click', stop);
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
```

```html
<!-- web/public/sender.html -->
<main>
  <h1>DashPi optical sender</h1>
  <p>This optical stream is not encrypted. Anyone with line of sight can capture it.</p>
  <label><input id="warning" type="checkbox"> I understand</label>
  <label>File <select id="artifact"><option value="report">Report</option><option value="clip">Clip</option></select></label>
  <label>bytes/frame <select id="bytes"><option>512</option><option>1024</option><option>1465</option></select></label>
  <label>QR scale <input id="scale" type="range" min="2" max="10" value="4"></label>
  <label>frames/second <select id="fps"><option>10</option><option>24</option><option>30</option></select></label>
  <button id="start" disabled>Start</button><button id="stop">Stop</button>
  <p>Frame <output id="sequence">0</output></p><canvas aria-label="Animated transfer QR"></canvas>
</main>
<script type="module" src="/assets/sender.js"></script>
```

```javascript
// web/build.mjs
import { build } from 'esbuild';
import { cp, mkdir, rm } from 'node:fs/promises';
await rm('dist',{recursive:true,force:true}); await cp('public','dist',{recursive:true});
await build({entryPoints:{sender:'src/sender.ts'},bundle:true,format:'esm',target:['safari17','chrome120'],outdir:'dist/assets',minify:true});
await mkdir('../src/dashpi/web/assets',{recursive:true});
await cp('dist/assets/sender.js','../src/dashpi/web/assets/sender.js');
await cp('dist/sender.html','../src/dashpi/web/sender.html');
```

- [ ] **Step 4: Run sender tests and production build**

Run: `cd web && npm test && npm run build`

Expected: sender contract passes and the bundle contains no `http://` or `https://` dependency URLs.

- [ ] **Step 5: Commit the display sender**

```bash
git add web/src/sender.ts web/public/sender.html web/build.mjs web/tests/sender.test.ts src/dashpi/web/assets
git commit -m "feat: display animated optical QR frames"
```

### Task 7: Offline Receiver PWA

**Files:**
- Create: `web/src/receiver.ts`
- Create: `web/src/optical/container.ts`
- Create: `web/public/receiver.html`
- Create: `web/public/manifest.webmanifest`
- Create: `web/public/sw.js`
- Create: `web/public/icon.svg`
- Modify: `web/build.mjs`
- Create: `web/tests/receiver.test.ts`
- Create: `web/tests/offline.test.ts`

**Interfaces:**
- Consumes: phone camera via `@zxing/browser`, `parseFrame`, browser `FountainDecoder`, container parser
- Produces: verified file preview/save; `foreign` frames remain silent; unsupported versions speak clearly

- [ ] **Step 1: Write receiver privacy and offline-shell tests**

```typescript
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('receiver does not auto-save or load remote assets', async () => {
  const html = await readFile(new URL('../public/receiver.html', import.meta.url), 'utf8');
  assert.equal(/https?:\/\//.test(html), false);
  assert.ok(html.includes('Start camera'));
  assert.ok(html.includes('Save verified file'));
});

test('service worker caches only application assets', async () => {
  const source = await readFile(new URL('../public/sw.js', import.meta.url), 'utf8');
  assert.ok(source.includes('dashpi-optical-v1'));
  assert.equal(source.includes('/api/'), false);
});
```

- [ ] **Step 2: Run and verify missing receiver**

Run: `cd web && npm test`

Expected: FAIL because receiver files do not exist.

- [ ] **Step 3: Implement camera decode, stream reset, verification, and explicit save**

```typescript
// core of web/src/receiver.ts
import { BrowserQRCodeReader } from '@zxing/browser';
import { parseFrame } from './optical/protocol.ts';
import { FountainDecoder } from './optical/fountain.ts';
import { unpackContainer } from './optical/container.ts';

let identity = '', decoder:FountainDecoder|undefined, objectUrl:string|undefined;
const reader = new BrowserQRCodeReader();
export async function startCamera(deviceId?:string) {
  await reader.decodeFromVideoDevice(deviceId, 'camera', (result) => {
    if (!result) return;
    const raw = result.getRawBytes();
    if (!raw) return;
    try {
      const frame = parseFrame(Uint8Array.from(raw));
      const nextIdentity = `${frame.sessionId}:${frame.blockCount}:${frame.blockSize}:${frame.totalLength}`;
      if (nextIdentity !== identity) { identity = nextIdentity; decoder = new FountainDecoder(frame.blockCount, frame.blockSize, frame.totalLength); }
      decoder!.add(frame);
      const packed = decoder!.result();
      if (packed) void verifyContainerAndEnableSave(packed);
    } catch (problem) {
      if (String(problem).includes('unsupported protocol')) document.querySelector('#status')!.textContent = 'Update this receiver to read the sender format.';
    }
  });
}

async function verifyContainerAndEnableSave(packed:Uint8Array) {
  const file = await unpackContainer(packed);
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(new Blob([file.payload],{type:file.mediaType}));
  const save = document.querySelector<HTMLAnchorElement>('#save')!;
  save.href = objectUrl; save.download = file.name; save.hidden = false;
  document.querySelector('#status')!.textContent = `Verified ${file.name}`;
}
document.querySelector('#start-camera')!.addEventListener('click', () => void startCamera());
```

```typescript
// web/src/optical/container.ts
export type OpticalFile={name:string;mediaType:string;payload:Uint8Array};
const decoder = new TextDecoder();
async function inflateBounded(body:Uint8Array):Promise<Uint8Array> {
  const reader=new Blob([body]).stream().pipeThrough(new DecompressionStream('deflate')).getReader(), chunks:Uint8Array[]=[]; let total=0;
  while (true) {
    const {done,value}=await reader.read(); if (done) break;
    total+=value.length; if (total>16*1024*1024) { await reader.cancel(); throw new Error('payload exceeds 16 MiB'); }
    chunks.push(value);
  }
  const output=new Uint8Array(total); let offset=0; for (const chunk of chunks) {output.set(chunk,offset);offset+=chunk.length;} return output;
}
export async function unpackContainer(data:Uint8Array):Promise<OpticalFile> {
  if (data.length < 49 || decoder.decode(data.subarray(0,4)) !== 'DPC1') throw new Error('invalid container');
  const view = new DataView(data.buffer,data.byteOffset,data.byteLength), flags=view.getUint8(4);
  const nameLength=view.getUint16(5,true), mediaLength=view.getUint16(7,true), originalLength=view.getUint32(9,true), bodyLength=view.getUint32(13,true);
  if (flags & ~1 || originalLength > 16*1024*1024 || 49+nameLength+mediaLength+bodyLength !== data.length) throw new Error('invalid container');
  const expectedHash=data.slice(17,49); let offset=49;
  const name=decoder.decode(data.slice(offset,offset+nameLength)).split(/[\\/]/).pop()!; offset+=nameLength;
  const mediaType=decoder.decode(data.slice(offset,offset+mediaLength)); offset+=mediaLength;
  const body=data.slice(offset), payload=flags&1 ? await inflateBounded(body) : body;
  const actualHash=new Uint8Array(await crypto.subtle.digest('SHA-256',payload));
  if (payload.length !== originalLength || !actualHash.every((value,index)=>value===expectedHash[index])) throw new Error('sha256 mismatch');
  return {name,mediaType,payload};
}
```

```html
<!-- web/public/receiver.html -->
<link rel="manifest" href="/manifest.webmanifest"><main><h1>DashPi optical receiver</h1><p id="status" role="status">Ready</p><button id="start-camera">Start camera</button><video id="camera" playsinline muted></video><a id="save" hidden>Save verified file</a></main>
<script type="module" src="/assets/receiver.js"></script>
<script>if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');</script>
```

```json
{
  "name":"DashPi Optical Receiver",
  "short_name":"DashPi",
  "start_url":"/receiver.html",
  "display":"standalone",
  "icons":[{"src":"/icon.svg","sizes":"any","type":"image/svg+xml"}]
}
```

```javascript
// web/public/sw.js
const CACHE='dashpi-optical-v1', ASSETS=['/receiver.html','/manifest.webmanifest','/icon.svg','/assets/receiver.js'];
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS))));
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.method==='GET')event.respondWith(caches.match(event.request).then(hit=>hit||fetch(event.request)));});
```

```svg
<!-- web/public/icon.svg -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="12" fill="currentColor"/><path d="M14 18h36v28H14zM20 24v16h24V24z" fill="white"/></svg>
```

In `web/build.mjs`, change `entryPoints` to `{sender:'src/sender.ts',receiver:'src/receiver.ts'}` so `dist/assets/receiver.js` is built after the receiver exists.

- [ ] **Step 4: Run web tests, build, and offline asset audit**

Run: `cd web && npm test && npm run build`

Expected: all browser-unit contracts pass and build succeeds.

Run: `if rg -n 'https?://' src/dashpi/web/assets web/public; then exit 1; fi; if rg -n '/api/' web/public/sw.js; then exit 1; fi`

Expected: no remote runtime assets and no API response caching.

- [ ] **Step 5: Commit the offline receiver**

```bash
git add web/src/receiver.ts web/public web/tests/receiver.test.ts web/tests/offline.test.ts src/dashpi/web/assets
git commit -m "feat: receive optical files offline"
```

### Task 8: End-to-End Loss and Build Verification

**Files:**
- Create: `scripts/make_optical_fixture.py`
- Create: `tests/test_optical_e2e.py`
- Create: `web/tests/e2e-vector.test.ts`
- Modify: `docs/TRD.md`

**Interfaces:**
- Produces: one deterministic 1 MiB cross-language fixture manifest with selected frame hex files
- Consumes: complete Python sender and TypeScript receiver

- [ ] **Step 1: Write a failing cross-language acceptance test**

```python
# tests/test_optical_e2e.py
import hashlib, random
from dashpi.optical.container import unpack_container
from dashpi.optical.fountain import FountainDecoder
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession

def test_one_megabyte_survives_deterministic_frame_loss(tmp_path):
    payload = random.Random(9).randbytes(1024 * 1024)
    source = tmp_path / "source.bin"; source.write_bytes(payload)
    session = OpticalSession.from_file(source, "application/octet-stream", 1024, 11)
    frames = [session.frame(index) for index in range(session.encoder.block_count * 2) if index % 20 not in {1, 7, 13}]
    frames += frames[:20]; random.Random(5).shuffle(frames)
    first = parse_frame(frames[0]); decoder = FountainDecoder(first.block_count, first.block_size, first.total_length)
    for wire in frames:
        frame = parse_frame(wire); decoder.add(frame.indices, frame.symbol)
        if decoder.result() is not None: break
    recovered = unpack_container(decoder.result())
    assert hashlib.sha256(recovered.payload).hexdigest() == hashlib.sha256(payload).hexdigest()
```

```typescript
// web/tests/e2e-vector.test.ts
import assert from 'node:assert/strict'; import { createHash } from 'node:crypto'; import test from 'node:test';
import fixture from '../../tests/fixtures/optical-e2e.json' with {type:'json'};
import { unpackContainer } from '../src/optical/container.ts'; import { FountainDecoder } from '../src/optical/fountain.ts'; import { parseFrame } from '../src/optical/protocol.ts';
const fromHex=(hex:string)=>Uint8Array.from(hex.match(/../g)!.map(value=>Number.parseInt(value,16)));
test('browser recovers the Python loss fixture', async () => {
  const first=parseFrame(fromHex(fixture.frames_hex[0])); const decoder=new FountainDecoder(first.blockCount,first.blockSize,first.totalLength);
  for (const hex of fixture.frames_hex) { decoder.add(parseFrame(fromHex(hex))); if (decoder.result()) break; }
  const file=await unpackContainer(decoder.result()!);
  assert.equal(createHash('sha256').update(file.payload).digest('hex'),fixture.payload_sha256);
});
```

- [ ] **Step 2: Run both suites and verify the acceptance test fails**

Run: `python3 -m pytest tests/test_optical_e2e.py -q && cd web && npm test`

Expected: FAIL until fixture generation and the browser container verifier are wired together.

- [ ] **Step 3: Add the deterministic fixture script and document measured scope**

```python
# scripts/make_optical_fixture.py
from pathlib import Path
import hashlib, json, random
from dashpi.optical.session import OpticalSession

payload = random.Random(9).randbytes(1024 * 1024)
source = Path(".tmp/optical-source.bin"); source.parent.mkdir(exist_ok=True); source.write_bytes(payload)
session = OpticalSession.from_file(source, "application/octet-stream", 1024, 11)
count = session.encoder.block_count * 2
frames = [session.frame(index) for index in range(count) if index % 20 not in {1, 7, 13}]
frames += frames[:20]; random.Random(5).shuffle(frames)
manifest = {"payload_sha256": hashlib.sha256(payload).hexdigest(), "frames_hex": [frame.hex() for frame in frames]}
encoded = json.dumps(manifest, separators=(",", ":"))
if len(encoded.encode()) > 8 * 1024 * 1024: raise RuntimeError("optical fixture exceeds 8 MiB")
Path("tests/fixtures/optical-e2e.json").write_text(encoded)
```

- [ ] **Step 4: Run fresh acceptance checks**

Run: `python3 -m pytest -q`

Expected: all Python tests pass, including deterministic loss recovery.

Run: `cd web && npm test && npm run build`

Expected: all TypeScript tests pass and offline bundles build.

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended plan implementation files remain staged or modified.

- [ ] **Step 5: Commit the optical PoC acceptance slice**

```bash
git add scripts/make_optical_fixture.py tests/test_optical_e2e.py tests/fixtures/optical-e2e.json web/tests/e2e-vector.test.ts docs/TRD.md
git commit -m "test: verify optical transfer under frame loss"
```

## Plan Acceptance

Run:

```bash
python3 -m pytest -q
cd web && npm test && npm run build
```

Accept when Python and TypeScript recover the same 1 MiB payload after deterministic 15% loss, duplicates, and reordering; corrupted payloads fail SHA-256; the receiver starts from its cached shell with networking disabled; and sender controls expose frame rate, QR scale, and payload calibration. Camera/display throughput remains a later hardware acceptance measurement.
