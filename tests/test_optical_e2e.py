import hashlib
import random

from dashpi.optical.container import unpack_container
from dashpi.optical.fountain import FountainDecoder
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession


PAYLOAD_SHA256 = "b667fe504328bfe900fb280750b938db0da1848d573db2f7534afcde0ef17a88"


def test_one_megabyte_survives_frame_loss_duplicates_and_reordering():
    payload = random.Random(9).randbytes(1024 * 1024)
    session = OpticalSession.from_bytes(
        "source.bin", payload, "application/octet-stream", 1024, 11
    )
    frames = [
        session.frame(sequence)
        for sequence in range(session.encoder.block_count * 2)
        if sequence % 20 not in {1, 7, 13}
    ]
    frames += frames[:20]
    random.Random(5).shuffle(frames)

    first = parse_frame(frames[0])
    decoder = FountainDecoder(first.block_count, first.block_size, first.total_length)
    for wire in frames:
        frame = parse_frame(wire)
        decoder.add(frame.indices, frame.symbol)
        if decoder.result() is not None:
            break

    packed = decoder.result()
    assert packed is not None
    recovered = unpack_container(packed)
    assert len(recovered.payload) == 1024 * 1024
    assert hashlib.sha256(recovered.payload).hexdigest() == PAYLOAD_SHA256
