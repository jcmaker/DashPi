import { BrowserQRCodeReader, type IScannerControls } from '@zxing/browser'
import { ResultMetadataType } from '@zxing/library'
import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { FrameCollector, messageForFrameError, qrPayload } from '@optical/collector.ts'
import { unpackContainer } from '@optical/container.ts'
import { parseFrame } from '@optical/protocol.ts'

export type VerifiedFile = {
  name: string
  mediaType: string
  size: number
  url: string
  blob: Blob
}

export type ReceiverPhase = 'idle' | 'starting' | 'scanning' | 'receiving' | 'verifying' | 'verified'

export type ReceiverState = {
  phase: ReceiverPhase
  recovered: number
  total: number
  file?: VerifiedFile
  error?: string
}

const initialState: ReceiverState = { phase: 'idle', recovered: 0, total: 0 }

export function useOpticalReceiver(video: RefObject<HTMLVideoElement | null>) {
  const [state, setState] = useState<ReceiverState>(initialState)
  const controls = useRef<IScannerControls | undefined>(undefined)
  const collector = useRef(new FrameCollector())
  const generation = useRef(0)
  const completedIdentity = useRef('')
  const fileUrl = useRef<string | undefined>(undefined)

  const releaseFile = useCallback(() => {
    if (fileUrl.current) URL.revokeObjectURL(fileUrl.current)
    fileUrl.current = undefined
  }, [])

  const stop = useCallback(() => {
    generation.current += 1
    controls.current?.stop()
    controls.current = undefined
    setState((current) =>
      current.phase === 'verified' || current.phase === 'verifying' ? current : { ...current, phase: 'idle' },
    )
  }, [])

  const handleFrame = useCallback(
    (raw: Uint8Array) => {
      const frames = collector.current
      let packed: Uint8Array | undefined
      try {
        const previousIdentity = frames.identity
        packed = frames.add(parseFrame(raw))
        if (frames.identity !== previousIdentity) {
          completedIdentity.current = ''
          releaseFile()
        }
      } catch (problem) {
        const message = messageForFrameError(problem)
        if (message) setState((current) => ({ ...current, error: message }))
        return
      }
      const { recovered, total } = frames.progress
      if (!packed) {
        setState((current) =>
          current.phase === 'scanning' || current.phase === 'receiving'
            ? { phase: 'receiving', recovered, total }
            : current,
        )
        return
      }
      if (completedIdentity.current === frames.identity) return
      completedIdentity.current = frames.identity
      const verifiedIdentity = frames.identity
      setState({ phase: 'verifying', recovered, total })
      void unpackContainer(packed)
        .then((file) => {
          if (frames.identity !== verifiedIdentity) return
          const payload = new Uint8Array(file.payload.length)
          payload.set(file.payload)
          const blob = new Blob([payload], { type: file.mediaType })
          releaseFile()
          fileUrl.current = URL.createObjectURL(blob)
          stop()
          setState({
            phase: 'verified',
            recovered,
            total,
            file: { name: file.name, mediaType: file.mediaType, size: blob.size, url: fileUrl.current, blob },
          })
        })
        .catch(() => {
          completedIdentity.current = ''
          setState({
            phase: 'scanning',
            recovered: 0,
            total: 0,
            error: '파일 무결성 검증에 실패했습니다. 저장할 수 없습니다.',
          })
        })
    },
    [releaseFile, stop],
  )

  const start = useCallback(() => {
    const element = video.current
    if (!element) return
    const runId = ++generation.current
    collector.current = new FrameCollector()
    completedIdentity.current = ''
    releaseFile()
    setState({ phase: 'starting', recovered: 0, total: 0 })
    new BrowserQRCodeReader()
      .decodeFromConstraints({ video: { facingMode: 'environment' }, audio: false }, element, (result) => {
        const payload = qrPayload(result?.getResultMetadata()?.get(ResultMetadataType.BYTE_SEGMENTS))
        if (payload && generation.current === runId) handleFrame(payload)
      })
      .then((scannerControls) => {
        if (generation.current !== runId) {
          scannerControls.stop()
          return
        }
        controls.current = scannerControls
        setState((current) => (current.phase === 'starting' ? { ...current, phase: 'scanning' } : current))
      })
      .catch(() => {
        if (generation.current !== runId) return
        setState({
          ...initialState,
          error: '카메라를 시작하지 못했습니다. 카메라 권한을 허용했는지 확인하세요.',
        })
      })
  }, [handleFrame, releaseFile, video])

  const reset = useCallback(() => {
    stop()
    releaseFile()
    collector.current = new FrameCollector()
    completedIdentity.current = ''
    setState(initialState)
  }, [releaseFile, stop])

  useEffect(() => {
    const onHidden = () => {
      if (document.hidden) stop()
    }
    document.addEventListener('visibilitychange', onHidden)
    return () => {
      document.removeEventListener('visibilitychange', onHidden)
      generation.current += 1
      controls.current?.stop()
      releaseFile()
    }
  }, [releaseFile, stop])

  return { state, start, stop, reset }
}
