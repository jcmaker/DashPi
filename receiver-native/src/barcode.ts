import { FrameCollector, messageForFrameError } from '../../web/src/optical/collector.ts'
import { parseFrame } from '../../web/src/optical/protocol.ts'

// Android CameraView sets `data` from ML Kit displayValue (`null` becomes the
// string "null") and `raw` from UTF-8 `String(rawBytes)`. Neither field can
// hold a byte-mode QR payload. The expo-camera patch adds `rawBytesBase64`.
export type BarcodeScan = {
  data?: string | null
  raw?: string | null
  rawBytesBase64?: string | null
}

export type BarcodeScanOutcome =
  | { status: 'ignore' }
  | { status: 'drop' }
  | { status: 'error'; message: string }
  | { status: 'progress'; recovered: number; total: number }
  | { status: 'done'; recovered: number; total: number; packed: Uint8Array }

const BASE64_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

function latin1(data: string): Uint8Array {
  const bytes = new Uint8Array(data.length)
  for (let index = 0; index < data.length; index += 1) {
    const code = data.charCodeAt(index)
    if (code > 0xff) throw new Error('barcode text is not byte data')
    bytes[index] = code
  }
  return bytes
}

function bytesFromBase64(value: string): Uint8Array {
  const cleaned = value.replace(/[\r\n]/g, '')
  const padding = cleaned.endsWith('==') ? 2 : cleaned.endsWith('=') ? 1 : 0
  const body = cleaned.slice(0, cleaned.length - padding)
  if (!cleaned || cleaned.length % 4 !== 0 || body.includes('=') || /[^A-Za-z0-9+/=]/.test(cleaned)) {
    throw new Error('barcode text is not byte data')
  }
  const length = (cleaned.length / 4) * 3 - padding
  const bytes = new Uint8Array(length)
  let offset = 0
  for (let index = 0; index < cleaned.length; index += 4) {
    const sextets = [0, 1, 2, 3].map((shift) => {
      const char = cleaned[index + shift] ?? ''
      return char === '=' ? 0 : BASE64_ALPHABET.indexOf(char)
    })
    if (sextets.some((sextet) => sextet < 0)) throw new Error('barcode text is not byte data')
    const chunk = ((sextets[0] ?? 0) << 18) | ((sextets[1] ?? 0) << 12) | ((sextets[2] ?? 0) << 6) | (sextets[3] ?? 0)
    bytes[offset] = (chunk >> 16) & 0xff
    if (offset + 1 < length) bytes[offset + 1] = (chunk >> 8) & 0xff
    if (offset + 2 < length) bytes[offset + 2] = chunk & 0xff
    offset += 3
  }
  return bytes
}

export function bytesFromBarcode(scan: BarcodeScan | string): Uint8Array {
  if (typeof scan !== 'string') {
    if (typeof scan.rawBytesBase64 === 'string' && scan.rawBytesBase64.length > 0) {
      return bytesFromBase64(scan.rawBytesBase64)
    }
    if (typeof scan.data !== 'string') throw new Error('barcode text is not byte data')
    return latin1(scan.data)
  }
  return latin1(scan)
}

export function handleBarcodeScan(collector: FrameCollector, scan: BarcodeScan): BarcodeScanOutcome {
  let bytes: Uint8Array
  try {
    bytes = bytesFromBarcode(scan)
  } catch {
    return { status: 'ignore' }
  }

  let packed: Uint8Array | undefined
  try {
    packed = collector.add(parseFrame(bytes))
  } catch (problem) {
    const message = messageForFrameError(problem)
    return message ? { status: 'error', message } : { status: 'drop' }
  }

  const { recovered, total } = collector.progress
  if (!packed) return { status: 'progress', recovered, total }
  return { status: 'done', recovered, total, packed }
}
