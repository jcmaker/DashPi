import random
from pathlib import Path

import pytest

import dashpi.optical.session as session_module
from dashpi.optical.container import MAX_PAYLOAD
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession


def test_session_repeats_sequence_exactly(tmp_path):
    path = tmp_path / "report.html"
    path.write_bytes(b"report")

    session = OpticalSession.from_file(path, "text/html", block_size=64, session_id=7)

    assert session.frame(10) == session.frame(10)
    assert parse_frame(session.frame(10)).session_id == 7


def test_session_from_file_matches_bytes_source(tmp_path):
    path = tmp_path / "report.html"
    payload = b"report"
    path.write_bytes(payload)

    from_file = OpticalSession.from_file(path, "text/html", block_size=64, session_id=7)
    from_bytes = OpticalSession.from_bytes(
        path.name, payload, "text/html", block_size=64, session_id=7
    )

    assert from_file.frame(10) == from_bytes.frame(10)


@pytest.mark.parametrize("sequence", [-1, 2**32, True])
def test_session_rejects_sequences_outside_frame_domain(tmp_path, sequence):
    path = tmp_path / "report.html"
    path.write_bytes(b"report")
    session = OpticalSession.from_file(path, "text/html", block_size=64, session_id=7)

    with pytest.raises(ValueError):
        session.frame(sequence)


def test_session_from_file_reads_at_most_the_payload_cap(tmp_path, monkeypatch):
    path = tmp_path / "report.html"
    path.write_bytes(b"x" * (MAX_PAYLOAD + 1))
    reads = []
    real_open = Path.open

    class Reader:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            self.source.__enter__()
            return self

        def __exit__(self, *args):
            return self.source.__exit__(*args)

        def read(self, size=-1):
            reads.append(size)
            return self.source.read(size)

    def open_with_recorded_reads(self, *args, **kwargs):
        return Reader(real_open(self, *args, **kwargs))

    monkeypatch.setattr(Path, "open", open_with_recorded_reads)

    with pytest.raises(ValueError, match="16 MiB"):
        OpticalSession.from_file(path, "text/html", block_size=512, session_id=7)

    assert reads == [MAX_PAYLOAD + 1]


def test_session_rejects_excessive_block_count_before_creating_encoder(monkeypatch):
    payload = random.Random(7).randbytes(65536)

    def encoder_must_not_be_created(*args):
        raise AssertionError("constructed fountain encoder before validating block count")

    monkeypatch.setattr(session_module, "FountainEncoder", encoder_must_not_be_created)

    with pytest.raises(ValueError, match="block count"):
        OpticalSession.from_bytes("report.html", payload, "text/html", block_size=1, session_id=7)
