import random

import pytest

from dashpi.optical.fountain import FountainDecoder, FountainEncoder


def test_systematic_symbols_recover_in_any_order():
    payload = bytes(range(251)) * 20
    encoder = FountainEncoder(payload, block_size=256, seed=7)
    symbols = [encoder.symbol(sequence) for sequence in range(encoder.block_count)]
    decoder = FountainDecoder(encoder.block_count, encoder.block_size, len(payload))

    for indices, data in reversed(symbols):
        decoder.add(indices, data)

    assert decoder.result() == payload


def test_one_megabyte_survives_loss_duplicates_and_reordering():
    payload = random.Random(9).randbytes(1024 * 1024)
    encoder = FountainEncoder(payload, block_size=1024, seed=11)
    frames = [encoder.symbol(sequence) for sequence in range(encoder.block_count * 2)]
    kept = [frame for index, frame in enumerate(frames) if index % 20 not in {1, 7, 13}]
    kept += kept[:20]
    random.Random(5).shuffle(kept)
    decoder = FountainDecoder(encoder.block_count, encoder.block_size, len(payload))

    for indices, data in kept:
        decoder.add(indices, data)
        if decoder.result() is not None:
            break

    assert decoder.result() == payload


@pytest.mark.parametrize(
    "geometry",
    [
        (0, 4, 1),
        (2, 0, 1),
        (2, 4, 4),
        (2, 4, 9),
        (True, 4, 1),
        (2, 4, True),
    ],
)
def test_decoder_rejects_invalid_geometry(geometry):
    with pytest.raises(ValueError):
        FountainDecoder(*geometry)


@pytest.mark.parametrize(
    ("indices", "symbol"),
    [
        ((), b"abcd"),
        ((0, 0), b"abcd"),
        ((-1,), b"abcd"),
        ((2,), b"abcd"),
        ((True,), b"abcd"),
        (("0",), b"abcd"),
        ((0,), b"abc"),
        ((0,), b"abcde"),
        ((0,), bytearray(b"abcd")),
    ],
)
def test_decoder_rejects_malformed_equations_before_mutation(indices, symbol):
    decoder = FountainDecoder(2, 4, 8)

    with pytest.raises(ValueError):
        decoder.add(indices, symbol)

    assert decoder.blocks == {}
    assert decoder.equations == []


def test_decoder_deduplicates_unresolved_equations():
    decoder = FountainDecoder(2, 4, 8)
    decoder.add((0, 1), b"abcd")
    decoder.add((0, 1), b"abcd")

    assert len(decoder.equations) == 1


def test_decoder_prunes_equations_after_resolving_them():
    decoder = FountainDecoder(2, 4, 8)
    decoder.add((0, 1), b"abcd")
    decoder.add((0,), b"wxyz")

    assert decoder.equations == []


def test_decoder_caps_retained_unresolved_equations():
    decoder = FountainDecoder(2, 4, 8)

    for value in range(1025):
        decoder.add((0, 1), value.to_bytes(4, "little"))

    assert len(decoder.equations) <= 1024
