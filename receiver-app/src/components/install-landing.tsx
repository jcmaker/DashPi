import { Camera, Download, ShieldCheck, Smartphone, WifiOff } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

const steps = [
  {
    icon: Download,
    title: '홈 화면에 설치',
    body: '이 페이지의 버튼으로 수신기를 홈 화면에 추가합니다.',
  },
  {
    icon: Smartphone,
    title: '설치된 앱을 열기',
    body: '홈 화면 앱으로 열거나, 이 브라우저에서 바로 카메라를 켭니다.',
  },
  {
    icon: Camera,
    title: 'DashPi QR을 비추기',
    body: '검증이 끝난 리포트만 이 기기에 저장할 수 있습니다.',
  },
]

export function InstallLanding({
  accepted,
  canPrompt,
  isIos,
  install,
  onOpenInBrowser,
}: {
  accepted: boolean
  canPrompt: boolean
  isIos: boolean
  install: () => Promise<void>
  onOpenInBrowser: () => void
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

  const hint = accepted
    ? '설치되었습니다. 이 탭을 닫고 홈 화면의 DashPi 수신을 여세요.'
    : isIos
      ? '버튼을 누르면 공유 창이 열립니다. 홈 화면에 추가를 선택하세요.'
      : '버튼을 누르면 브라우저 설치 창이 열립니다.'

  const action = !accepted && (
    <Button className="w-full" size="lg" onClick={download}>
      <Download />
      홈 화면에 설치
    </Button>
  )

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col gap-8 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))]">
      <header className="flex flex-col gap-4">
        <p className="text-muted-foreground text-xs">DashPi 수신</p>
        <h1 className="font-heading text-3xl font-semibold tracking-tight">
          사고 리포트를
          <br />
          휴대폰으로 받으세요
        </h1>
        <p className="text-muted-foreground text-sm leading-6">
          DashPi 화면의 QR을 홈 화면 앱이 읽습니다. 인터넷 없이도 되고, 받은 파일은 이 기기 밖으로 나가지 않습니다.
        </p>
        {action}
        <Button className="w-full" size="lg" variant="outline" onClick={onOpenInBrowser}>
          <Camera />
          브라우저에서 카메라 열기
        </Button>
        <p className="text-muted-foreground text-xs leading-5">{hint}</p>
      </header>

      <section className="flex flex-col gap-3" aria-labelledby="steps-title">
        <h2 id="steps-title" className="text-sm font-medium">받는 순서</h2>
        {steps.map((step, index) => (
          <Card key={step.title} size="sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Badge variant="outline">{index + 1}</Badge>
                <step.icon />
                {step.title}
              </CardTitle>
              <CardDescription>{step.body}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="trust-title">
        <h2 id="trust-title" className="text-sm font-medium">이 앱이 지키는 것</h2>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <WifiOff />
              오프라인
            </CardTitle>
            <CardDescription>설치한 뒤에는 네트워크 없이 앱을 엽니다.</CardDescription>
          </CardHeader>
        </Card>
        <Card size="sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck />
              검증 후에만 저장
            </CardTitle>
            <CardDescription>SHA-256 확인을 통과한 파일만 저장할 수 있습니다.</CardDescription>
          </CardHeader>
        </Card>
      </section>

      {action}
    </main>
  )
}
