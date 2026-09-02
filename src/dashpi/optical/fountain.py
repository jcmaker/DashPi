import random


MAX_UNRESOLVED_EQUATIONS = 1024


def xor_into(target: bytearray, source: bytes) -> None:
    for index, value in enumerate(source):
        target[index] ^= value


def split_blocks(data: bytes, block_size: int) -> list[bytes]:
    return [
        data[offset : offset + block_size].ljust(block_size, b"\0")
        for offset in range(0, len(data), block_size)
    ]


class FountainEncoder:
    def __init__(self, data: bytes, block_size: int, seed: int):
        self.data = data
        self.block_size = block_size
        self.seed = seed
        self.blocks = split_blocks(data, block_size)
        self.block_count = len(self.blocks)

    def symbol(self, sequence: int) -> tuple[tuple[int, ...], bytes]:
        if sequence < self.block_count:
            indices = (sequence,)
        else:
            rng = random.Random((self.seed << 32) | sequence)
            # ponytail: fixed repair degree favors reliable MVP recovery; use robust-soliton tuning when measured overhead matters.
            degree = min(self.block_count, 10)
            indices = tuple(sorted(rng.sample(range(self.block_count), degree)))
        symbol = bytearray(self.block_size)
        for index in indices:
            xor_into(symbol, self.blocks[index])
        return indices, bytes(symbol)


class FountainDecoder:
    def __init__(self, block_count: int, block_size: int, total_length: int):
        if (
            any(type(value) is not int for value in (block_count, block_size, total_length))
            or not 1 <= block_count < 2**16
            or not 1 <= block_size < 2**16
            or not (block_count - 1) * block_size < total_length <= block_count * block_size
            or total_length >= 2**32
        ):
            raise ValueError("invalid fountain geometry")
        self.block_count = block_count
        self.block_size = block_size
        self.total_length = total_length
        self.blocks: dict[int, bytes] = {}
        self.equations: list[tuple[set[int], bytearray]] = []

    def add(self, indices: tuple[int, ...], symbol: bytes) -> None:
        if (
            type(indices) is not tuple
            or not indices
            or any(type(index) is not int for index in indices)
            or len(set(indices)) != len(indices)
            or any(index < 0 or index >= self.block_count for index in indices)
            or type(symbol) is not bytes
            or len(symbol) != self.block_size
        ):
            raise ValueError("invalid fountain equation")
        unknown = set(indices)
        value = bytearray(symbol)
        for index in tuple(unknown & self.blocks.keys()):
            xor_into(value, self.blocks[index])
            unknown.remove(index)
        if not unknown:
            if any(value):
                raise ValueError("conflicting fountain equation")
            return
        if unknown and not self._has_equation(unknown, value):
            if len(self.equations) < MAX_UNRESOLVED_EQUATIONS:
                self.equations.append((unknown, value))
        self._peel()

    def _has_equation(self, unknown: set[int], value: bytearray) -> bool:
        for equation_indices, equation_value in self.equations:
            if unknown != equation_indices:
                continue
            if value != equation_value:
                raise ValueError("conflicting fountain equation")
            return True
        return False

    def _peel(self) -> None:
        while True:
            singleton = next(
                (
                    (next(iter(indices)), value)
                    for indices, value in self.equations
                    if len(indices) == 1
                ),
                None,
            )
            if singleton is None:
                break
            index, value = singleton
            resolved = bytes(value)
            self.blocks[index] = resolved
            remaining: list[tuple[set[int], bytearray]] = []
            seen: dict[frozenset[int], bytes] = {}
            for indices, equation_value in self.equations:
                if index in indices:
                    xor_into(equation_value, resolved)
                    indices.remove(index)
                if not indices:
                    continue
                key = frozenset(indices)
                value = bytes(equation_value)
                if key in seen:
                    if seen[key] != value:
                        raise ValueError("conflicting fountain equation")
                    continue
                seen[key] = value
                remaining.append((indices, equation_value))
            self.equations = remaining

    def result(self) -> bytes | None:
        if len(self.blocks) != self.block_count:
            return None
        return b"".join(self.blocks[index] for index in range(self.block_count))[ : self.total_length]
