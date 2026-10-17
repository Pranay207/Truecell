"""The frozen launcher keeps resources, user data and networking predictable."""

from pathlib import Path

import pytest

from portable import launcher


def test_source_resource_and_application_roots_are_project_root(monkeypatch):
    monkeypatch.delattr(launcher.sys, "_MEIPASS", raising=False)
    monkeypatch.delattr(launcher.sys, "frozen", raising=False)
    monkeypatch.delenv("TRUECELL_PORTABLE_ROOT", raising=False)
    expected = Path(launcher.__file__).resolve().parents[1]
    assert launcher.resource_root() == expected
    assert launcher.application_root() == expected


def test_portable_root_override_supports_paths_with_spaces(monkeypatch, tmp_path):
    target = tmp_path / "Truecell Portable Copy"
    monkeypatch.setenv("TRUECELL_PORTABLE_ROOT", str(target))
    assert launcher.application_root() == target.resolve()


def test_port_scan_is_bounded(monkeypatch):
    attempted = []

    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            attempted.append(address)
            raise OSError("occupied")

    monkeypatch.setattr(launcher.socket, "socket", OccupiedSocket)
    assert launcher.available_port(65534, "127.0.0.1") is None
    assert attempted == [("127.0.0.1", 65534), ("127.0.0.1", 65535)]


def test_incomplete_portable_copy_fails_before_starting_server(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(launcher, "resource_root", lambda: tmp_path)
    monkeypatch.setattr(launcher, "application_root", lambda: tmp_path)
    assert launcher.main(["--no-browser"]) == 2
    assert "Extract the entire ZIP" in capsys.readouterr().out


def test_portable_app_disables_external_tesseract(monkeypatch, tmp_path):
    captured = {}

    def fake_create_app(**options):
        captured.update(options)
        return object()

    monkeypatch.setattr("truecell.api.create_app", fake_create_app)
    app = launcher.create_portable_app(tmp_path / "data", tmp_path / "resources")
    assert app is not None
    assert launcher.os.environ["TRUECELL_PORTABLE_RAPIDOCR_ONLY"] == "1"
    assert captured["root"] == tmp_path / "data" / "jobs"


@pytest.mark.parametrize("port", [0, 65536])
def test_portable_launcher_rejects_invalid_ports(port):
    with pytest.raises(SystemExit):
        launcher.main(["--port", str(port), "--no-browser"])
