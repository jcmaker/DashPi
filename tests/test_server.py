from dashpi.server import build_parser


def test_server_defaults_to_loopback():
    args = build_parser().parse_args(["--data-root", "/tmp/dashpi"])

    assert (args.host, args.port) == ("127.0.0.1", 8000)
