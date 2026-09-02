from dashpi.models import IncidentMetadata, IncidentState


def test_new_incident_starts_collecting():
    incident = IncidentMetadata.new("inc-1", wall_time="2026-09-02T00:00:00Z", trigger_mono=40.0, post_seconds=15.0)
    assert incident.state is IncidentState.COLLECTING_POST_TRIGGER
    assert incident.post_deadline_mono == 55.0
    assert incident.transitions == [{"state": "collecting_post_trigger", "at": "2026-09-02T00:00:00Z"}]
