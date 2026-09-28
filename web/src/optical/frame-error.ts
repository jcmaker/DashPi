export function messageForFrameError(problem: unknown): string | undefined {
  const text = String(problem);
  if (text.includes('unsupported protocol')) {
    return '이 송신 형식을 읽으려면 수신기를 업데이트하세요.';
  }
  if (text.includes('conflicting equation')) {
    return '수신한 QR이 서로 맞지 않습니다. 새로 받으세요.';
  }
  return undefined;
}
