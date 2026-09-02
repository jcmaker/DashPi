import pytest

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
