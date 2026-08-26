"""Command-line interface tests."""

from __future__ import annotations

import json
import sqlite3
from email.message import Message
from importlib.metadata import version
from pathlib import Path
from urllib.request import Request
from uuid import UUID

import pytest

from asymmetric_engine import __version__
from asymmetric_engine.application.evidence_operations import IngestSourceDocuments
from asymmetric_engine.cli import doctor_payload, main
from asymmetric_engine.infrastructure.persistence.sqlite_evidence_ledger import TABLE_NAME
from asymmetric_engine.infrastructure.providers import sec_edgar

SEC_REFERENCE = "0000320193/0000320193-24-000123"


class FakeSecResponse:
    def __init__(self) -> None:
        self.content = (
            b"<SEC-DOCUMENT>"
            b"\n<ACCESSION-NUMBER>0000320193-24-000123"
            b"\n<CONFORMED-SUBMISSION-TYPE>10-K"
            b"\n<CONFORMED-PERIOD-OF-REPORT>20240928"
            b"\n<FILER><COMPANY-DATA>"
            b"\n<COMPANY-CONFORMED-NAME>Example Corp"
            b"\n<CENTRAL-INDEX-KEY>0000320193"
            b"\n</COMPANY-DATA></FILER>"
            b"\n<DOCUMENT>exact filing bytes</DOCUMENT>"
            b"\n</SEC-DOCUMENT>"
        )
        self.headers = Message()
        self.headers["Content-Length"] = str(len(self.content))

    def __enter__(self) -> FakeSecResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.content[:limit]

    def geturl(self) -> str:
        return "https://www.sec.gov/Archives/edgar/data/320193/filing.txt"


def test_package_version_comes_from_distribution_metadata() -> None:
    assert __version__ == version("asymmetric-insight-engine")


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


def test_evidence_cli_requires_declared_sec_identity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AIE_SEC_USER_AGENT", raising=False)

    exit_code = main(
        [
            "evidence",
            "ingest-sec",
            "--database",
            str(tmp_path / "ledger.sqlite3"),
            "--reference",
            SEC_REFERENCE,
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "error"
    assert "AIE_SEC_USER_AGENT" in payload["message"]


def test_evidence_cli_rejects_malformed_identity_and_ambiguous_batch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    command = [
        "evidence",
        "ingest-sec",
        "--database",
        str(database_path),
        "--reference",
        SEC_REFERENCE,
    ]
    monkeypatch.setenv("AIE_SEC_USER_AGENT", "anonymous")

    assert main(command) == 2
    malformed = json.loads(capsys.readouterr().out)
    assert malformed["error"] == "CliUsageError"
    assert "user_agent" in malformed["message"]
    assert not database_path.exists()

    monkeypatch.setenv("AIE_SEC_USER_AGENT", "AIE admin@example.com")
    assert main([*command, "--reference", SEC_REFERENCE]) == 2
    duplicated = json.loads(capsys.readouterr().out)
    assert duplicated["error"] == "CliUsageError"
    assert "duplicate" in duplicated["message"]
    assert not database_path.exists()


def test_evidence_cli_ingests_lists_reports_and_verifies_without_real_network(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("AIE_SEC_USER_AGENT", "AIE admin@example.com")

    def fake_urlopen(request: Request, timeout: float) -> FakeSecResponse:
        assert request.get_header("User-agent") == "AIE admin@example.com"
        assert timeout == 30.0
        return FakeSecResponse()

    monkeypatch.setattr(sec_edgar, "urlopen", fake_urlopen)

    assert (
        main(
            [
                "evidence",
                "ingest-sec",
                "--database",
                str(database_path),
                "--reference",
                SEC_REFERENCE,
            ]
        )
        == 0
    )
    ingestion = json.loads(capsys.readouterr().out)
    assert ingestion["succeeded"] == 1
    assert ingestion["failed"] == 0
    document_id = UUID(ingestion["outcomes"][0]["document"]["document_id"])

    boundary_arguments = [
        "--database",
        str(database_path),
        "--subject",
        "company:sec-cik-0000320193",
        "--as-of",
        "2099-01-01T00:00:00+00:00",
        "--knowledge-mode",
        "live_system_replay",
    ]
    assert main(["evidence", "list", *boundary_arguments]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert [item["document_id"] for item in listed["documents"]] == [str(document_id)]

    assert main(["evidence", "coverage", *boundary_arguments]) == 0
    coverage = json.loads(capsys.readouterr().out)
    assert coverage["total_versions"] == 1
    assert coverage["included_versions"] == 1
    assert coverage["warnings"] == ["historical_publication_time_unverified"]

    assert (
        main(
            [
                "evidence",
                "verify",
                "--database",
                str(database_path),
                "--document-id",
                str(document_id),
            ]
        )
        == 0
    )
    verification = json.loads(capsys.readouterr().out)
    assert verification["status"] == "ok"
    assert verification["hash_matches"]
    assert verification["size_matches"]

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TRIGGER evidence_source_no_update")
        connection.execute(
            f"UPDATE {TABLE_NAME} SET content = ? WHERE document_id = ?",
            (b"tampered", str(document_id)),
        )
    assert (
        main(
            [
                "evidence",
                "verify",
                "--database",
                str(database_path),
                "--document-id",
                str(document_id),
            ]
        )
        == 3
    )
    corrupted = json.loads(capsys.readouterr().out)
    assert corrupted["status"] == "corrupt"
    assert not corrupted["hash_matches"]
    assert not corrupted["size_matches"]


def test_evidence_cli_returns_machine_readable_reference_failures(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIE_SEC_USER_AGENT", "AIE admin@example.com")

    exit_code = main(
        [
            "evidence",
            "ingest-sec",
            "--database",
            str(tmp_path / "ledger.sqlite3"),
            "--reference",
            "not-a-sec-reference",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["failed"] == 1
    assert payload["outcomes"][0]["failure_kind"] == "invalid_reference"


@pytest.mark.parametrize(
    ("as_of", "message"),
    [
        ("not-a-date", "ISO-8601"),
        ("2026-08-25T18:00:00", "timezone offset"),
    ],
)
def test_evidence_cli_rejects_invalid_decision_timestamps_before_storage_access(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    as_of: str,
    message: str,
) -> None:
    database_path = tmp_path / "ledger.sqlite3"

    with pytest.raises(SystemExit) as exit_info:
        main(
            [
                "evidence",
                "list",
                "--database",
                str(database_path),
                "--subject",
                "company:sec-cik-0000320193",
                "--as-of",
                as_of,
                "--knowledge-mode",
                "historical_reconstruction",
            ]
        )

    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err
    assert not database_path.exists()


def test_evidence_cli_rejects_blank_subject_without_masking_programming_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary_arguments = [
        "--database",
        str(tmp_path / "ledger.sqlite3"),
        "--subject",
        " ",
        "--as-of",
        "2026-08-25T18:00:00+00:00",
        "--knowledge-mode",
        "historical_reconstruction",
    ]
    assert main(["evidence", "coverage", *boundary_arguments]) == 2
    blank_subject = json.loads(capsys.readouterr().out)
    assert blank_subject["error"] == "CliUsageError"
    assert "subject" in blank_subject["message"]

    missing_database = tmp_path / "missing.sqlite3"
    valid_boundary_arguments = [
        "--database",
        str(missing_database),
        "--subject",
        "company:sec-cik-0000320193",
        "--as-of",
        "2026-08-25T18:00:00+00:00",
        "--knowledge-mode",
        "historical_reconstruction",
    ]
    assert main(["evidence", "list", *valid_boundary_arguments]) == 2
    absent_database = json.loads(capsys.readouterr().out)
    assert absent_database["error"] == "CliUsageError"
    assert "does not exist" in absent_database["message"]
    assert not missing_database.exists()

    monkeypatch.setenv("AIE_SEC_USER_AGENT", "AIE admin@example.com")

    def broken_execute(*_args: object, **_kwargs: object) -> object:
        raise ValueError("unexpected implementation bug")

    monkeypatch.setattr(IngestSourceDocuments, "execute", broken_execute)
    with pytest.raises(ValueError, match="unexpected implementation bug"):
        main(
            [
                "evidence",
                "ingest-sec",
                "--database",
                str(tmp_path / "other.sqlite3"),
                "--reference",
                SEC_REFERENCE,
            ]
        )
