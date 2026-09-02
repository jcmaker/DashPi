import type { OpticalFrame } from './protocol.ts';

type Equation = { indices: Set<number>; value: Uint8Array };

function xorInto(target: Uint8Array, source: Uint8Array): void {
  for (let index = 0; index < target.length; index += 1) target[index] ^= source[index];
}

function isGeometry(blockCount: unknown, blockSize: unknown, totalLength: unknown): boolean {
  return (
    Number.isInteger(blockCount) &&
    Number.isInteger(blockSize) &&
    Number.isInteger(totalLength) &&
    (blockCount as number) > 0 &&
    (blockCount as number) <= 0xffff &&
    (blockSize as number) > 0 &&
    (blockSize as number) <= 0xffff &&
    (totalLength as number) > ((blockCount as number) - 1) * (blockSize as number) &&
    (totalLength as number) <= (blockCount as number) * (blockSize as number)
  );
}

function equationKey(indices: Set<number>): string {
  return [...indices].sort((left, right) => left - right).join(',');
}

function sameBytes(left: Uint8Array, right: Uint8Array): boolean {
  return left.length === right.length && left.every((byte, index) => byte === right[index]);
}

function isZero(bytes: Uint8Array): boolean {
  return bytes.every((byte) => byte === 0);
}

export class FountainDecoder {
  private readonly blocks = new Map<number, Uint8Array>();
  private equations: Equation[] = [];

  constructor(
    private readonly blockCount: number,
    private readonly blockSize: number,
    private readonly totalLength: number,
  ) {
    if (!isGeometry(blockCount, blockSize, totalLength)) throw new Error('malformed stream');
  }

  add(frame: OpticalFrame): void {
    if (
      !frame ||
      frame.blockCount !== this.blockCount ||
      frame.blockSize !== this.blockSize ||
      frame.totalLength !== this.totalLength
    ) {
      throw new Error('stream changed');
    }
    if (
      !Number.isInteger(frame.sessionId) ||
      frame.sessionId < 0 ||
      frame.sessionId >= 2 ** 32 ||
      !Number.isInteger(frame.sequence) ||
      frame.sequence < 0 ||
      frame.sequence >= 2 ** 32 ||
      !Array.isArray(frame.indices) ||
      frame.indices.length === 0 ||
      frame.indices.length > Math.min(255, this.blockCount) ||
      new Set(frame.indices).size !== frame.indices.length ||
      frame.indices.some((index) => !Number.isInteger(index) || index < 0 || index >= this.blockCount) ||
      !(frame.symbol instanceof Uint8Array) ||
      frame.symbol.length !== this.blockSize
    ) {
      throw new Error('malformed frame');
    }

    const indices = new Set(frame.indices);
    const value = frame.symbol.slice();
    for (const index of indices) {
      const block = this.blocks.get(index);
      if (block) {
        xorInto(value, block);
        indices.delete(index);
      }
    }
    if (indices.size === 0) {
      if (!isZero(value)) throw new Error('conflicting equation');
      return;
    }

    this.store({ indices, value });
    this.peel();
  }

  result(): Uint8Array | undefined {
    if (this.blocks.size !== this.blockCount) return undefined;

    const output = new Uint8Array(this.blockCount * this.blockSize);
    for (let index = 0; index < this.blockCount; index += 1) {
      output.set(this.blocks.get(index)!, index * this.blockSize);
    }
    return output.slice(0, this.totalLength);
  }

  private store(equation: Equation): void {
    const key = equationKey(equation.indices);
    const existing = this.equations.find((candidate) => equationKey(candidate.indices) === key);
    if (existing) {
      if (!sameBytes(existing.value, equation.value)) throw new Error('conflicting equation');
      return;
    }
    if (this.equations.length < 1024) this.equations.push(equation);
  }

  private peel(): void {
    for (;;) {
      const position = this.equations.findIndex((equation) => equation.indices.size === 1);
      if (position < 0) return;

      const [equation] = this.equations.splice(position, 1);
      const index = equation.indices.values().next().value as number;
      const known = this.blocks.get(index);
      if (known) {
        if (!sameBytes(known, equation.value)) throw new Error('conflicting equation');
        continue;
      }
      this.blocks.set(index, equation.value.slice());
      for (const other of this.equations) {
        if (other.indices.delete(index)) xorInto(other.value, equation.value);
      }
      this.removeResolvedAndDeduplicate();
    }
  }

  private removeResolvedAndDeduplicate(): void {
    const unique = new Map<string, Equation>();
    for (const equation of this.equations) {
      if (equation.indices.size === 0) {
        if (!isZero(equation.value)) throw new Error('conflicting equation');
        continue;
      }
      const key = equationKey(equation.indices);
      const existing = unique.get(key);
      if (existing && !sameBytes(existing.value, equation.value)) {
        throw new Error('conflicting equation');
      }
      unique.set(key, existing ?? equation);
    }
    this.equations = [...unique.values()];
  }
}
