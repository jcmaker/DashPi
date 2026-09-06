from argparse import Namespace
from types import SimpleNamespace

from dashpi.config import OverlaySettings
from dashpi.server import build_parser
import dashpi.server as server_module


def test_server_defaults_to_loopback():
    args = build_parser().parse_args(["--data-root", "/tmp/dashpi"])

    assert (args.host, args.port) == ("127.0.0.1", 8000)


def test_server_accepts_optional_analysis_models_and_overlay_flags():
    args = build_parser().parse_args(
        [
            "--data-root", "/tmp/dashpi", "--ollama-model", "vision", "--detector-model", "/tmp/yolo.pt",
            "--show-traffic-lights", "--show-lanes", "--show-traffic-signs",
        ]
    )

    assert args.ollama_model == "vision"
    assert args.detector_model.name == "yolo.pt"
    assert (args.show_traffic_lights, args.show_lanes, args.show_traffic_signs) == (True, True, True)


def test_server_wires_regeneration_through_the_single_analysis_worker(monkeypatch, tmp_path):
    args = Namespace(
        data_root=tmp_path,
        host="127.0.0.1",
        port=8000,
        ollama_model="vision",
        detector_model=tmp_path / "yolo.pt",
        show_traffic_lights=True,
        show_lanes=False,
        show_traffic_signs=True,
    )
    captured = {}

    class Client:
        def __init__(self, model):
            self.model = model

        def analyze(self, _frames):
            return {"summary": "report"}

    class Pipeline:
        def __init__(self, settings, store, detector, wait_for_capacity):
            captured["settings"] = settings
            captured["store"] = store
            captured["detector"] = detector
            captured["wait_for_capacity"] = wait_for_capacity

        def regenerate_report(self, item, analyze, offset, overlays):
            captured["report"] = (item, analyze, offset, overlays)
            return "report"

    class App:
        def on_event(self, name):
            assert name == "shutdown"

            def register(handler):
                captured["shutdown"] = handler
                return handler

            return register

    def run(_app, **_kwargs):
        try:
            future = captured["regenerate"](SimpleNamespace(incident_id="incident"), 4.0, OverlaySettings(True, False, True))
            assert future.result(timeout=2) == "report"
        finally:
            captured["shutdown"]()

    monkeypatch.setattr(server_module, "build_parser", lambda: type("Parser", (), {"parse_args": lambda self: args})())
    monkeypatch.setattr(server_module, "OllamaClient", Client)
    monkeypatch.setattr(server_module, "YoloDetector", lambda model, confidence: (model, confidence))
    monkeypatch.setattr(server_module, "IncidentPipeline", Pipeline)
    monkeypatch.setattr(server_module, "create_app", lambda store, regenerate_report: captured.update(regenerate=regenerate_report) or App())
    monkeypatch.setattr(server_module.uvicorn, "run", run)

    server_module.main()

    assert captured["settings"].overlays == OverlaySettings(True, False, True)
    assert captured["report"][0] == "incident"
    assert callable(captured["report"][1])
    assert captured["report"][2] == 4.0
    assert captured["report"][3] == OverlaySettings(True, False, True)
