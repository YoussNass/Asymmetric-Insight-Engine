"""Dependency-free local browser workspace over Chapter 9A/9B contracts."""

from __future__ import annotations

import html
import json
import secrets
from collections.abc import Iterable
from io import BytesIO
from typing import Any, Protocol
from urllib.parse import parse_qs
from uuid import UUID
from wsgiref.simple_server import make_server

from pydantic import ValidationError

from asymmetric_engine.application.product_persistence import (
    LoadedProductRecord,
)
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


class StartResponse(Protocol):
    def __call__(
        self,
        status: str,
        headers: list[tuple[str, str]],
        exc_info: object | None = None,
    ) -> object: ...


WsgiEnviron = dict[str, Any]
WsgiBody = Iterable[bytes]


class WorkspaceWriteTokenError(PermissionError):
    """Raised when a write-enabled local browser request lacks the server-generated token."""


def _json_response(
    start_response: StartResponse,
    status: str,
    payload: dict[str, Any],
) -> WsgiBody:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ],
    )
    return [body]


def _html_response(start_response: StartResponse, status: str, body_html: str) -> WsgiBody:
    body = body_html.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'"),
            ("X-Content-Type-Options", "nosniff"),
            ("X-Frame-Options", "DENY"),
        ],
    )
    return [body]


def _layout(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ font-family: ui-sans-serif, system-ui, sans-serif; color-scheme: light dark; }}
body {{ max-width: 1180px; margin: 0 auto; padding: 24px; line-height: 1.45; }}
a {{ color: inherit; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; vertical-align: top; border-bottom: 1px solid #8886; padding: 8px; }}
code, pre, textarea {{ font-family: ui-monospace, SFMono-Regular, monospace; }}
pre {{ white-space: pre-wrap; overflow-wrap: anywhere; border: 1px solid #8886; padding: 12px; }}
textarea {{ width: 100%; min-height: 260px; }}
select, button, textarea {{ font: inherit; padding: 8px; }}
.notice {{ border-left: 4px solid currentColor; padding: 8px 12px; margin: 16px 0; }}
.meta {{ opacity: .8; }}
</style>
</head>
<body>
<header><h1>Asymmetric Insight Engine</h1><p class="meta">{WORKSPACE_CONTRACT_VERSION}</p></header>
{content}
</body>
</html>"""


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
    """Render a persisted-record navigator and optional strict API submission surface."""

    records = workspace.list_records()
    write_panel = ""
    if workspace.write_enabled:
        if not write_token:
            raise WorkspaceWriteTokenError(
                "write-enabled browser workspace requires a non-empty local write token"
            )
        options = "".join(
            f'<option value="{html.escape(value)}">{html.escape(value)}</option>'
            for value in (
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
        escaped_token = html.escape(write_token, quote=True)
        write_panel = f"""
<section>
<h2>Submit strict AIE request</h2>
<div class="notice">The workspace does not calculate or repair fields. Paste one complete
<code>aie-api-v1</code> request. Validation and canonical replay failures are blocking.</div>
<form method="post" action="/submit">
<input type="hidden" name="write_token" value="{escaped_token}">
<label>Operation <select name="operation">{options}</select></label>
<p><label>Request JSON<textarea name="payload" required></textarea></label></p>
<button type="submit">Invoke canonical use case and persist output</button>
</form>
</section>"""

    return _layout(
        "AIE Operator Workspace",
        f"""
<section>
<h2>Persisted canonical records</h2>
<div class="notice">Storage verification is not financial replay. A loaded decision record must
still pass its canonical application verification before it can influence another decision.</div>
<table>
<thead><tr><th>Kind</th><th>Type</th><th>Storage ID</th><th>First stored</th><th>SHA-256</th></tr></thead>
<tbody>{_summary_rows(records)}</tbody>
</table>
</section>
{write_panel}
""",
    )


def _projection(record: LoadedProductRecord) -> tuple[str, dict[str, Any]] | None:
    canonical = record.record
    if isinstance(canonical, ExecutionPlan):
        card = ProjectExecutionCard.from_execution_plan(canonical)
        return "Execution Card", card.model_dump(mode="json")
    if isinstance(canonical, ReplacementDecision):
        card = ProjectDecisionCard.from_replacement_decision(canonical)
        return "Decision Card", card.model_dump(mode="json")
    if isinstance(canonical, PositionReview):
        card = ProjectDecisionCard.from_position_review(canonical)
        return "Decision Card", card.model_dump(mode="json")
    return None


def render_record_detail(record: LoadedProductRecord) -> str:
    """Render exact persisted content and existing read-only projections without recalculation."""

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
        projection_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        projection_html = (
            f"<section><h2>{html.escape(label)}</h2>"
            f"<pre>{html.escape(projection_json)}</pre></section>"
        )
    return _layout(
        f"AIE {record.envelope.kind.value}",
        f"""
<p><a href="/">← All records</a></p>
<h2>{html.escape(record.envelope.kind.value)}</h2>
<dl>
<dt>Storage ID</dt><dd><code>{record.envelope.record_id}</code></dd>
<dt>Schema</dt><dd>{html.escape(record.envelope.schema_version)}</dd>
<dt>First stored</dt><dd>{html.escape(record.envelope.stored_at.isoformat())}</dd>
<dt>SHA-256</dt><dd><code>{html.escape(record.envelope.payload_sha256)}</code></dd>
</dl>
<div class="notice">This page proves storage verification only. Downstream decision use still
requires the canonical application replay owned by the relevant AIE capability.</div>
{projection_html}
<section><h2>Canonical record</h2><pre>{html.escape(canonical_json)}</pre></section>
""",
    )


def render_submission_result(submission_json: str) -> str:
    parsed = json.loads(submission_json)
    links = "".join(
        f'<li><a href="/records/{item["record_id"]}">{html.escape(item["kind"])}</a> '
        f'({html.escape(item["status"])})</li>'
        for item in parsed["persisted"]
    )
    pretty = json.dumps(parsed["response"], ensure_ascii=False, indent=2, sort_keys=True)
    return _layout(
        "AIE workspace submission",
        f"""
<p><a href="/">← Workspace</a></p>
<h2>Canonical operation completed</h2>
<ul>{links}</ul>
<h3>Exact API response</h3>
<pre>{html.escape(pretty)}</pre>
""",
    )


class WorkspaceWsgiApp:
    """Small local-capable WSGI surface; service composition remains injected."""

    def __init__(
        self,
        workspace: OperatorWorkspace,
        *,
        write_token: str | None = None,
    ) -> None:
        if workspace.write_enabled and not write_token:
            raise WorkspaceWriteTokenError(
                "write-enabled WSGI workspace requires a non-empty local write token"
            )
        self._workspace = workspace
        self._write_token = write_token

    def __call__(self, environ: WsgiEnviron, start_response: StartResponse) -> WsgiBody:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        try:
            if method == "GET" and path == "/":
                return _html_response(
                    start_response,
                    "200 OK",
                    render_workspace_index(
                        self._workspace,
                        write_token=self._write_token,
                    ),
                )
            if method == "GET" and path.startswith("/records/"):
                record_id = UUID(path.removeprefix("/records/"))
                record = self._workspace.load_record(record_id)
                return _html_response(
                    start_response,
                    "200 OK",
                    render_record_detail(record),
                )
            if method == "POST" and path == "/submit":
                operation, payload_json, submitted_token = self._form_submission(environ)
                self._require_write_token(submitted_token)
                submission = self._workspace.submit_json(operation, payload_json)
                return _html_response(
                    start_response,
                    "201 Created",
                    render_submission_result(workspace_submission_json(submission)),
                )
            if method == "POST" and path.startswith("/operations/"):
                self._require_write_token(str(environ.get(WRITE_TOKEN_HEADER, "")))
                operation = path.removeprefix("/operations/")
                payload_json = self._read_body(environ).decode("utf-8")
                submission = self._workspace.submit_json(operation, payload_json)
                return _json_response(
                    start_response,
                    "201 Created",
                    json.loads(workspace_submission_json(submission)),
                )
        except ValidationError as exc:
            return _json_response(
                start_response,
                "400 Bad Request",
                {
                    "blocking": True,
                    "error": "ValidationError",
                    "fields": exc.errors(include_url=False),
                },
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
        raw_length = str(environ.get("CONTENT_LENGTH", "0") or "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("workspace request body exceeds admitted size")
        stream = environ.get("wsgi.input")
        if not hasattr(stream, "read"):
            stream = BytesIO()
        body = stream.read(length)
        if not isinstance(body, bytes):
            raise ValueError("workspace request body must be bytes")
        return body

    @classmethod
    def _form_submission(cls, environ: WsgiEnviron) -> tuple[str, str, str]:
        body = cls._read_body(environ).decode("utf-8")
        fields = parse_qs(body, keep_blank_values=True, strict_parsing=True)
        operation = fields.get("operation", [""])[0].strip()
        payload_json = fields.get("payload", [""])[0]
        write_token = fields.get("write_token", [""])[0]
        if not operation or not payload_json.strip():
            raise ValueError("operation and payload are required")
        return operation, payload_json, write_token


def serve_local_workspace(
    workspace: OperatorWorkspace,
    *,
    port: int = DEFAULT_WORKSPACE_PORT,
) -> None:
    """Serve only on IPv4 loopback; this is not an authenticated remote deployment."""

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
