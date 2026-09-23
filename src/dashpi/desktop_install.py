"""Install a native DashPi launcher on Raspberry Pi OS Desktop."""

from __future__ import annotations

import argparse
from importlib.resources import files
import os
from pathlib import Path
import shutil

from dashpi.storage import atomic_write


def install_launcher(applications_dir: Path, desktop_dir: Path, executable: Path) -> Path:
    if not executable.is_absolute():
        raise ValueError("dashpi-app executable path must be absolute")
    command = str(executable)
    if any(character in command for character in "\n\r%"):
        raise ValueError("invalid dashpi-app executable path")
    if any(character in command for character in ' \\"'):
        command = '"' + command.replace("\\", "\\\\").replace('"', '\\"') + '"'
    application = applications_dir / "DashPi.desktop"
    desktop = desktop_dir / "DashPi.desktop"
    for target in (application, desktop):
        if target.exists() and "X-DashPi-Managed=true" not in target.read_text():
            raise FileExistsError(f"사용자가 만든 실행 아이콘을 덮어쓰지 않습니다: {target}")
    icon = applications_dir.parent / "icons" / "hicolor" / "scalable" / "apps" / "dashpi.svg"
    entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DashPi\n"
        "Comment=Native camera and incident analysis\n"
        f"Exec={command}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=AudioVideo;Video;\n"
        "X-DashPi-Managed=true\n"
    ).encode()
    atomic_write(icon, files("dashpi").joinpath("web", "icon.svg").read_bytes())
    for target in (application, desktop):
        atomic_write(target, entry)
        target.chmod(0o755)
    return desktop


def main() -> None:
    parser = argparse.ArgumentParser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    parser.add_argument("--applications-dir", type=Path, default=data_home / "applications")
    parser.add_argument("--desktop-dir", type=Path, default=Path.home() / "Desktop")
    args = parser.parse_args()
    command = shutil.which("dashpi-app")
    if command is None:
        parser.error("dashpi-app 실행 파일을 찾을 수 없습니다. 먼저 앱을 설치하세요.")
    print(install_launcher(args.applications_dir, args.desktop_dir, Path(command).resolve()))


if __name__ == "__main__":
    main()
