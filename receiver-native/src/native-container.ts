import * as Crypto from 'expo-crypto'
import pako from 'pako'
import { unpackOpticalContainer, type OpticalFile } from './unpack'

const MAX_PAYLOAD = 16 * 1024 * 1024

function inflateBounded(body: Uint8Array, expectedLength: number): Uint8Array {
  const chunks: Uint8Array[] = []
  let total = 0
  let oversized = false
  const inflator = new pako.Inflate()
  inflator.onData = (chunk) => {
    const bytes = chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk)
    total += bytes.length
    if (total > expectedLength || total > MAX_PAYLOAD) {
      oversized = true
      return
    }
    chunks.push(bytes)
  }
  try {
    inflator.push(body, true)
  } catch {
    throw new Error('invalid compressed payload')
  }
  if (oversized) throw new Error('invalid container length')
  if (inflator.err !== 0 && inflator.err !== 1) throw new Error('invalid compressed payload')

  const output = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    output.set(chunk, offset)
    offset += chunk.length
  }
  return output
}

export function unpackNativeContainer(data: Uint8Array): Promise<OpticalFile> {
  return unpackOpticalContainer(
    data,
    inflateBounded,
    async (payload) => {
      const digestInput = new Uint8Array(payload.byteLength)
      digestInput.set(payload)
      return new Uint8Array(await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256, digestInput))
    },
  )
}
