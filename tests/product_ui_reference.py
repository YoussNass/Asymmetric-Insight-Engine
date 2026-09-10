"""Create an isolated synthetic UI demonstration; refuse any existing destination."""

import sys
from pathlib import Path

from tests.product_ui_factories import make_product_ui_runtime


def create_reference(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    _, service, request = make_product_ui_runtime(directory)
    service.submit(request.model_dump_json())
    (directory / "new-capital.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")
    print(f"Synthetic reference dossiers created in {directory}. Use --reference-data in the UI.")


if __name__ == "__main__":
    create_reference(Path(sys.argv[1]))
