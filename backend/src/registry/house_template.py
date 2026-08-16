"""The bundled starting template (RM-15).

A template is mandatory: `deck/renderer.py` clones a real template's own
designed slides or renders nothing, and there is no stock theme to fall back
on. Without a seeded one, a fresh install is a dead end -- an author opens
Studio, finds an empty picker, and can generate nothing until an admin
uploads a `.pptx`, catalogues it, and reviews the catalog.

Seeding one removes that cliff without weakening the rule: the house
template is a real, catalogued template like any other, not a special case
in the renderer. It still needs a human to review its catalog before
`GenerationService.create` will plan against it (L3) -- seeding gets it as
far as `catalog_status: "cataloguing"`, not further; that review step is
deliberately not automated (Phase A's `PHASE-A-REPORT.md` §7 F1 named this
gap, closed here by enqueuing the SAME job an upload triggers, not by
skipping the review).

Idempotent by NAME within a tenant, so re-running the seeder (which happens on
every deploy) neither duplicates it nor overwrites a version the workspace has
since replaced.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..models import Job, JobStatus, JobType, RegistryStatus, Template, TemplateCatalogStatus
from ..storage.object_store import ObjectStore

logger = get_logger("orchestrator.registry.house_template")

HOUSE_TEMPLATE_NAME = "BRI Default"
HOUSE_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "assets" / "templates" / "bri-default.pptx"


def seed_house_template(
    *, db: Session, tenant_id: uuid.UUID, object_store: ObjectStore, created_by: uuid.UUID | None = None
) -> Template | None:
    """Install the bundled template for `tenant_id`, or return None if it is
    already there (or the asset is missing).

    A missing asset is a warning, not a crash: the seeder runs as an `init`
    container gating the whole stack's startup, and a stack that refuses to
    boot over an optional convenience template would be a worse failure than
    the empty picker this exists to avoid.

    Cataloguing is enqueued the same way `TemplateService.create` does it
    (LD-3) -- an LLM call belongs in a job, never inline in a sync seed
    script. The job row is created directly here rather than dispatched
    through a live Arq connection (this script runs before the worker is
    necessarily up): `workers/settings.py::_on_startup`'s stranded-job
    reconciler already re-enqueues any `queued`, never-attempted `Job` row on
    worker boot, which is exactly this row's state -- no separate dispatch
    path needed.
    """
    existing = (
        db.query(Template)
        .filter(Template.tenant_id == tenant_id, Template.name == HOUSE_TEMPLATE_NAME)
        .first()
    )
    if existing is not None:
        logger.info("house_template_already_present", extra={"template_id": str(existing.logical_id)})
        return None

    if not HOUSE_TEMPLATE_PATH.exists():
        logger.warning("house_template_asset_missing", extra={"path": str(HOUSE_TEMPLATE_PATH)})
        return None

    pptx_bytes = HOUSE_TEMPLATE_PATH.read_bytes()
    logical_id = uuid.uuid4()
    key = object_store.tenant_key(
        tenant_id=tenant_id.hex,
        project_id="templates",
        source_id=logical_id.hex,
        filename="bri-default.pptx",
    )
    object_store.put_bytes(
        key=key,
        data=pptx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )

    template = Template(
        logical_id=logical_id,
        version=1,
        tenant_id=tenant_id,
        name=HOUSE_TEMPLATE_NAME,
        source_pptx_uri=key,
        brand_tokens={},
        status=RegistryStatus.draft,
        catalog_status=TemplateCatalogStatus.cataloguing,
        created_by=created_by,
    )
    db.add(template)
    db.flush()

    job = Job(
        tenant_id=tenant_id,
        type=JobType.catalog_template,
        ref_id=template.id,
        status=JobStatus.queued,
        attempts=0,
        idempotency_key=f"catalog_template:{template.id}",
        progress={"step": "queued", "percent": 0},
    )
    db.add(job)
    db.flush()

    logger.info(
        "house_template_seeded",
        extra={"template_id": str(logical_id), "catalog_job_id": str(job.id)},
    )
    return template
