# Live ByteTrack: Pi deployment and hardware acceptance

Date: 2026-10-02 (Asia/Seoul). **Acceptance incomplete: device became unreachable after test launch.** Reviewed application code: `8c4aa38`, branch `feat/live-bytetrack`. No production source changes were made for measurement.

## Environment and preserved evidence

Pi 5 4GB, Debian 13, Python 3.13, IMX708; actual installation `/home/wonmaker/DashPi-native`, system-site-packages `.venv`. Display `:0`, X authority `/home/wonmaker/.Xauthority`, runtime `/run/user/1000`. Production data root `/home/wonmaker/.local/share/dashpi`; acceptance root `/home/wonmaker/.local/share/dashpi-tracking-acceptance`. Neither existing recordings nor settings nor API key files were edited. No incident analysis was requested.

Before deployment, process inspection confirmed PID 1798 running `.venv/bin/python -m dashpi.desktop`. Native Git status contained only untracked `models/`. Both Desktop entries used that command without tracking arguments. The existing recording was gracefully stopped using the LCD Stop button through xdotool, followed by Alt+F4 to close the app.

Backup directory: `/home/wonmaker/.cache/dashpi-tracking-backup/deploy-20261002/`. `source.tar.gz` contains original `src/dashpi/{desktop,pi_camera,vision}.py` and `pyproject.toml`; `applications.desktop` and `Desktop.desktop` preserve both launchers. Deployed only reviewed `desktop.py`, `pi_camera.py`, `vision.py`, `live_tracking.py`, and `pyproject.toml` using scp. Launchers have **not yet been changed**, because acceptance has not passed.

## Model and dependencies

Previously verified preflight: supervision 0.27.0, SciPy 1.17.1; apt NumPy 2.2.4 and cv2 4.14.0 preserved. Incomplete SciPy 1.18.1 metadata was moved to the cache by preflight, not by this deployment. The optional dependency now pins SciPy below 1.18. No Torch was installed; no additional dependency or model download was needed during acceptance.

Persistent model `/home/wonmaker/DashPi-native/models/yolov8n.onnx`, SHA-256 `162ec5e9d2886fc411e4b81811c731e81a72c8f85571de1e0ab040833d92d4f2`. Source: `https://huggingface.co/salim4n/yolov8n-detect-onnx/resolve/main/yolov8n-onnx-web/yolov8n.onnx`. Preflight OpenCV output `(1,84,8400)`; standalone detection on an actual camera screenshot identified a person at confidence .894. This is detector preflight, not integrated tracking acceptance.

## Attempt and observations

A temporary wrapper `/tmp/acceptance.py` called the original application main, original camera prepare/read methods, ByteTrack update, and worker stop. It scheduled two normal GUI recording cycles, with default production 1920×1080 at 30fps and the actual embedded Qt preview. It logged camera callback frame counts, tracking updates/IDs, capture waits and stop join duration to `/tmp/dashpi-acceptance-events.jsonl`; output redirected to `/tmp/dashpi-acceptance.log`. It did not modify production source, inference thresholds, or encoder. Requested tracking defaults: max10Hz, detector confidence .10, activation .45, stale overlay1s.

Launch returned PID **7161**. The next multiplex SSH request, intended to collect resource stats and `scrot --overwrite /tmp/dashpi-acceptance-cycle1.png`, hung without output. Independent `ssh -o ControlPath=none -o ConnectTimeout=8 wonmaker ...` attempts returned:

```text
ssh: connect to host wonmaker-rpi port 22: Operation timed out
```

Ping also failed. These observations establish loss of connectivity, not its cause. No integrated tracking frames, colored boxes, stable IDs, camera rate, CPU/RSS, valid MP4 or successful worker stop were observed or retrieved. Scheduled actions cannot be assumed to have run. Production app restoration is pending device recovery.

## Actual preflight measurements and limitations

While the earlier production app recorded1080p30, detector timing was .349/.301/.296 seconds at one OpenCV thread, .187/.186/.186 seconds at two threads, and .197/.196/.199 seconds at four threads. These are standalone model timings, not measured integrated FPS. Earlier baseline temperature40.8°C and throttled0x0 changed to47.4°C and `get_throttled=0x50000`: historical undervoltage and throttling flags, with current flags clear. A transient power-related event occurred during preflight load. This is a material hardware limit to resolve; the later connectivity failure has no confirmed cause.

Parent's full local regression at `8c4aa38`:508 passed,14 existing FastAPI deprecation warnings,76.42 seconds. Automated tests do not establish physical camera or display acceptance.

## Recovery, completion and rollback

Reconnect using `ssh -o ControlPath=/tmp/dashpi-pi-ssh -o ConnectTimeout=8 wonmaker`; recreate the SSH master if the stale socket is unavailable. First inspect process list, logs and saved test recordings. Do not start a second camera owner. If the test app remains active, stop recording through its LCD Stop button and close it normally. Retrieve `/tmp/dashpi-acceptance-events.jsonl`, `/tmp/dashpi-acceptance.log`, and screenshots before reboot if reachable.

Complete two observed recording cycles with real road objects; inspect screenshot boxes and IDs, measure inference updates and camera/preview rates separately, collect CPU/RSS/temperature/throttle flags, ffprobe all acceptance MP4s, and inspect decoded original frames for absence of boxes. Verify worker joins and camera reopens. Keep photographed people out of the Git repository. Acceptance artifacts may be copied to workstation `/tmp/dashpi-live-acceptance/`.

After successful acceptance, edit only Exec in both launchers to:

```text
Exec=/home/wonmaker/DashPi-native/.venv/bin/python -m dashpi.desktop --tracking-model /home/wonmaker/DashPi-native/models/yolov8n.onnx
```

Restore the regular data root app on LCD and start recording if the scene is ready. Keep existing API settings private.

Rollback after gracefully stopping any camera owner:

```sh
cd /home/wonmaker/DashPi-native
tar xzf /home/wonmaker/.cache/dashpi-tracking-backup/deploy-20261002/source.tar.gz
cp /home/wonmaker/.cache/dashpi-tracking-backup/deploy-20261002/applications.desktop /home/wonmaker/.local/share/applications/DashPi.desktop
cp /home/wonmaker/.cache/dashpi-tracking-backup/deploy-20261002/Desktop.desktop /home/wonmaker/Desktop/DashPi.desktop
DISPLAY=:0 XAUTHORITY=/home/wonmaker/.Xauthority XDG_RUNTIME_DIR=/run/user/1000 .venv/bin/python -m dashpi.desktop
```

The added `live_tracking.py`, model and optional dependencies can remain unused during rollback. No command above removes any recording or key file.
