import pytest


def test_installer_creates_clickable_native_desktop_entry(tmp_path):
    from dashpi.desktop_install import install_launcher

    applications = tmp_path / "data" / "applications"
    desktop = tmp_path / "Desktop"
    installed = install_launcher(applications, desktop, tmp_path / "bin" / "dashpi-app")

    assert installed == desktop / "DashPi.desktop"
    content = installed.read_text()
    assert (applications / "DashPi.desktop").read_text() == content
    assert "Type=Application" in content
    assert f"Exec={tmp_path / 'bin' / 'python'} -m dashpi.desktop" in content
    assert "Terminal=false" in content
    assert "Chromium" not in content
    icon = tmp_path / "data" / "icons" / "hicolor" / "scalable" / "apps" / "dashpi.svg"
    assert icon.is_file() and icon.stat().st_size > 100
    assert f"Icon={icon}" in content
    assert installed.stat().st_mode & 0o111


def test_installer_does_not_replace_unmanaged_desktop_entry(tmp_path):
    from dashpi.desktop_install import install_launcher

    applications = tmp_path / "data" / "applications"
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    existing = desktop / "DashPi.desktop"
    existing.write_text("user customization")

    with pytest.raises(FileExistsError):
        install_launcher(applications, desktop, tmp_path / "bin" / "dashpi-app")
    assert existing.read_text() == "user customization"
