from dashpi import progress


def test_emit_is_silent_without_a_listener_and_stops_after_the_block():
    progress.emit("clip", "start")  # nobody listening: must not fail
    events = []
    with progress.reporting(lambda *event: events.append(event)):
        progress.emit("clip", "done", "20.0초")
    progress.emit("frames", "start")

    assert events == [("clip", "done", "20.0초", None)]
