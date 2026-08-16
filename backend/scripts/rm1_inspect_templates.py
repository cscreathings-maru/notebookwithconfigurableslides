"""RM-1 spike — inventory every layout in every uploaded template's .pptx.

Throwaway, operational-only (not part of `src/deck/`): answers the one open
question that gates the monolith-renderer plan
(`revamp/ASSESSMENT-ARCHITECTURE-2026-08-15.md` §5.4, `revamp/PLAN-MONOLITH-RENDERER.md`
RM-1) — do the real templates carry real placeholders python-pptx can fill, or
are they static text boxes with nothing to inspect?

Usage (inside the orchestrator container):
    python -m scripts.rm1_inspect_templates

Reads every Template row with a source_pptx_uri, downloads it from the object
store, prints placeholder geometry for every slide-master layout, and writes a
JSON report plus a copy of each inspected .pptx to /tmp/rm1-templates/ — pull
both off the container with the `docker compose cp` command it prints at the end.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from pptx import Presentation

from src.core.db import SessionLocal
from src.models import Template
from src.storage.object_store import get_object_store

OUT_DIR = Path("/tmp/rm1-templates")


def _in_or_none(length) -> float | None:
    """python-pptx returns `Length` (EMU) objects with a `.inches` property, or
    None when a placeholder inherits geometry from the master rather than
    setting its own — which is itself a finding worth seeing, not an error."""
    return round(length.inches, 2) if length is not None else None


def inspect_one(*, name: str, version: int, data: bytes) -> dict:
    prs = Presentation(io.BytesIO(data))
    masters = []
    for m_idx, master in enumerate(prs.slide_masters):
        layouts = []
        for l_idx, layout in enumerate(master.slide_layouts):
            placeholders = [
                {
                    "idx": ph.placeholder_format.idx,
                    "type": str(ph.placeholder_format.type),
                    "name": ph.name,
                    "left_in": _in_or_none(ph.left),
                    "top_in": _in_or_none(ph.top),
                    "width_in": _in_or_none(ph.width),
                    "height_in": _in_or_none(ph.height),
                }
                for ph in layout.placeholders
            ]
            static_shapes = sum(1 for sh in layout.shapes if not sh.is_placeholder)
            layouts.append(
                {
                    "layout_index": l_idx,
                    "layout_name": layout.name,
                    "placeholder_count": len(placeholders),
                    "placeholders": placeholders,
                    "static_shape_count": static_shapes,
                }
            )
        masters.append(
            {
                "master_index": m_idx,
                "master_name": master.name,
                "layout_count": len(layouts),
                "layouts": layouts,
            }
        )
    return {
        "template": name,
        "version": version,
        "slide_width_in": _in_or_none(prs.slide_width),
        "slide_height_in": _in_or_none(prs.slide_height),
        "master_count": len(masters),
        "masters": masters,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    store = get_object_store()
    results: list[dict] = []

    with SessionLocal() as db:
        rows = (
            db.query(Template)
            .filter(Template.source_pptx_uri.isnot(None))
            .order_by(Template.logical_id, Template.version)
            .all()
        )
        if not rows:
            print("No Template rows with a source_pptx_uri found. Nothing to inspect.")
            return

        for row in rows:
            print(f"--- {row.name} v{row.version} ({row.source_pptx_uri}) ---")
            try:
                data = store.get_bytes(key=row.source_pptx_uri)
            except Exception as exc:
                print(f"  FAILED to fetch: {type(exc).__name__}: {exc}")
                continue

            safe_name = row.name.replace("/", "_").replace(" ", "_")
            local_path = OUT_DIR / f"{safe_name}_v{row.version}.pptx"
            local_path.write_bytes(data)
            print(f"  saved -> {local_path} ({len(data)} bytes)")

            try:
                report = inspect_one(name=row.name, version=row.version, data=data)
            except Exception as exc:
                print(f"  FAILED to open as pptx: {type(exc).__name__}: {exc}")
                continue

            results.append(report)
            usable = [
                layout
                for m in report["masters"]
                for layout in m["layouts"]
                if layout["placeholder_count"] > 0
            ]
            total_layouts = sum(m["layout_count"] for m in report["masters"])
            print(
                f"  masters={report['master_count']} total_layouts={total_layouts} "
                f"layouts_with_placeholders={len(usable)}"
            )

    out_json = OUT_DIR / "rm1-inspection-report.json"
    out_json.write_text(json.dumps(results, indent=2))
    print(f"\nFull report -> {out_json}")
    print("Pull both the report and the .pptx fixtures off the container with:")
    print(
        "  docker compose -f deploy/docker-compose.lite.yml --env-file deploy/.env.lite "
        f"cp orchestrator:{OUT_DIR} ./revamp/rm1-templates"
    )


if __name__ == "__main__":
    main()
