import type { OpticalFile } from './unpack'

/** Only generated, escaped report HTML reaches the native PDF renderer. */
export async function shareReportPdf(html: OpticalFile, output: {
  print: (html: string) => Promise<{ uri: string; numberOfPages: number }>
  read: (uri: string) => Promise<Uint8Array>
  remove: (uri: string) => void
  share: (file: OpticalFile) => Promise<void>
}): Promise<void> {
  const pdf = await output.print(new TextDecoder('utf-8', { fatal: true }).decode(html.payload))
  try {
    const payload = await output.read(pdf.uri)
    if (pdf.numberOfPages < 1 || new TextDecoder().decode(payload.subarray(0, 5)) !== '%PDF-') {
      throw new Error('PDF를 만들지 못했습니다. 앱에 저장된 리포트는 그대로 있습니다.')
    }
    await output.share({
      name: html.name.replace(/\.html$/i, '') + '.pdf',
      mediaType: 'application/pdf',
      payload,
    })
  } finally {
    output.remove(pdf.uri)
  }
}
