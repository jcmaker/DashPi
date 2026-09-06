import hashlib
import random
import socket

from dashpi.config import Settings
from dashpi.media import segment_source
from dashpi.models import IncidentMetadata
from dashpi.optical.container import MAX_PAYLOAD, unpack_container
from dashpi.optical.fountain import FountainDecoder
from dashpi.optical.protocol import parse_frame
from dashpi.optical.session import OpticalSession
from dashpi.pipeline import IncidentPipeline
from dashpi.storage import IncidentStore
from tests.media_factory import make_video
from tests.test_pipeline import pipeline_fixture


def test_injected_analysis_pipeline_never_opens_network(pipeline_fixture, monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    pipeline, incident, segments = pipeline_fixture

    result = pipeline.process(
        incident,
        segments,
        lambda _frames: {"incident_timestamp": 3.0, "summary": "Offline", "observations": [], "limitations": []},
    )

    assert result.state.value == "ready"


def test_incident_report_survives_existing_optical_transport_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("outbound network attempted")),
    )
    pipeline, incident, segments = deterministic_45_second_pipeline(tmp_path)
    result = pipeline.process(incident, segments, deterministic_analysis)
    payload = result.report_html.path.read_bytes()
    assert len(payload) <= MAX_PAYLOAD

    session = OpticalSession.from_bytes("report.html", payload, "text/html", 1024, 11)
    wires = [
        session.frame(n)
        for n in range(session.encoder.block_count * 2)
        if n % 20 not in {1, 7, 13}
    ]
    wires += wires[:20]
    random.Random(5).shuffle(wires)
    first = parse_frame(wires[0])
    decoder = FountainDecoder(first.block_count, first.block_size, first.total_length)
    for wire in wires:
        frame = parse_frame(wire)
        decoder.add(frame.indices, frame.symbol)
        if decoder.result() is not None:
            break
    packed = decoder.result()
    assert packed is not None
    recovered = unpack_container(packed)
    assert recovered.name == "report.html"
    assert recovered.sha256 == hashlib.sha256(payload).hexdigest()
    assert b"data:video/mp4;base64," in recovered.payload
    assert recovered.payload.count(b"data:image/jpeg;base64,") == 3


def deterministic_analysis(_frames):
    return {
        "incident_timestamp": 22.5,
        "summary": "급정지 뒤 접촉",
        "observations": [{"timestamp": 22.5, "description": "차량 접촉"}],
        "limitations": ["단일 전방 카메라"],
    }


def deterministic_45_second_pipeline(tmp_path):
    source = make_video(tmp_path / "source.mp4", 46)
    segments = segment_source(source, tmp_path / "segments", 2.0)
    settings = Settings(tmp_path / "data", "test-model", pre_seconds=30.0, post_seconds=15.0)
    incident = IncidentMetadata.new(
        "inc-e2e", "2026-09-06T00:00:00Z", 30.0, settings.post_seconds, settings.pre_seconds
    )

    def detector(_frame):
        return [{"label": "car", "confidence": 0.91, "box": [20, 20, 90, 90]}]

    return IncidentPipeline(settings, IncidentStore(settings.data_root), detector), incident, segments
