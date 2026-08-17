"""Command-line interface tests."""

import json

import pytest

from asymmetric_engine import __version__
from asymmetric_engine.cli import doctor_payload, main


def test_doctor_payload_is_machine_readable() -> None:
    payload = doctor_payload()

    assert payload["status"] == "ok"
    assert payload["version"] == __version__


def test_doctor_command_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["package"] == "asymmetric-insight-engine"


def test_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__
