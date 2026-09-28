import * as Crypto from 'expo-crypto'
import { inflateBounded } from './inflate-bounded'
import { unpackOpticalContainer, type OpticalFile } from './unpack'

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
