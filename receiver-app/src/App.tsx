import { useRef } from 'react'
import {
  Camera,
  CameraOff,
  CircleAlert,
  Download,
  RotateCcw,
  Share2,
  ShieldCheck,
  Smartphone,
  WifiOff,
} from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { useInstallPrompt } from '@/hooks/use-install-prompt'
import { useOpticalReceiver, type ReceiverState, type VerifiedFile } from '@/hooks/use-optical-receiver'

const statusText: Record<ReceiverState['phase'], string> = {
  idle: '카메라를 시작하면 DashPi 화면의 QR을 읽습니다.',
  starting: '카메라 권한을 확인하고 있습니다.',
  scanning: 'DashPi QR 화면을 카메라 안에 맞추세요.',
  receiving: '수신 중입니다. 화면을 계속 비추세요.',
  verifying: 'SHA-256 무결성을 검증하고 있습니다.',
  verified: '검증이 끝났습니다.',
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function InstallScreen({
  accepted,
  canPrompt,
  isIos,
  install,
}: {
  accepted: boolean
  canPrompt: boolean
  isIos: boolean
  install: () => Promise<void>
}) {
  const download = () => {
    if (canPrompt) {
      void install()
      return
    }
    if (isIos && typeof navigator.share === 'function') {
      void navigator.share({ title: 'DashPi 수신', url: window.location.href }).catch(() => undefined)
    }
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col justify-center gap-4 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]">
      <header>
        <p className="text-muted-foreground text-xs">DashPi · Optical Receiver</p>
        <h1 className="font-heading text-xl font-semibold">사고 리포트 받기</h1>
      </header>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Smartphone />
            앱을 설치하세요
          </CardTitle>
          <CardDescription>
            {accepted
              ? '설치되었습니다. 브라우저를 닫고 홈 화면의 DashPi 수신을 여세요.'
              : '홈 화면에 설치한 뒤, 그 앱에서 리포트를 받으세요.'}
          </CardDescription>
        </CardHeader>
        {!accepted && (
          <CardFooter>
            <Button className="w-full" onClick={download}>
              <Download />
              다운로드
            </Button>
          </CardFooter>
        )}
      </Card>
    </main>
  )
}

function VerifiedCard({ file, onReset }: { file: VerifiedFile; onReset: () => void }) {
  const shareable =
    typeof navigator.canShare === 'function' &&
    navigator.canShare({ files: [new File([file.blob], file.name, { type: file.mediaType })] })
  const share = () =>
    void navigator
      .share({ files: [new File([file.blob], file.name, { type: file.mediaType })] })
      .catch(() => undefined)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="text-primary" />
          검증 완료
        </CardTitle>
        <CardDescription className="break-all">
          {file.name} · {formatBytes(file.size)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {file.mediaType === 'text/html' && (
          <iframe
            title="검증된 분석 리포트"
            src={file.url}
            sandbox="allow-scripts allow-downloads allow-modals"
            className="h-[70svh] w-full rounded-lg border bg-background"
          />
        )}
        {file.mediaType.startsWith('video/') && (
          <video src={file.url} controls playsInline preload="metadata" className="w-full rounded-lg" />
        )}
      </CardContent>
      <CardFooter className="flex-col gap-2">
        {shareable && (
          <Button className="w-full" onClick={share}>
            <Share2 />
            공유 또는 파일에 저장
          </Button>
        )}
        <Button asChild variant={shareable ? 'outline' : 'default'} className="w-full">
          <a href={file.url} download={file.name}>
            <Download />
            기기에 저장
          </a>
        </Button>
        <Button variant="ghost" className="w-full" onClick={onReset}>
          <RotateCcw />
          새로 받기
        </Button>
      </CardFooter>
    </Card>
  )
}

export default function App() {
  const { installed, accepted, canPrompt, isIos, install } = useInstallPrompt()
  if (!installed) return <InstallScreen accepted={accepted} canPrompt={canPrompt} isIos={isIos} install={install} />
  return <Receiver />
}

function Receiver() {
  const video = useRef<HTMLVideoElement>(null)
  const { state, start, stop, reset } = useOpticalReceiver(video)
  const cameraOn = state.phase === 'starting' || state.phase === 'scanning' || state.phase === 'receiving'
  const percent = state.total > 0 ? Math.round((state.recovered / state.total) * 100) : 0

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col gap-4 px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(1rem,env(safe-area-inset-bottom))]">
      <header className="flex items-start justify-between gap-3">
        <div>
          <p className="text-muted-foreground text-xs">DashPi · Optical Receiver</p>
          <h1 className="font-heading text-xl font-semibold">사고 리포트 받기</h1>
        </div>
        <Badge variant="outline">
          <WifiOff />
          오프라인 작동
        </Badge>
      </header>

      {state.error && (
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>수신 문제</AlertTitle>
          <AlertDescription>{state.error}</AlertDescription>
        </Alert>
      )}

      {state.phase === 'verified' && state.file ? (
        <VerifiedCard file={state.file} onReset={reset} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>카메라로 QR 읽기</CardTitle>
            <CardDescription role="status" aria-live="polite">
              {statusText[state.phase]}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="bg-muted relative aspect-square w-full overflow-hidden rounded-lg">
              <video
                ref={video}
                playsInline
                muted
                aria-label="광학 QR 스캐너 카메라"
                className={cameraOn ? 'size-full object-cover' : 'hidden'}
              />
              {!cameraOn && (
                <div className="text-muted-foreground absolute inset-0 flex items-center justify-center">
                  <Camera className="size-10" />
                </div>
              )}
            </div>
            {(state.phase === 'receiving' || state.phase === 'verifying') && (
              <div className="flex flex-col gap-1.5">
                <Progress value={percent} />
                <p className="text-muted-foreground text-xs tabular-nums">
                  {state.recovered} / {state.total} 조각 · {percent}%
                </p>
              </div>
            )}
          </CardContent>
          <CardFooter>
            {cameraOn ? (
              <Button variant="outline" className="w-full" onClick={stop}>
                <CameraOff />
                카메라 중지
              </Button>
            ) : (
              <Button className="w-full" onClick={start} disabled={state.phase === 'verifying'}>
                <Camera />
                카메라 시작
              </Button>
            )}
          </CardFooter>
        </Card>
      )}

      <p className="text-muted-foreground text-center text-xs">
        QR 프레임은 이 기기 안에서만 처리되며 어디에도 업로드되지 않습니다. 전체 길이와 SHA-256 검증을 통과한 파일만
        저장할 수 있습니다.
      </p>
    </main>
  )
}
