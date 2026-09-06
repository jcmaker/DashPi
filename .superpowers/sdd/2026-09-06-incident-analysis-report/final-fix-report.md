# Final fix report — incident analysis report

Date: 2026-09-06
Worktree: /Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report
Branch: codex/incident-analysis-report
Starting HEAD: 93c2fb1 (test: verify offline incident report delivery)
Requested commit subject: fix: address incident report final review findings

## Status

All eight Important and both Minor findings have implementation changes in this single wave. Functional backend and JavaScript regressions pass. Full verification is **not fully green** because this execution environment denies socket binding and native browser execution. Rendered visibility has an executable regression, but its RED/GREEN rendering could not be observed; the CSS change therefore has an explicit strict-TDD verification gap.

The required complete Python command was run. With a temporary offline uv cache, its result is **294 passed, 2 failed, 14 warnings**; both remaining failures are local HTTP-server socket binding denied by the sandbox. The required npm test command fails before test execution when tsx creates its IPC socket. The direct Node runner executes the same test files: **26 passed, 1 skipped** (the native browser visibility test). Build and both immutable optical diffs pass. The 14 warnings are the existing FastAPI on_event deprecation exercised by seven new real server wiring tests.

No subagents or other worktrees were used. No dependencies were added. The existing src/dashpi.egg-info directory was neither edited nor staged; git still identifies it as untracked. The wheel test builds a copied source tree in a temporary directory.

## Changes and review finding coverage

| Finding | Implementation and focused evidence |
| --- | --- |
| Important 1: regeneration clip trust boundary | API preflight now requires canonical clip.mp4 and reuses _open_verified_file for regular-file, size and SHA-256 verification. The server queues the incident ID. Inside the worker, regenerate_report reloads metadata using open_incident and verifies the canonical clip again. A private TemporaryDirectory snapshot is copied from the verified descriptor for every native media reader. The original descriptor remains open through execution and is hashed again before READY. Tests reject outside metadata paths, symlinked clips and directories, nonregular/empty/corrupted files, queued replacements, and verify safe input bytes after a clip or directory pathname replacement. An in-place original-file mutation produces ANALYSIS_FAILED. |
| Important 2: sample timestamps | sample_frames now returns list[tuple[Path, float]] using the exact timestamp supplied to ffmpeg -ss. OllamaClient.analyze accepts this narrow interface and sends images and clip-relative timestamps in matching order. The exact mandated prompt sentence remains intact; an appended origin clarification and ordered timestamp list disambiguate the first sampled image from evidence time zero. Tests pin the 45-second/12-sample mapping and the actual serialized request payload. |
| Important 3: late derivative metadata | Each successful derivative publication updates incident.annotated immediately, before probing, keyframes, rendering, or report writes can fail. Quality downgrade publication updates it again before probing. Eight regression cases cover initial builds and predecessor replacement, with report.json, report.html, fallback keyframe, and quality-probe failure. Saved artifact digests and lengths match the completed files. |
| Important 4: stale queued snapshots | Worker execution reloads metadata rather than retaining the request snapshot. API locking also rejects a duplicate pending regeneration. The two-job regression queues a successful rebuild followed by failed report validation and verifies that the first job's derivative, report digest and transitions survive. |
| Important 5: async terminal visibility | Added a lock-protected per-incident Future status endpoint. Pending work reports analyzing even before the worker starts; terminal pipeline failures and exceptional Futures are visible. The native page polls status, refreshes the incident list through terminal visibility, hides stale report/transfer links during processing, and disables resubmission. Selection is not taken back from another incident. JavaScript tests execute the shipped script for delayed success/failure and selection changes. |
| Important 6: hidden display behavior | Explicit .detail[hidden], .report-controls[hidden], and .sender-link[hidden] rules override the grid/inline-flex declarations. The browser regression checks both computed display and rendered box counts, including children while their parent is visible. Browser execution was blocked, so rendered RED/GREEN remains unverified. |
| Important 7: offset carryover | Changing incident IDs clears the manual offset. Refreshing the same incident preserves its current input. The regression enters 7 for A, switches to B, submits, and verifies that B's request has no manual offset. |
| Important 8: paused worker test cleanup | Every worker-owning test now closes its worker in finally, and the single-worker sequencing test also releases its own gate there. A bounded subprocess regression injects an exception after submission in each of the three existing worker tests and verifies process exit. The new regeneration integration helper and existing server wiring test also clean up unconditionally. |
| Minor: boolean offsets | A Pydantic before-validator rejects true and false before float coercion. API tests expect 422 and no callback invocation. |
| Minor: wrong size explanation | The size explanation requires a completed report with optical transfer unavailable; an analysis failure with no report does not show it. |

## Files

Production:
- src/dashpi/api.py — verified request boundary, boolean validation, pending-job locking, terminal status.
- src/dashpi/server.py — capture only incident ID and invoke worker-time reload.
- src/dashpi/pipeline.py — verified snapshot lifecycle, original descriptor integrity check, immediate completed derivative metadata.
- src/dashpi/media.py — sample path/timestamp pairs.
- src/dashpi/reports.py — timestamp-aware input interface and literal prompt extension.
- src/dashpi/web/index.html — polling and pending state, selection/offset handling, correct availability explanation.
- src/dashpi/web/tokens.css — explicit hidden selectors, scoped to the workbench elements.

Tests:
- tests/test_api.py — invalid evidence, boolean offsets, duplicate pending jobs and Future status.
- tests/test_regeneration.py (new) — real server/worker/pipeline composition, queued reload and safe clip access during execution.
- tests/test_pipeline.py — completed-artifact metadata across four late failure boundaries, with and without a predecessor.
- tests/test_analysis_worker.py — failure-injected subprocess cleanup regressions and finally blocks.
- tests/test_server.py — updated narrow worker entry point and unconditional test cleanup.
- tests/test_media.py — exact sample seek mapping.
- tests/test_reports.py — tuple input and serialized prompt/image mapping, retaining network/redirect coverage.
- web/tests/incidents.test.ts (new) — shipped-script behavior regressions with DOM/network/timer boundary doubles, plus opt-in native Chromium rendered visibility.

This report is deliberately force-added because .superpowers is ignored by repository rules. No optical source, fixture, sender/receiver implementation, or generated optical bundle is changed.

## TDD evidence

Commands below ran in this worktree. Output blocks preserve the terminal text with trailing whitespace trimmed for git diff --check; full original logs are retained as /tmp/incident-fix-*.log. Interface failures are expected RED failures from the missing tuple contract, not import or collection errors.

### Timestamp interface

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_media.py::test_samples_carry_the_exact_clip_relative_seek_times tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests -q
src/dashpi/reports.py:57: AttributeError
=========================== short test summary info ============================
FAILED tests/test_media.py::test_samples_carry_the_exact_clip_relative_seek_times
FAILED tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests
2 failed in 0.02s
```
RED showed PosixPath was not subscriptable in the sampling contract and the old analyzer attempted read_bytes on a tuple. After the minimal interface changes, the same command returned:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_media.py::test_samples_carry_the_exact_clip_relative_seek_times tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests -q
..                                                                       [100%]
2 passed in 0.01s
```

The localhost payload test was updated first but could not reach its assertion because binding was denied. To establish observable payload RED without a socket, the in-process opener test was extended to assert the real serialized prompt and images, the prompt extension was temporarily removed, and that specific assertion failed. The separate evidence mutation regression failed in the same run (READY instead of ANALYSIS_FAILED):

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis
FAILED tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests
2 failed, 2 warnings in 0.76s
```
The extension was restored and the original descriptor's final hash check implemented. GREEN:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_regeneration.py tests/test_reports.py::test_client_uses_proxy_disabled_opener_for_both_requests -q
8 passed, 14 warnings in 1.40s
```

### API trust, boolean and async status boundaries

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_api.py -k 'regeneration_rejects_boolean or regeneration_enforces or regeneration_status' -q
tests/test_api.py:151: KeyError
=========================== short test summary info ============================
FAILED tests/test_api.py::test_report_regeneration_rejects_boolean_offsets[True]
FAILED tests/test_api.py::test_report_regeneration_rejects_boolean_offsets[False]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[outside]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[symlink]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[directory]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[empty]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[size]
FAILED tests/test_api.py::test_regeneration_enforces_the_clip_download_trust_boundary[digest]
FAILED tests/test_api.py::test_regeneration_status_tracks_queued_work_through_terminal_result[ready]
FAILED tests/test_api.py::test_regeneration_status_tracks_queued_work_through_terminal_result[analysis_failed]
FAILED tests/test_api.py::test_regeneration_status_tracks_queued_work_through_terminal_result[exception]
11 failed, 1 passed, 58 deselected in 0.25s
```
The already-protected symlinked incident-directory case passed in RED. The six other damaged clip cases wrongly reached the callback; booleans returned 200; the status route did not exist. GREEN also includes the existing regeneration tests:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_api.py -k 'regeneration' -q
...............                                                          [100%]
15 passed, 55 deselected in 0.20s
```

### Late completed-artifact metadata

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_pipeline.py -k report_write_failure -q
tests/test_pipeline.py:277: AssertionError
=========================== short test summary info ============================
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[report.json-False]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[report.json-True]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[report.html-False]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[report.html-True]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[keyframe-False]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[keyframe-True]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[quality_probe-False]
FAILED tests/test_pipeline.py::test_report_write_failure_persists_exposed_clip[quality_probe-True]
8 failed, 11 deselected in 5.36s
```
All eight cases failed on absent annotated metadata or a predecessor digest that no longer matched the completed derivative. Minimum production changes assign metadata at each publication boundary. Combined GREEN appears below.

### Queued work and descriptor lifetime

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_regeneration.py -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[outside]
FAILED tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[clip_symlink]
FAILED tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[directory_symlink]
FAILED tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
FAILED tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement
5 failed, 10 warnings in 0.87s
```
Three cases sampled a clip that should have been rejected. The running pathname-swap test sampled "evil" instead of the verified "clip" bytes. The initial two-job fixture used a two-second clip; its first job failed on late frame sampling, which was not valid evidence of the stale-snapshot bug. The fixture was corrected to six seconds and the old server callback was temporarily restored. The resulting RED failed on the saved report digest versus the published report digest:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata -q
-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
1 failed, 2 warnings in 0.94s
```
After restoring ID-based worker reload, the combined late-failure, queue, trust and server wiring tests were GREEN:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_regeneration.py tests/test_server.py tests/test_pipeline.py -k 'regeneration or server or report_write_failure' -q
16 passed, 11 deselected, 10 warnings in 6.41s
```
Subsequent directory-path and in-place mutation cases are included in the eight-test GREEN and the final full suite above.

### Paused-worker cleanup

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_analysis_worker.py -k close_even -q
=========================== short test summary info ============================
FAILED tests/test_analysis_worker.py::test_worker_tests_close_even_when_submission_raises[test_analysis_waits_during_recording_pressure_without_blocking_caller]
FAILED tests/test_analysis_worker.py::test_worker_tests_close_even_when_submission_raises[test_worker_runs_only_one_analysis_at_a_time]
FAILED tests/test_analysis_worker.py::test_worker_tests_close_even_when_submission_raises[test_recording_continues_while_analysis_is_paused]
3 failed, 3 deselected in 3.17s
```
Each child exceeded the bounded timeout because an exception left a worker alive. After finally-based cleanup:

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_analysis_worker.py -q
......                                                                   [100%]
6 passed in 0.29s
```

### UI behavior

```text
$ node --import ./web/node_modules/tsx/dist/loader.mjs --test web/tests/incidents.test.ts
1..6
# tests 6
# suites 0
# pass 0
# fail 5
# cancelled 0
# skipped 1
# todo 0
# duration_ms 644.232875
```
RED observations were stale "ready" instead of "analyzing", offset value "7" after switching, an exposed size explanation on failure, and zero status polls. The same command after the page changes:

```text
$ node --import ./web/node_modules/tsx/dist/loader.mjs --test web/tests/incidents.test.ts
TAP version 13
# Subtest: regeneration polls queued and absent incidents until delayed ready is visible
ok 1 - regeneration polls queued and absent incidents until delayed ready is visible
  ---
  duration_ms: 1.08775
  type: 'test'
  ...
# Subtest: regeneration polls queued and absent incidents until delayed analysis_failed is visible
ok 2 - regeneration polls queued and absent incidents until delayed analysis_failed is visible
  ---
  duration_ms: 0.382666
  type: 'test'
  ...
# Subtest: switching incidents clears the manual offset before regeneration
ok 3 - switching incidents clears the manual offset before regeneration
  ---
  duration_ms: 0.397542
  type: 'test'
  ...
# Subtest: unavailable reports only show the size explanation for completed reports
ok 4 - unavailable reports only show the size explanation for completed reports
  ---
  duration_ms: 0.248458
  type: 'test'
  ...
# Subtest: a pending rebuild does not take selection back from another incident
ok 5 - a pending rebuild does not take selection back from another incident
  ---
  duration_ms: 0.39525
  type: 'test'
  ...
# Subtest: hidden detail, report controls and sender link have no rendered boxes
ok 6 - hidden detail, report controls and sender link have no rendered boxes # SKIP
  ---
  duration_ms: 0.025333
  type: 'test'
  ...
1..6
# tests 6
# suites 0
# pass 5
# fail 0
# cancelled 0
# skipped 1
# todo 0
# duration_ms 65.235083
```

### Rendered visibility — blocked, not counted as RED/GREEN

The browser regression was added before the CSS fix. Its explicit execution failed when native Chrome aborted, before any DOM assertion. It is opt-in via DASHPI_BROWSER, so a machine without a usable Chromium binary does not silently claim rendering coverage.

```text
$ DASHPI_BROWSER='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' node --import ./web/node_modules/tsx/dist/loader.mjs --test --test-name-pattern='rendered boxes' web/tests/incidents.test.ts
TAP version 13
# Subtest: hidden detail, report controls and sender link have no rendered boxes
not ok 1 - hidden detail, report controls and sender link have no rendered boxes
  ---
  duration_ms: 75.481458
  type: 'test'
  location: '/Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/web/tests/incidents.test.ts:1:5168'
  failureType: 'testCodeFailure'
  error: 'Command failed: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --headless --disable-gpu --no-first-run --user-data-dir=/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/dashpi-visibility-11c0Zt/profile --dump-dom file:///var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/dashpi-visibility-11c0Zt/test.html'
  code: 'ERR_TEST_FAILURE'
  stack: |-
    genericNodeError (node:internal/errors:983:15)
    wrappedFn (node:internal/errors:537:14)
    checkExecSyncError (node:child_process:916:11)
    execFileSync (node:child_process:952:15)
    TestContext.<anonymous> (/Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/web/tests/incidents.test.ts:146:20)
    async Test.run (node:internal/test_runner/test:1054:7)
    async startSubtestAfterBootstrap (node:internal/test_runner/harness:296:3)
  ...
1..1
# tests 1
# suites 0
# pass 0
# fail 1
# cancelled 0
# skipped 0
# todo 0
# duration_ms 134.36525
```
A connected-browser attempt to open the local test document was also rejected: "The browser URL policy blocks this action." No workaround for that security rejection was attempted. CSS specificity was self-reviewed, but that is not rendered verification. This remains an explicit incomplete validation requirement.

## Required and supplemental verification

### Focused Python

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_api.py tests/test_regeneration.py tests/test_analysis_worker.py tests/test_server.py tests/test_pipeline.py tests/test_media.py tests/test_reports.py tests/test_web.py -q -k 'not test_client_sends_local_generate_request_with_expected_payload_and_timeouts and not test_client_rejects_redirect_without_requesting_redirect_target'
153 passed, 2 deselected, 14 warnings in 15.15s
```

The earlier focused command without exclusions returned 2 failed, 151 passed, 10 warnings in 14.89s, solely because the local HTTP-server tests could not bind. The final focused command includes the two subsequently added trust cases.

### Complete Python suite: exact requested command

```text
$ /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest -q
........................................................................ [ 24%]
........................................................................ [ 48%]
..............................................................F......... [ 72%]
........................................................FF.............. [ 97%]
........                                                                 [100%]
=================================== FAILURES ===================================
___________ test_installed_wheel_constructs_app_and_serves_local_ui ____________

tmp_path = PosixPath('/private/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/pytest-of-justin/pytest-212/test_installed_wheel_construct0')

    def test_installed_wheel_constructs_app_and_serves_local_ui(tmp_path):
        project_root = Path(__file__).resolve().parents[1]
        source_directory = tmp_path / "source"
        distribution_directory = tmp_path / "dist"
        installation_directory = tmp_path / "installed"
        build_temp = tmp_path / "build-temp"
        pip_cache = tmp_path / "pip-cache"
        distribution_directory.mkdir()
        build_temp.mkdir()
        source_directory.mkdir()
        shutil.copy2(project_root / "pyproject.toml", source_directory / "pyproject.toml")
        shutil.copytree(project_root / "src", source_directory / "src")
        uv = shutil.which("uv")
        assert uv is not None, "offline wheel smoke requires uv"

        build = subprocess.run(
            [
                uv,
                "build",
                "--offline",
                "--wheel",
                "--out-dir",
                str(distribution_directory),
                "--no-create-gitignore",
                str(source_directory),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
>       assert build.returncode == 0, build.stdout + build.stderr
E       AssertionError: error: Failed to initialize cache at `/Users/justin/.cache/uv`
E           Caused by: failed to open file `/Users/justin/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)
E
E       assert 2 == 0
E        +  where 2 = CompletedProcess(args=['/Users/justin/.local/bin/uv', 'build', '--offline', '--wheel', '--out-dir', '/private/var/fold...v`\n  Caused by: failed to open file `/Users/justin/.cache/uv/sdists-v9/.git`: Operation not permitted (os error 1)\n').returncode

tests/test_packaging.py:39: AssertionError
_ test_client_sends_local_generate_request_with_expected_payload_and_timeouts __

tmp_path = PosixPath('/private/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/pytest-of-justin/pytest-212/test_client_sends_local_genera0')

    def test_client_sends_local_generate_request_with_expected_payload_and_timeouts(tmp_path):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, None))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"models":[{"name":"moondream"}]}')

            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                seen.append((self.path, payload))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"response":"{\\"incident_timestamp\\": 3.0, \\"summary\\": \\"Vehicle stopped\\", \\"observations\\": [], \\"limitations\\": []}"}')

            def log_message(self, *_):
                return None

        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"jpeg")
>       with LocalServer(Handler) as server:
             ^^^^^^^^^^^^^^^^^^^^

tests/test_reports.py:346:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/test_reports.py:12: in __init__
    self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:456: in __init__
    self.server_bind()
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/http/server.py:140: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <http.server.ThreadingHTTPServer object at 0x1133df5d0>

    def server_bind(self):
        """Called by constructor to bind the socket.

        May be overridden.

        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:472: PermissionError
_______ test_client_rejects_redirect_without_requesting_redirect_target ________

tmp_path = PosixPath('/private/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/pytest-of-justin/pytest-212/test_client_rejects_redirect_w0')

    def test_client_rejects_redirect_without_requesting_redirect_target(tmp_path):
        target_hits = []

        class TargetHandler(BaseHTTPRequestHandler):
            def respond(self):
                target_hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "17")
                self.end_headers()
                self.wfile.write(b'{"response":"{}"}')

            do_GET = respond
            do_POST = respond

            def log_message(self, *_):
                return None

>       with LocalServer(TargetHandler) as target:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_reports.py:391:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/test_reports.py:12: in __init__
    self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:456: in __init__
    self.server_bind()
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/http/server.py:140: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <http.server.ThreadingHTTPServer object at 0x1134f4d50>

    def server_bind(self):
        """Called by constructor to bind the socket.

        May be overridden.

        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:472: PermissionError
=============================== warnings summary ===============================
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[outside]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[clip_symlink]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[directory_symlink]
tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[clip]
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[directory]
tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis
  /Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/src/dashpi/server.py:57: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    @app.on_event("shutdown")

tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[outside]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[clip_symlink]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[directory_symlink]
tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[clip]
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[directory]
tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis
  /Users/justin/Documents/ChatGPT/DashPi/.venv/lib/python3.11/site-packages/fastapi/applications.py:4681: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    return self.router.on_event(event_type)  # ty: ignore[deprecated]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_packaging.py::test_installed_wheel_constructs_app_and_serves_local_ui
FAILED tests/test_reports.py::test_client_sends_local_generate_request_with_expected_payload_and_timeouts
FAILED tests/test_reports.py::test_client_rejects_redirect_without_requesting_redirect_target
3 failed, 293 passed, 14 warnings in 17.78s
```

The wheel failure was an environment cache write denial. Existing setuptools/wheel cache records and their small archive directories were copied read-only from the default uv cache into /tmp/dashpi-final-fix-uv-cache. No installed package or original cache file was changed. The standalone wheel test then passed:

```text
$ UV_CACHE_DIR=/tmp/dashpi-final-fix-uv-cache /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest tests/test_packaging.py -q
.                                                                        [100%]
1 passed in 0.93s
```

The complete suite was rerun with that temporary cache. Exact output:

```text
$ UV_CACHE_DIR=/tmp/dashpi-final-fix-uv-cache /Users/justin/Documents/ChatGPT/DashPi/.venv/bin/python -m pytest -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
........................................................FF.............. [ 97%]
........                                                                 [100%]
=================================== FAILURES ===================================
_ test_client_sends_local_generate_request_with_expected_payload_and_timeouts __

tmp_path = PosixPath('/private/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/pytest-of-justin/pytest-215/test_client_sends_local_genera0')

    def test_client_sends_local_generate_request_with_expected_payload_and_timeouts(tmp_path):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.path, None))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"models":[{"name":"moondream"}]}')

            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                seen.append((self.path, payload))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"response":"{\\"incident_timestamp\\": 3.0, \\"summary\\": \\"Vehicle stopped\\", \\"observations\\": [], \\"limitations\\": []}"}')

            def log_message(self, *_):
                return None

        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"jpeg")
>       with LocalServer(Handler) as server:
             ^^^^^^^^^^^^^^^^^^^^

tests/test_reports.py:346:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/test_reports.py:12: in __init__
    self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:456: in __init__
    self.server_bind()
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/http/server.py:140: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <http.server.ThreadingHTTPServer object at 0x115a54610>

    def server_bind(self):
        """Called by constructor to bind the socket.

        May be overridden.

        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:472: PermissionError
_______ test_client_rejects_redirect_without_requesting_redirect_target ________

tmp_path = PosixPath('/private/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/pytest-of-justin/pytest-215/test_client_rejects_redirect_w0')

    def test_client_rejects_redirect_without_requesting_redirect_target(tmp_path):
        target_hits = []

        class TargetHandler(BaseHTTPRequestHandler):
            def respond(self):
                target_hits.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "17")
                self.end_headers()
                self.wfile.write(b'{"response":"{}"}')

            do_GET = respond
            do_POST = respond

            def log_message(self, *_):
                return None

>       with LocalServer(TargetHandler) as target:
             ^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_reports.py:391:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/test_reports.py:12: in __init__
    self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:456: in __init__
    self.server_bind()
/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/http/server.py:140: in server_bind
    socketserver.TCPServer.server_bind(self)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

self = <http.server.ThreadingHTTPServer object at 0x1159dc250>

    def server_bind(self):
        """Called by constructor to bind the socket.

        May be overridden.

        """
        if self.allow_reuse_address and hasattr(socket, "SO_REUSEADDR"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if self.allow_reuse_port and hasattr(socket, "SO_REUSEPORT"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
>       self.socket.bind(self.server_address)
E       PermissionError: [Errno 1] Operation not permitted

/Users/justin/.local/share/uv/python/cpython-3.11.15-macos-aarch64-none/lib/python3.11/socketserver.py:472: PermissionError
=============================== warnings summary ===============================
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[outside]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[clip_symlink]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[directory_symlink]
tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[clip]
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[directory]
tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis
  /Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/src/dashpi/server.py:57: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    @app.on_event("shutdown")

tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[outside]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[clip_symlink]
tests/test_regeneration.py::test_queued_regeneration_revalidates_clip_before_analysis[directory_symlink]
tests/test_regeneration.py::test_queued_regeneration_reloads_the_latest_completed_metadata
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[clip]
tests/test_regeneration.py::test_regeneration_media_reads_verified_snapshot_after_path_replacement[directory]
tests/test_regeneration.py::test_regeneration_detects_in_place_evidence_changes_during_analysis
  /Users/justin/Documents/ChatGPT/DashPi/.venv/lib/python3.11/site-packages/fastapi/applications.py:4681: DeprecationWarning:
          on_event is deprecated, use lifespan event handlers instead.

          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).

    return self.router.on_event(event_type)  # ty: ignore[deprecated]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED tests/test_reports.py::test_client_sends_local_generate_request_with_expected_payload_and_timeouts
FAILED tests/test_reports.py::test_client_rejects_redirect_without_requesting_redirect_target
2 failed, 294 passed, 14 warnings in 19.09s
```

### npm test: exact requested command

```text
$ npm --prefix web test

> test
> tsx --test tests/*.test.ts

node:net:1919
      const error = new UVExceptionWithHostPort(rval, 'listen', address, port);
                    ^

Error: listen EPERM: operation not permitted /var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/tsx-501/33763.pipe
    at Server.setupListenHandle [as _listen2] (node:net:1919:21)
    at listenInCluster (node:net:1998:12)
    at Server.listen (node:net:2120:5)
    at file:///Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/web/node_modules/tsx/dist/cli.mjs:53:31472
    at new Promise (<anonymous>)
    at createIpcServer (file:///Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/web/node_modules/tsx/dist/cli.mjs:53:31450)
    at async file:///Users/justin/Documents/ChatGPT/DashPi/.worktrees/incident-analysis-report/web/node_modules/tsx/dist/cli.mjs:55:542 {
  code: 'EPERM',
  errno: -1,
  syscall: 'listen',
  address: '/var/folders/3v/k_2lb2sn5c95591njks36x5m0000gn/T/tsx-501/33763.pipe',
  port: -1
}

Node.js v22.23.1
```

The wrapper aborts before collecting tests because its IPC socket is denied. The direct Node test runner uses the same checked-in TS loader and test files without creating that optional wrapper IPC server:

```text
$ node --import ./web/node_modules/tsx/dist/loader.mjs --test web/tests/*.test.ts
TAP version 13
# Subtest: unpacks a compressed DPC1 file after SHA-256 verification
ok 1 - unpacks a compressed DPC1 file after SHA-256 verification
  ---
  duration_ms: 13.760208
  type: 'test'
  ...
# Subtest: rejects a DPC1 file whose payload does not match its SHA-256
ok 2 - rejects a DPC1 file whose payload does not match its SHA-256
  ---
  duration_ms: 5.116958
  type: 'test'
  ...
# Subtest: rejects container metadata that is unsafe as a download name
ok 3 - rejects container metadata that is unsafe as a download name
  ---
  duration_ms: 0.420583
  type: 'test'
  ...
# Subtest: browser recovers the Python one-megabyte loss fixture
ok 4 - browser recovers the Python one-megabyte loss fixture
  ---
  duration_ms: 176.528125
  type: 'test'
  ...
# Subtest: recovers carried equations without a shared PRNG
ok 5 - recovers carried equations without a shared PRNG
  ---
  duration_ms: 1.091083
  type: 'test'
  ...
# Subtest: rejects another session before it can corrupt the result
ok 6 - rejects another session before it can corrupt the result
  ---
  duration_ms: 0.392042
  type: 'test'
  ...
# Subtest: rejects a conflicting equation that reduces to a solved block
ok 7 - rejects a conflicting equation that reduces to a solved block
  ---
  duration_ms: 0.145958
  type: 'test'
  ...
# Subtest: rejects contradictory unresolved equations after peeling
ok 8 - rejects contradictory unresolved equations after peeling
  ---
  duration_ms: 0.425875
  type: 'test'
  ...
# Subtest: rejects malformed symbols before changing decoder state
ok 9 - rejects malformed symbols before changing decoder state
  ---
  duration_ms: 0.187334
  type: 'test'
  ...
# Subtest: regeneration polls queued and absent incidents until delayed ready is visible
ok 10 - regeneration polls queued and absent incidents until delayed ready is visible
  ---
  duration_ms: 3.29575
  type: 'test'
  ...
# Subtest: regeneration polls queued and absent incidents until delayed analysis_failed is visible
ok 11 - regeneration polls queued and absent incidents until delayed analysis_failed is visible
  ---
  duration_ms: 1.221167
  type: 'test'
  ...
# Subtest: switching incidents clears the manual offset before regeneration
ok 12 - switching incidents clears the manual offset before regeneration
  ---
  duration_ms: 0.732541
  type: 'test'
  ...
# Subtest: unavailable reports only show the size explanation for completed reports
ok 13 - unavailable reports only show the size explanation for completed reports
  ---
  duration_ms: 0.539333
  type: 'test'
  ...
# Subtest: a pending rebuild does not take selection back from another incident
ok 14 - a pending rebuild does not take selection back from another incident
  ---
  duration_ms: 1.418792
  type: 'test'
  ...
# Subtest: hidden detail, report controls and sender link have no rendered boxes
ok 15 - hidden detail, report controls and sender link have no rendered boxes # SKIP
  ---
  duration_ms: 0.05525
  type: 'test'
  ...
# Subtest: service worker caches only the local receiver shell
ok 16 - service worker caches only the local receiver shell
  ---
  duration_ms: 6.284208
  type: 'test'
  ...
# Subtest: parses the Python golden vector
ok 17 - parses the Python golden vector
  ---
  duration_ms: 0.654834
  type: 'test'
  ...
# Subtest: rejects a golden frame with a corrupted CRC
ok 18 - rejects a golden frame with a corrupted CRC
  ---
  duration_ms: 0.147541
  type: 'test'
  ...
# Subtest: rejects a checksummed frame whose total length exceeds its geometry
ok 19 - rejects a checksummed frame whose total length exceeds its geometry
  ---
  duration_ms: 0.215
  type: 'test'
  ...
# Subtest: rejects checksummed frames outside the v1 header boundary
ok 20 - rejects checksummed frames outside the v1 header boundary
  ---
  duration_ms: 0.370584
  type: 'test'
  ...
# Subtest: receiver keeps camera start and verified save explicit
ok 21 - receiver keeps camera start and verified save explicit
  ---
  duration_ms: 3.747375
  type: 'test'
  ...
# Subtest: keeps foreign QR errors silent and explains unsupported DashPi versions
ok 22 - keeps foreign QR errors silent and explains unsupported DashPi versions
  ---
  duration_ms: 0.081958
  type: 'test'
  ...
# Subtest: resets incomplete recovery when a new optical stream arrives
ok 23 - resets incomplete recovery when a new optical stream arrives
  ---
  duration_ms: 0.480167
  type: 'test'
  ...
# Subtest: requires confidentiality acknowledgement and calibration controls
ok 24 - requires confidentiality acknowledgement and calibration controls
  ---
  duration_ms: 4.348791
  type: 'test'
  ...
# Subtest: waits for each QR render before starting another frame
ok 25 - waits for each QR render before starting another frame
  ---
  duration_ms: 0.124292
  type: 'test'
  ...
# Subtest: clears a prior error tone when status returns to normal
ok 26 - clears a prior error tone when status returns to normal
  ---
  duration_ms: 0.071625
  type: 'test'
  ...
# Subtest: discards a late resource after the sender stops
ok 27 - discards a late resource after the sender stops
  ---
  duration_ms: 0.234584
  type: 'test'
  ...
1..27
# tests 27
# suites 0
# pass 26
# fail 0
# cancelled 0
# skipped 1
# todo 0
# duration_ms 400.055208
```

### Build, whitespace, immutable optical checks

```text
$ npm --prefix web run build

> build
> node build.mjs
```
```text
$ git diff --check

```
```text
$ git diff 3a2e791 -- src/dashpi/optical tests/fixtures/optical-v1.json tests/fixtures/optical-e2e.json

```
```text
$ git diff 3a2e791 -- web/src/container.ts web/src/fountain.ts web/src/protocol.ts web/src/receiver.ts web/src/sender.ts

```
All four commands exited 0. Both optical diffs and the whitespace check produced no output. The build produced no tracked optical bundle differences.

## Self-review

- Walked every final-review finding against its production change and regression. No finding was deliberately deferred; rendered verification is blocked as described.
- Checked that the request thread does not confer pathname trust on queued work. It performs preflight; the worker independently reloads and verifies. Native source reads use only the private snapshot, and the original descriptor is still available for the final integrity check.
- Checked descriptor and TemporaryDirectory lifetime under successful work, trust rejection, analyzer failure, and pathname replacement. Context managers close them and remove private input copies. This adds one evidence-clip-sized temporary disk copy per running regeneration; only one analysis worker runs at a time.
- Checked pending-job locking and status before execution, terminal success, terminal pipeline failure, and exceptional Future completion. A duplicate pending request cannot submit another API job. The separate direct-worker queue test still proves that independently queued jobs reload metadata.
- Checked that each completed derivative metadata assignment precedes possible later failure. Failed reports remain excluded from report-serving routes. Existing partial/fsync/hash/rename writers are unchanged.
- Checked the literal prompt and the timestamp list independently of the request mock: the sampler uses literal expected 45-second timings, and the client assertion inspects its actual HTTP Request body.
- Checked page selection after asynchronous work: the submitted ID is captured, pending controls are incident-specific, and a refresh only updates the incident still selected.
- Checked hidden selectors' specificity against grid/inline-flex declarations; native rendering still needs a permitted browser run.
- Checked every worker-owning test added or touched for finally cleanup, including the server wiring fixture.
- Confirmed changes stay within the report boundaries and use existing storage verification, locking, native HTML/CSS/JS and stdlib. No DPC1/DPQ1 code or fixture change.
- Confirmed git ls-files src/dashpi.egg-info returns no files. No command writes or stages that directory.

## Concerns and remaining validation

1. The session's shell sandbox denies loopback and IPC socket creation. The two complete-suite HTTP tests and exact npm wrapper remain blocked. The tool rejected an escalation attempt with: "approval policy is Never; reject command — you cannot ask for escalated permissions if the approval policy is Never". No test result is presented as passing when it did not run.
2. The native rendered-visibility regression must be run in a permitted Chromium environment using DASHPI_BROWSER. The strict observed-RED/GREEN requirement for this CSS boundary could not be fulfilled here.
3. Job status is held in process memory, matching the existing single-server/single-worker lifetime. Reloading the server loses those status Futures; browser polling currently retries unavailable status responses. Durable jobs and restart recovery are outside this requested fix wave.
4. No new Pi hardware performance measurements were made. The private snapshot introduces one temporary clip copy during regeneration; all media paths and completed artifacts still use the existing implementation.

## Commit record

The requested complete-wave commit will include the production fixes, regressions, and this report, with src/dashpi.egg-info explicitly excluded. Subject: fix: address incident report final review findings. The final response records the actual commit SHA or the exact repository-permission blocker.
