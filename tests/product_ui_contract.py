"""Export real Python adapter responses for TypeScript contract-drift tests."""

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from asymmetric_engine.interfaces.product_ui import PRODUCT_UI_VERSION
from tests.product_ui_factories import make_product_ui_runtime


def export(destination: Path) -> None:
    with TemporaryDirectory() as directory:
        _, service, request = make_product_ui_runtime(Path(directory))
        service.submit(request.model_dump_json())
        summaries = service.records()
        kinds = {"opportunity_state", "portfolio_state", "marginal_decision"}
        details = [
            {"contract_version": PRODUCT_UI_VERSION, **service.detail(UUID(summary["record_id"]))}
            for summary in summaries
            if summary["kind"] in kinds
        ]
        destination.write_text(
            json.dumps({"records": summaries, "details": details}), encoding="utf-8"
        )


if __name__ == "__main__":
    export(Path(sys.argv[1]))
