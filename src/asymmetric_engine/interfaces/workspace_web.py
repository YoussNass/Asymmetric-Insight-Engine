"""Dependency-free local browser workspace over Chapter 9A/9B contracts."""

from __future__ import annotations

import html
import json
import secrets
from collections.abc import Iterable
from io import BytesIO
from typing import Any, cast
from urllib.parse import parse_qs
from uuid import UUID
from wsgiref.simple_server import make_server

from pydantic import ValidationError

from asymmetric_engine.application.product_persistence import LoadedProductRecord
from asymmetric_engine.domain.execution import ExecutionPlan
from asymmetric_engine.domain.portfolio import PositionReview, ReplacementDecision
from asymmetric_engine.interfaces.decision_card import ProjectDecisionCard
from asymmetric_engine.interfaces.execution_card import ProjectExecutionCard
from asymmetric_engine.interfaces.operator_workspace import (
    WORKSPACE_CONTRACT_VERSION,
    OperatorWorkspace,
    UnknownWorkspaceOperation,
    WorkspaceRecordSummary,
    WorkspaceWriteUnavailable,
    workspace_submission_json,
)

MAX_REQUEST_BYTES = 2_000_000
LOCAL_WORKSPACE_HOST = "127.0.0.1"
DEFAULT_WORKSPACE_PORT = 8765
WRITE_TOKEN_HEADER = "HTTP_X_AIE_WORKSPACE_TOKEN"

type StartResponse = Any
type WsgiEnviron = dict[str, Any]
type WsgiBody = Iterable[bytes]


class WorkspaceWriteTokenError(PermissionError):
    """A write-enabled local request lacks the server-generated token."""


def _response(
    start_response: StartResponse,
    status: str,
    body: str,
    *,
    content_type: str,
) -> WsgiBody:
    encoded = body.encode("utf-8")
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(encoded))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if content_type.startswith("text/html"):
        headers.extend(
            [
                ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"),
                ("X-Frame-Options", "DENY"),
            ]
        )
    start_response(status, headers)
    return [encoded]


def _json_response(
    start_response: StartResponse,
    status: str,
    payload: dict[str, Any],
) -> WsgiBody:
    return _response(
        start_response,
        status,
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
        content_type="application/json; charset=utf-8",
    )


def _html_response(start_response: StartResponse, status: str, body: str) -> WsgiBody:
    return _response(
        start_response,
        status,
        body,
        content_type="text/html; charset=utf-8",
    )


def _layout(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body {{ max-width: 1180px; margin: auto; padding: 24px; font-family: system-ui; }}
table {{ border-collapse: collapse; width: 100%; }}
th,td {{ text-align: left; border-bottom: 1px solid #8886; padding: 8px; }}
pre,textarea {{ white-space: pre-wrap; overflow-wrap: anywhere; width: 100%; }}
.notice {{ border-left: 4px solid currentColor; padding: 8px 12px; margin: 16px 0; }}
</style></head><body>
<h1>Asymmetric Insight Engine</h1><p>{WORKSPACE_CONTRACT_VERSION}</p>{content}
</body></html>"""


def _summary_rows(records: tuple[WorkspaceRecordSummary, ...]) -> str:
    if not records:
        return '<tr><td colspan="5">No persisted records.</td></tr>'
    return "".join(
        "<tr>"
        f'<td><a href="/records/{record.record_id}">{html.escape(record.kind.value)}</a></td>'
        f"<td>{html.escape(record.record_type)}</td>"
        f"<td><code>{record.record_id}</code></td>"
        f"<td>{html.escape(record.stored_at)}</td>"
        f"<td><code>{html.escape(record.payload_sha256[:16])}…</code></td>"
        "</tr>"
        for record in records
    )


def render_workspace_index(
    workspace: OperatorWorkspace,
    *,
    write_token: str | None = None,
) -> str:
    records = workspace.list_records()
    write_panel = ""
    if workspace.write_enabled:
        if not write_token:
            raise WorkspaceWriteTokenError("write-enabled browser workspace requires a token")
        options = "".join(
            f'<option value="{html.escape(operation)}">{html.escape(operation)}</option>'
            for operation in (
                "build_portfolio_state",
                "build_portfolio_exposure",
                "build_marginal_decision",
                "record_position_hold",
                "build_owner_portfolio_policy",
                "apply_portfolio_policy",
                "build_replacement_decision",
                "build_execution_policy",
                "build_execution_from_policy_allocation",
                "build_execution_from_replacement",
                "open_learning_case_from_policy_allocation",
                "open_learning_case_from_replacement",
                "build_learning_evaluation",
            )
        )
        write_panel = f"""<h2>Submit strict AIE request</h2>
<form method="post" action="/submit">
<input type="hidden" name="write_token" value="{html.escape(write_token, quote=True)}">
<select name="operation">{options}</select>
<textarea name="payload" required></textarea>
<button type="submit">Invoke canonical use case and persist output</button></form>"""
    return _layout(
        "AIE Operator Workspace",
        f"""<h2>Persisted canonical records</h2>
<div class="notice">Storage verification is not financial replay.</div>
<table><thead><tr><th>Kind</th><th>Type</th><th>Storage ID</th>
<th>First stored</th><th>SHA-256</th></tr></thead>
<tbody>{_summary_rows(records)}</tbody></table>{write_panel}""",
    )


def _projection(record: LoadedProductRecord) -> tuple[str, dict[str, Any]] | None:
    canonical = record.record
    if isinstance(canonical, ExecutionPlan):
        return (
            "Execution Card",
            ProjectExecutionCard.from_execution_plan(canonical).model_dump(mode="json"),
        )
    if isinstance(canonical, ReplacementDecision):
        return (
            "Decision Card",
            ProjectDecisionCard.from_replacement_decision(canonical).model_dump(mode="json"),
        )
    if isinstance(canonical, PositionReview):
        return (
            "Decision Card",
            ProjectDecisionCard.from_position_review(canonical).model_dump(mode="json"),
        )
    return None


def render_record_detail(record: LoadedProductRecord) -> str:
    canonical_json = json.dumps(
        record.record.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    projection = _projection(record)
    projection_html = ""
    if projection is not None:
        label, payload = projection
        projection_html = (
            f"<h2>{html.escape(label)}</h2>"
            f"<pre>{html.escape(json.dumps(payload, indent=2, sort_keys=True))}</pre>"
        )
    envelope = record.envelope
    return _layout(
        f"AIE {envelope.kind.value}",
        f"""<p><a href="/">← All records</a></p><h2>{html.escape(envelope.kind.value)}</h2>
<p>Storage ID: <code>{envelope.record_id}</code></p>
<p>First stored: {html.escape(envelope.stored_at.isoformat())}</p>
<p>SHA-256: <code>{html.escape(envelope.payload_sha256)}</code></p>
<div class="notice">Downstream use still requires canonical application replay.</div>
{projection_html}<h2>Canonical record</h2><pre>{html.escape(canonical_json)}</pre>""",
    )


def render_submission_result(submission_json: str) -> str:
    parsed = json.loads(submission_json)
    links = "".join(
        f'<li><a href="/records/{item["record_id"]}">{html.escape(item["kind"])}</a> '
        f"({html.escape(item['status'])})</li>"
        for item in parsed["persisted"]
    )
    response = json.dumps(parsed["response"], ensure_ascii=False, indent=2, sort_keys=True)
    return _layout(
        "AIE workspace submission",
        f"<p><a href='/'>← Workspace</a></p><ul>{links}</ul><pre>{html.escape(response)}</pre>",
    )


class WorkspaceWsgiApp:
    def __init__(
        self,
        workspace: OperatorWorkspace,
        *,
        write_token: str | None = None,
    ) -> None:
        if workspace.write_enabled and not write_token:
            raise WorkspaceWriteTokenError("write-enabled WSGI workspace requires a token")
        self._workspace = workspace
        self._write_token = write_token

    def __call__(self, environ: WsgiEnviron, start_response: StartResponse) -> WsgiBody:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        try:
            if method == "GET" and path == "/":
                body = render_workspace_index(
                    self._workspace,
                    write_token=self._write_token,
                )
                return _html_response(start_response, "200 OK", body)
            if method == "GET" and path.startswith("/records/"):
                record_id = UUID(path.removeprefix("/records/"))
                body = render_record_detail(self._workspace.load_record(record_id))
                return _html_response(start_response, "200 OK", body)
            if method == "POST" and path == "/submit":
                operation, payload, token = self._form_submission(environ)
                self._require_write_token(token)
                submission = self._workspace.submit_json(operation, payload)
                body = render_submission_result(workspace_submission_json(submission))
                return _html_response(start_response, "201 Created", body)
            if method == "POST" and path.startswith("/operations/"):
                self._require_write_token(str(environ.get(WRITE_TOKEN_HEADER, "")))
                operation = path.removeprefix("/operations/")
                payload = self._read_body(environ).decode("utf-8")
                submission = self._workspace.submit_json(operation, payload)
                return _json_response(
                    start_response,
                    "201 Created",
                    json.loads(workspace_submission_json(submission)),
                )
        except ValidationError as exc:
            return _json_response(
                start_response,
                "400 Bad Request",
                {"blocking": True, "error": "ValidationError", "fields": exc.errors()},
            )
        except (UnknownWorkspaceOperation, KeyError) as exc:
            return _json_response(
                start_response,
                "404 Not Found",
                {"blocking": True, "error": type(exc).__name__, "message": str(exc)},
            )
        except (WorkspaceWriteUnavailable, WorkspaceWriteTokenError) as exc:
            return _json_response(
                start_response,
                "403 Forbidden",
                {"blocking": True, "error": type(exc).__name__, "message": str(exc)},
            )
        except (UnicodeDecodeError, ValueError) as exc:
            return _json_response(
                start_response,
                "409 Conflict",
                {"blocking": True, "error": type(exc).__name__, "message": str(exc)},
            )
        return _json_response(
            start_response,
            "404 Not Found",
            {"blocking": True, "error": "NotFound", "message": "workspace route not found"},
        )

    def _require_write_token(self, supplied: str) -> None:
        expected = self._write_token
        if expected is None or not secrets.compare_digest(supplied, expected):
            raise WorkspaceWriteTokenError("workspace write token is missing or invalid")

    @staticmethod
    def _read_body(environ: WsgiEnviron) -> bytes:
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "0") or "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("workspace request body exceeds admitted size")
        stream = cast(Any, environ.get("wsgi.input", BytesIO()))
        body = stream.read(length)
        if not isinstance(body, bytes):
            raise ValueError("workspace request body must be bytes")
        return body

    @classmethod
    def _form_submission(cls, environ: WsgiEnviron) -> tuple[str, str, str]:
        fields = parse_qs(
            cls._read_body(environ).decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
        )
        operation = fields.get("operation", [""])[0].strip()
        payload = fields.get("payload", [""])[0]
        token = fields.get("write_token", [""])[0]
        if not operation or not payload.strip():
            raise ValueError("operation and payload are required")
        return operation, payload, token


def serve_local_workspace(
    workspace: OperatorWorkspace,
    *,
    port: int = DEFAULT_WORKSPACE_PORT,
) -> None:
    if not 1 <= port <= 65535:
        raise ValueError("workspace port must be between 1 and 65535")
    write_token = secrets.token_urlsafe(32) if workspace.write_enabled else None
    app = WorkspaceWsgiApp(workspace, write_token=write_token)
    with make_server(LOCAL_WORKSPACE_HOST, port, app) as server:
        server.serve_forever()


__all__ = [
    "DEFAULT_WORKSPACE_PORT",
    "LOCAL_WORKSPACE_HOST",
    "MAX_REQUEST_BYTES",
    "WRITE_TOKEN_HEADER",
    "WorkspaceWriteTokenError",
    "WorkspaceWsgiApp",
    "render_record_detail",
    "render_submission_result",
    "render_workspace_index",
    "serve_local_workspace",
]
