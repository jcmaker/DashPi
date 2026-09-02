import { BrowserQRCodeReader, type IScannerControls } from '@zxing/browser';
import { FountainDecoder } from './optical/fountain.ts';
import { parseFrame, type OpticalFrame } from './optical/protocol.ts';
import { unpackContainer } from './optical/container.ts';

export function messageForFrameError(problem: unknown): string | undefined {
  return String(problem).includes('unsupported protocol')
    ? '이 송신 형식을 읽으려면 수신기를 업데이트하세요.'
    : undefined;
}

export class FrameCollector {
  private decoder: FountainDecoder | undefined;
  private currentIdentity = '';

  get identity(): string { return this.currentIdentity; }

  add(frame: OpticalFrame): Uint8Array | undefined {
    const identity = `${frame.sessionId}:${frame.blockCount}:${frame.blockSize}:${frame.totalLength}`;
    if (identity !== this.currentIdentity) {
      this.currentIdentity = identity;
      this.decoder = new FountainDecoder(frame.blockCount, frame.blockSize, frame.totalLength);
    }
    this.decoder!.add(frame);
    return this.decoder!.result();
  }
}

if (typeof document !== 'undefined') {
  const reader = new BrowserQRCodeReader();
  const collector = new FrameCollector();
  const camera = document.querySelector<HTMLVideoElement>('#camera')!;
  const startButton = document.querySelector<HTMLButtonElement>('#start-camera')!;
  const stopButton = document.querySelector<HTMLButtonElement>('#stop-camera')!;
  const status = document.querySelector<HTMLElement>('#receiver-status')!;
  const resultPanel = document.querySelector<HTMLElement>('#verified-result')!;
  const resultName = document.querySelector<HTMLElement>('#verified-name')!;
  const reportPreview = document.querySelector<HTMLIFrameElement>('#preview-report')!;
  const videoPreview = document.querySelector<HTMLVideoElement>('#preview-video')!;
  const save = document.querySelector<HTMLAnchorElement>('#save')!;
  let controls: IScannerControls | undefined;
  let generation = 0;
  let completedIdentity = '';
  let objectUrl: string | undefined;

  const showStatus = (text: string, tone?: string) => {
    status.textContent = text;
    if (tone) status.dataset.tone = tone;
    else delete status.dataset.tone;
  };

  const clearVerifiedFile = () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = undefined;
    save.removeAttribute('href');
    save.removeAttribute('download');
    save.hidden = true;
    reportPreview.removeAttribute('src');
    reportPreview.hidden = true;
    videoPreview.removeAttribute('src');
    videoPreview.load();
    videoPreview.hidden = true;
    resultPanel.hidden = true;
  };

  const stopCamera = (announce = true) => {
    generation += 1;
    controls?.stop();
    controls = undefined;
    startButton.disabled = false;
    stopButton.disabled = true;
    if (announce) showStatus('카메라를 중지했습니다. 검증된 파일은 이 기기에만 남아 있습니다.');
  };

  const handleFrame = (raw: Uint8Array) => {
    try {
      const previousIdentity = collector.identity;
      const packed = collector.add(parseFrame(raw));
      if (collector.identity !== previousIdentity) {
        completedIdentity = '';
        clearVerifiedFile();
        showStatus('DashPi 전송을 찾았습니다. QR 프레임을 계속 비추세요.');
      }
      if (!packed || completedIdentity === collector.identity) return;
      completedIdentity = collector.identity;
      const verifiedIdentity = collector.identity;
      void unpackContainer(packed)
        .then((file) => {
          if (collector.identity !== verifiedIdentity) return;
          const payload = new Uint8Array(file.payload.length);
          payload.set(file.payload);
          objectUrl = URL.createObjectURL(new Blob([payload], { type: file.mediaType }));
          save.href = objectUrl;
          save.download = file.name;
          save.hidden = false;
          resultName.textContent = file.name;
          resultPanel.hidden = false;
          if (file.mediaType === 'text/html') {
            reportPreview.src = objectUrl;
            reportPreview.hidden = false;
          } else if (file.mediaType.startsWith('video/')) {
            videoPreview.src = objectUrl;
            videoPreview.hidden = false;
          }
          showStatus(`SHA-256 검증 완료: ${file.name}`);
        })
        .catch(() => showStatus('파일 무결성 검증에 실패했습니다. 저장할 수 없습니다.', 'error'));
    } catch (problem) {
      const message = messageForFrameError(problem);
      if (message) showStatus(message, 'error');
    }
  };

  startButton.addEventListener('click', () => {
    const runId = ++generation;
    startButton.disabled = true;
    stopButton.disabled = false;
    showStatus('카메라 권한을 확인하고 있습니다.');
    void reader.decodeFromVideoDevice(undefined, camera, (result) => {
      if (result) handleFrame(Uint8Array.from(result.getRawBytes()));
    }).then((scannerControls) => {
      if (generation !== runId) {
        scannerControls.stop();
        return;
      }
      controls = scannerControls;
      showStatus('카메라가 켜졌습니다. DashPi QR 화면을 비추세요.');
    }).catch(() => {
      if (generation !== runId) return;
      stopCamera(false);
      showStatus('카메라를 시작하지 못했습니다. 권한과 보안 연결을 확인하세요.', 'error');
    });
  });

  stopButton.addEventListener('click', () => stopCamera());
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopCamera(); });
  window.addEventListener('pagehide', () => {
    stopCamera(false);
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  });
}
