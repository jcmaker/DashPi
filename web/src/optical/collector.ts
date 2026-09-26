import { FountainDecoder } from './fountain.ts';
import type { OpticalFrame } from './protocol.ts';

export function messageForFrameError(problem: unknown): string | undefined {
  return String(problem).includes('unsupported protocol')
    ? '이 송신 형식을 읽으려면 수신기를 업데이트하세요.'
    : undefined;
}

// ZXing's getRawBytes() returns QR codewords with mode and length headers;
// the scanned bytes live in the BYTE_SEGMENTS result metadata.
export function qrPayload(segments: unknown): Uint8Array | undefined {
  if (!Array.isArray(segments) || segments.length === 0) return undefined;
  if (!segments.every((segment) => segment instanceof Uint8Array)) return undefined;
  const total = segments.reduce((sum: number, segment: Uint8Array) => sum + segment.length, 0);
  const payload = new Uint8Array(total);
  let offset = 0;
  for (const segment of segments as Uint8Array[]) {
    payload.set(segment, offset);
    offset += segment.length;
  }
  return payload;
}

export class FrameCollector {
  private decoder: FountainDecoder | undefined;
  private currentIdentity = '';
  private blockCount = 0;

  get identity(): string { return this.currentIdentity; }

  get progress(): { recovered: number; total: number } {
    return { recovered: this.decoder?.recoveredBlocks ?? 0, total: this.blockCount };
  }

  add(frame: OpticalFrame): Uint8Array | undefined {
    const identity = `${frame.sessionId}:${frame.blockCount}:${frame.blockSize}:${frame.totalLength}`;
    if (identity !== this.currentIdentity) {
      this.currentIdentity = identity;
      this.blockCount = frame.blockCount;
      this.decoder = new FountainDecoder(frame.blockCount, frame.blockSize, frame.totalLength);
    }
    this.decoder!.add(frame);
    return this.decoder!.result();
  }
}
