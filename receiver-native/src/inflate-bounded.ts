import { Inflate } from 'pako'

const MAX_PAYLOAD = 16 * 1024 * 1024

export function inflateBounded(body: Uint8Array, expectedLength: number): Uint8Array {
  const cap = Math.min(expectedLength, MAX_PAYLOAD)
  const chunks: Uint8Array[] = []
  let total = 0
  const inflator = new Inflate({ chunkSize: cap + 1 })
  inflator.onData = (chunk) => {
    const bytes = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk)
    if (total + bytes.length > cap) {
      // Returning from onData does not stop Inflate.push; it keeps reading until the zlib stream ends.
      throw new Error('invalid container length')
    }
    chunks.push(bytes)
    total += bytes.length
  }
  try {
    inflator.push(body, true)
  } catch (error) {
    if (error instanceof Error && error.message === 'invalid container length') throw error
    throw new Error('invalid compressed payload')
  }
  if (inflator.err !== 0 && inflator.err !== 1) throw new Error('invalid compressed payload')

  const output = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    output.set(chunk, offset)
    offset += chunk.length
  }
  return output
}
