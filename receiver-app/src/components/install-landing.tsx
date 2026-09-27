import { Camera, Download, Settings, ShieldCheck, Smartphone, WifiOff } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { androidApkPath } from '@/lib/android-apk'

const features = [
  {
    icon: Settings,
    title: '카메라 허용이 이 앱에 있습니다',
    body: '카메라 시작을 누르면 허용 창이 뜹니다. 이미 거절했다면 설정 열기가 이 앱의 시스템 설정으로 이동합니다.',
  },
  {
    icon: WifiOff,
    title: '설치한 뒤에는 오프라인',
    body: '앱을 연 뒤에는 네트워크 없이 DashPi 화면의 QR을 읽을 수 있습니다.',
  },
  {
    icon: ShieldCheck,
    title: '검증된 파일만 저장',
    body: 'SHA-256 확인을 통과한 리포트만 이 기기에 남습니다. 받은 파일은 기기 밖으로 나가지 않습니다.',
  },
]

const steps = [
  {
    icon: Download,
    title: '안드로이드 앱 받기',
    body: '이 페이지의 버튼으로 APK를 받습니다.',
  },
  {
    icon: Smartphone,
    title: 'DashPi 설치',
    body: '설치가 막히면 이 브라우저에서 앱 설치를 허용한 뒤 DashPi를 엽니다.',
  },
  {
    icon: Camera,
    title: 'QR을 비추기',
    body: '카메라 시작 뒤 DashPi 화면의 QR을 맞추면 리포트를 받습니다.',
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
      ? '홈 화면에 설치를 누르면 공유 창이 열립니다. 홈 화면에 추가를 선택하세요.'
      : '홈 화면에 설치를 누르면 브라우저 설치 창이 열립니다.'

  const apkHref = androidApkPath(import.meta.env?.BASE_URL)
  const installApk = () => (
    <Button asChild className="w-full sm:w-auto" size="lg">
      <a href={apkHref} download="DashPi.apk">
        <Download />
        안드로이드 앱 받기
      </a>
    </Button>
  )

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-5xl flex-col gap-16 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[max(3rem,env(safe-area-inset-bottom))] md:gap-24 md:pt-16">
      <header className="flex flex-col items-start gap-6 md:items-center md:text-center">
        <Badge variant="outline">DashPi 수신 · Android</Badge>
        <div className="flex max-w-2xl flex-col gap-4">
          <h1 className="font-heading text-4xl font-semibold tracking-tight md:text-5xl">
            사고 리포트를
            <br />
            휴대폰으로 받으세요
          </h1>
          <p className="text-muted-foreground text-base leading-7 text-balance">
            DashPi 화면의 QR을 안드로이드 앱이 읽습니다. 앱을 설치하면 카메라 허용 창과 설정 열기가 DashPi에서 열립니다.
          </p>
        </div>
        <div className="flex w-full max-w-md flex-col gap-3 sm:max-w-none sm:flex-row sm:justify-center">
          {installApk()}
          <Button className="w-full sm:w-auto" size="lg" variant="outline" onClick={onOpenInBrowser}>
            <Camera />
            브라우저에서 카메라 열기
          </Button>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-3" aria-labelledby="features-title">
        <h2 id="features-title" className="sr-only">
          이 앱이 하는 일
        </h2>
        {features.map((feature) => (
          <Card key={feature.title}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <feature.icon />
                {feature.title}
              </CardTitle>
              <CardDescription className="leading-6 text-balance">{feature.body}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      <section className="flex flex-col gap-6" aria-labelledby="steps-title">
        <div className="flex max-w-2xl flex-col gap-2 md:mx-auto md:text-center">
          <h2 id="steps-title" className="font-heading text-2xl font-semibold tracking-tight">
            안드로이드에 설치하는 순서
          </h2>
          <p className="text-muted-foreground text-sm leading-6">세 단계면 이 폰에서 리포트를 받을 수 있습니다.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          {steps.map((step, index) => (
            <Card key={step.title}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Badge variant="outline">{index + 1}</Badge>
                  <step.icon />
                  {step.title}
                </CardTitle>
                <CardDescription className="leading-6 text-balance">{step.body}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
        <Alert>
          <Smartphone />
          <AlertTitle>안드로이드용 설치 파일입니다</AlertTitle>
          <AlertDescription>
            설치가 막히면 Chrome에서 이 사이트의 앱 설치를 허용하세요. 아이폰은 APK를 설치할 수 없고, 아래 홈 화면 설치로 수신기를 엽니다.
          </AlertDescription>
        </Alert>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>홈 화면 수신기</CardTitle>
          <CardDescription className="leading-6">{hint}</CardDescription>
        </CardHeader>
        {!accepted && (
          <CardFooter>
            <Button variant="outline" onClick={download}>
              <Download />
              홈 화면에 설치
            </Button>
          </CardFooter>
        )}
      </Card>

      <Card className="md:text-center">
        <CardHeader className="md:items-center">
          <CardTitle className="text-xl">이 폰에 DashPi를 설치하세요</CardTitle>
          <CardDescription className="max-w-xl leading-6">
            안드로이드 앱을 받으면 카메라 권한과 설정 열기를 DashPi 앱에서 바로 할 수 있습니다.
          </CardDescription>
        </CardHeader>
        <CardFooter className="md:justify-center">{installApk()}</CardFooter>
      </Card>
    </main>
  )
}
