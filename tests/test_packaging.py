import os
from pathlib import Path
import shutil
import subprocess
import sys


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
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = list(distribution_directory.glob("dashpi-*.whl"))
    assert len(wheels) == 1

    environment = os.environ.copy()
    environment.update(
        {
            "PIP_CACHE_DIR": str(pip_cache),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "TMPDIR": str(build_temp),
        }
    )
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(installation_directory),
            str(wheels[0]),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    environment["PYTHONPATH"] = str(installation_directory)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    smoke = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            "-c",
            "\n".join(
                [
                    "from pathlib import Path",
                    "from fastapi.testclient import TestClient",
                    "import dashpi",
                    "from dashpi.api import create_app",
                    "from dashpi.storage import IncidentStore",
                    f"installed = Path({str(installation_directory)!r}).resolve()",
                    "assert Path(dashpi.__file__).resolve().is_relative_to(installed)",
                    f"app = create_app(IncidentStore(Path({str(tmp_path / 'data')!r})))",
                    "response = TestClient(app).get('/')",
                    "assert response.status_code == 200",
                    "assert '<title>DashPi 인시던트</title>' in response.text",
                    "stylesheet = TestClient(app).get('/tokens.css')",
                    "assert stylesheet.status_code == 200",
                    "assert '--color-paper:' in stylesheet.text",
                ]
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
