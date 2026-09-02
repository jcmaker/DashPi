export type OpticalFile = { name: string; mediaType: string; payload: Uint8Array };

const HEADER_SIZE = 49;
const MAX_PAYLOAD = 16 * 1024 * 1024;
const MAX_TEXT_FIELD = 255;
const textDecoder = new TextDecoder('utf-8', { fatal: true });

async function inflateBounded(body: Uint8Array, expectedLength: number): Promise<Uint8Array> {
  const compressed = new Uint8Array(body.length);
  compressed.set(body);
  const reader = new Blob([compressed])
    .stream()
    .pipeThrough(new DecompressionStream('deflate'))
    .getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > expectedLength || total > MAX_PAYLOAD) {
        await reader.cancel();
        throw new Error('invalid container length');
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof Error && error.message === 'invalid container length') throw error;
    throw new Error('invalid compressed payload', { cause: error });
  }

  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

function metadata(data: Uint8Array, field: 'name' | 'media type'): string {
  let value: string;
  try { value = textDecoder.decode(data); } catch { throw new Error('invalid container metadata'); }
  if (!value) throw new Error('invalid container metadata');
  if (field === 'name' && (value === '.' || value === '..' || value.includes('/') || value.includes('\\') || value.includes('\0'))) {
    throw new Error('invalid container metadata');
  }
  return value;
}

export async function unpackContainer(data: Uint8Array): Promise<OpticalFile> {
  if (!(data instanceof Uint8Array) || data.length < HEADER_SIZE) throw new Error('truncated container');
  if (data[0] !== 0x44 || data[1] !== 0x50 || data[2] !== 0x43 || data[3] !== 0x31) {
    throw new Error('unsupported container');
  }

  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const flags = view.getUint8(4);
  const nameLength = view.getUint16(5, true);
  const mediaLength = view.getUint16(7, true);
  const originalLength = view.getUint32(9, true);
  const bodyLength = view.getUint32(13, true);
  if (flags > 1 || nameLength === 0 || mediaLength === 0 || nameLength > MAX_TEXT_FIELD || mediaLength > MAX_TEXT_FIELD) {
    throw new Error('unsupported container');
  }
  if (
    originalLength > MAX_PAYLOAD ||
    (flags === 0 && bodyLength !== originalLength) ||
    (flags === 1 && bodyLength >= originalLength) ||
    HEADER_SIZE + nameLength + mediaLength + bodyLength !== data.length
  ) {
    throw new Error('invalid container length');
  }

  const expectedHash = data.slice(17, HEADER_SIZE);
  let offset = HEADER_SIZE;
  const name = metadata(data.slice(offset, offset + nameLength), 'name');
  offset += nameLength;
  const mediaType = metadata(data.slice(offset, offset + mediaLength), 'media type');
  offset += mediaLength;
  const body = data.slice(offset);
  const payload = flags === 1 ? await inflateBounded(body, originalLength) : body;
  if (payload.length !== originalLength) throw new Error('invalid container length');

  const digestInput = new Uint8Array(payload.length);
  digestInput.set(payload);
  const actualHash = new Uint8Array(await crypto.subtle.digest('SHA-256', digestInput));
  let difference = 0;
  for (let index = 0; index < expectedHash.length; index += 1) difference |= actualHash[index] ^ expectedHash[index];
  if (difference !== 0) throw new Error('sha256 mismatch');
  return { name, mediaType, payload };
}
