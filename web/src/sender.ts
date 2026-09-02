import QRCode from 'qrcode';

export function updateStatus(
  target: { textContent: string | null; dataset: { tone?: string } },
  text: string,
  tone?: string,
): void {
  target.textContent = text;
  if (tone) target.dataset.tone = tone;
  else delete target.dataset.tone;
}

export async function resolveWhileCurrent<T>(
  pending: Promise<T>,
  isCurrent: () => boolean,
  discard?: (value: T) => void | Promise<void>,
): Promise<T | undefined> {
  const value = await pending;
  if (isCurrent()) return value;
  await discard?.(value);
  return undefined;
}

export async function runFrameLoop(
  renderFrame: () => Promise<void>,
  shouldContinue: () => boolean,
  wait: () => Promise<void>,
): Promise<void> {
  while (shouldContinue()) {
    await renderFrame();
    if (shouldContinue()) await wait();
  }
}

if (typeof document !== 'undefined') {
  const canvas = document.querySelector<HTMLCanvasElement>('canvas')!;
  const placeholder = document.querySelector<HTMLElement>('#canvas-placeholder')!;
  const warning = document.querySelector<HTMLInputElement>('#warning')!;
  const startButton = document.querySelector<HTMLButtonElement>('#start')!;
  const stopButton = document.querySelector<HTMLButtonElement>('#stop')!;
  const sequenceLabel = document.querySelector<HTMLOutputElement>('#sequence')!;
  const scale = document.querySelector<HTMLInputElement>('#scale')!;
  const scaleValue = document.querySelector<HTMLOutputElement>('#scale-value')!;
  const status = document.querySelector<HTMLElement>('#sender-status')!;
  let generation = 0;
  let sequence = 0;
  let wakeLock: WakeLockSentinel | undefined;

  const stop = (announce = true) => {
    generation += 1;
    void wakeLock?.release();
    wakeLock = undefined;
    startButton.disabled = !warning.checked;
    startButton.textContent = '전송 시작';
    delete startButton.dataset.state;
    stopButton.disabled = true;
    canvas.getContext('2d')?.clearRect(0, 0, canvas.width, canvas.height);
    canvas.hidden = true;
    placeholder.hidden = false;
    if (announce) updateStatus(status, '전송을 중지하고 화면의 QR을 지웠습니다.');
  };

  warning.addEventListener('change', () => {
    startButton.disabled = !warning.checked;
    updateStatus(status, warning.checked
      ? '보정값을 확인한 뒤 전송을 시작하세요.'
      : '경고를 확인하면 전송을 시작할 수 있습니다.');
  });

  scale.addEventListener('input', () => { scaleValue.value = scale.value; });

  startButton.addEventListener('click', () => {
    void (async () => {
      const incidentId = new URL(location.href).searchParams.get('incident');
      if (!warning.checked) return;
      if (!incidentId) throw new Error('전송할 incident 쿼리 값이 없습니다.');

      stop(false);
      const runId = ++generation;
      startButton.disabled = true;
      stopButton.disabled = false;
      startButton.dataset.state = 'loading';
      startButton.textContent = '세션 준비 중…';
      updateStatus(status, '광학 전송 세션을 준비하고 있습니다.');

      const blockSize = Number(document.querySelector<HTMLSelectElement>('#bytes')!.value);
      const fps = Number(document.querySelector<HTMLSelectElement>('#fps')!.value);
      const artifact = document.querySelector<HTMLSelectElement>('#artifact')!.value;
      const created = await resolveWhileCurrent(
        fetch(`/api/incidents/${encodeURIComponent(incidentId)}/optical`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artifact, block_size: blockSize }),
        }),
        () => generation === runId,
      );
      if (!created) return;
      if (!created.ok) throw new Error(`세션 생성 실패 (${created.status})`);

      const { session_id: sessionId } = await created.json() as { session_id: number };
      sequence = 0;
      sequenceLabel.value = '0';
      stopButton.disabled = false;
      startButton.dataset.state = 'success';
      startButton.textContent = '전송 중';
      updateStatus(status, 'QR 프레임을 전송 중입니다. 화면이 보이는 범위를 통제하세요.');
      try {
        wakeLock = await resolveWhileCurrent(
          Promise.resolve(navigator.wakeLock?.request('screen')),
          () => generation === runId,
          (lock) => lock?.release(),
        );
      } catch { wakeLock = undefined; }

      await runFrameLoop(async () => {
        const response = await fetch(`/api/optical/${sessionId}/frames/${sequence}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`프레임 요청 실패 (${response.status})`);
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (generation !== runId) return;
        await QRCode.toCanvas(canvas, [{ data: bytes, mode: 'byte' }], {
          errorCorrectionLevel: 'L',
          margin: 1,
          scale: Number(scale.value),
        });
        if (generation !== runId) return;
        sequence += 1;
        sequenceLabel.value = String(sequence);
        canvas.hidden = false;
        placeholder.hidden = true;
      }, () => generation === runId, () => new Promise((resolve) => window.setTimeout(resolve, 1000 / fps)));
    })().catch((error: unknown) => {
      stop(false);
      startButton.dataset.state = 'error';
      updateStatus(
        status,
        error instanceof Error ? error.message : '광학 전송을 시작하지 못했습니다.',
        'error',
      );
    });
  });

  stopButton.addEventListener('click', () => stop());
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
}
