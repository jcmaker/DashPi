// Expo Camera returns QR byte mode as a string of character codes, not a Uint8Array.
export function bytesFromBarcode(data: string): Uint8Array {
  const bytes = new Uint8Array(data.length)
  for (let index = 0; index < data.length; index += 1) {
    const code = data.charCodeAt(index)
    if (code > 0xff) throw new Error('barcode text is not byte data')
    bytes[index] = code
  }
  return bytes
}
