export type OpticalFrame = {
  sessionId: number;
  sequence: number;
  blockCount: number;
  blockSize: number;
  totalLength: number;
  indices: number[];
  symbol: Uint8Array;
};

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

export function parseFrame(bytes: Uint8Array): OpticalFrame {
  if (!(bytes instanceof Uint8Array)) throw new Error('malformed frame');
  if (bytes.length < 27) throw new Error('truncated frame');

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (crc32(bytes.subarray(0, -4)) !== view.getUint32(bytes.length - 4, true)) {
    throw new Error('crc mismatch');
  }
  if (new TextDecoder().decode(bytes.subarray(0, 4)) !== 'DPQ1') {
    throw new Error('foreign frame');
  }
  if (view.getUint8(4) !== 1 || view.getUint8(5) !== 0) {
    throw new Error('unsupported protocol');
  }

  const blockCount = view.getUint16(14, true);
  const blockSize = view.getUint16(16, true);
  const totalLength = view.getUint32(18, true);
  const degree = view.getUint8(22);
  const expectedLength = 23 + degree * 2 + blockSize + 4;
  if (
    degree === 0 ||
    blockCount === 0 ||
    blockSize === 0 ||
    totalLength <= (blockCount - 1) * blockSize ||
    totalLength > blockCount * blockSize ||
    expectedLength !== bytes.length
  ) {
    throw new Error('malformed frame');
  }

  const indices = Array.from(
    { length: degree },
    (_, index) => view.getUint16(23 + index * 2, true),
  );
  if (
    new Set(indices).size !== indices.length ||
    indices.some((index) => index >= blockCount)
  ) {
    throw new Error('malformed frame');
  }
  const symbolOffset = 23 + degree * 2;

  return {
    sessionId: view.getUint32(6, true),
    sequence: view.getUint32(10, true),
    blockCount,
    blockSize,
    totalLength,
    indices,
    symbol: bytes.slice(symbolOffset, -4),
  };
}
