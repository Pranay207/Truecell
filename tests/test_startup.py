"""Launcher errors remain actionable instead of producing socket tracebacks."""

import argparse

import pytest

import run as launcher
from scripts import bootstrap


@pytest.mark.parametrize("value", ["0", "-1", "65536"])
def test_launcher_rejects_ports_outside_tcp_range(value):
    with pytest.raises(argparse.ArgumentTypeError, match="between 1 and 65535"):
        bootstrap.port_number(value)


def test_port_scan_stops_at_last_tcp_port(monkeypatch):
    attempted = []

    class OccupiedSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            attempted.append(address[1])
            raise OSError("Already occupied")

    monkeypatch.setattr(bootstrap.socket, "socket", OccupiedSocket)
    assert bootstrap.available_port(65535) is None
    assert attempted == [65535]


def test_port_scan_uses_wildcard_binding_for_lan(monkeypatch):
    attempted = []

    class AvailableSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def bind(self, address):
            attempted.append(address)

    monkeypatch.setattr(bootstrap.socket, "socket", AvailableSocket)
    assert bootstrap.available_port(8501, "0.0.0.0") == 8501
    assert attempted == [("0.0.0.0", 8501)]


def test_modern_lan_launch_uses_exact_discovered_host(monkeypatch):
    captured = {}

    def fake_call(command, **options):
        captured["command"] = command
        captured["options"] = options
        return 0

    monkeypatch.setattr(launcher, "discover_lan_address", lambda: "192.168.20.15")
    monkeypatch.setattr(launcher.subprocess, "call", fake_call)
    assert launcher.modern(8501, no_browser=True, lan=True) == 0
    command = captured["command"]
    assert command[command.index("--host") + 1] == "0.0.0.0"
    assert "--no-proxy-headers" in command
    assert captured["options"]["env"]["TRUECELL_LAN_HOST"] == "192.168.20.15"


def test_modern_lan_launch_fails_without_private_address(monkeypatch):
    monkeypatch.setattr(launcher, "discover_lan_address", lambda: None)
    monkeypatch.setattr(
        launcher.subprocess,
        "call",
        lambda *args, **kwargs: pytest.fail("server must not start without a private address"),
    )
    assert launcher.modern(8501, no_browser=True, lan=True) == 2
