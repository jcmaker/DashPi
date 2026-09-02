from dataclasses import dataclass
from pathlib import Path

from dashpi.optical.container import pack_container
from dashpi.optical.fountain import FountainEncoder
from dashpi.optical.protocol import OpticalFrame, pack_frame


@dataclass
class OpticalSession:
    session_id: int
    encoder: FountainEncoder
    total_length: int

    @classmethod
    def from_file(
        cls, path: Path, media_type: str, block_size: int, session_id: int
    ) -> "OpticalSession":
        return cls.from_bytes(path.name, path.read_bytes(), media_type, block_size, session_id)

    @classmethod
    def from_bytes(
        cls, name: str, payload: bytes, media_type: str, block_size: int, session_id: int
    ) -> "OpticalSession":
        if type(session_id) is not int or not 0 <= session_id < 2**32:
            raise ValueError("invalid optical session id")
        if type(block_size) is not int or not 1 <= block_size < 2**16:
            raise ValueError("invalid optical block size")
        packed = pack_container(name, media_type, payload)
        encoder = FountainEncoder(packed, block_size, session_id)
        if not 1 <= encoder.block_count < 2**16:
            raise ValueError("invalid optical block count")
        return cls(session_id, encoder, len(packed))

    def frame(self, sequence: int) -> bytes:
        if type(sequence) is not int or not 0 <= sequence < 2**32:
            raise ValueError("invalid optical sequence")
        indices, symbol = self.encoder.symbol(sequence)
        return pack_frame(
            OpticalFrame(
                self.session_id,
                sequence,
                self.encoder.block_count,
                self.encoder.block_size,
                self.total_length,
                indices,
                symbol,
            )
        )
