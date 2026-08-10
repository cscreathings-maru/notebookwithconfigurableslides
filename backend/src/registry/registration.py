"""Template registration worker (TM-2) — drives one template to a terminal state.

Mirrors `ingestion/service.py::ingest_source` and `generation/worker.py`: a standalone
async function, not a service method, invoked by the Arq task
(`workers/tasks.py::run_register_template`) with its own collaborators, and just as
easily invoked directly in tests without a queue.

Idempotent: a template that already reached a terminal state (`registered`/
`failed`/`no_source`) is a no-op, same discipline as `ingest_source` and
`generate_presentation`.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..core.logging import get_logger
from ..models import RegistrationStatus, RegistryStatus, Template
from ..storage.object_store import ObjectStore
from .service import tenant_namespace

logger = get_logger("orchestrator.registry.registration")

_TERMINAL = frozenset(
    {RegistrationStatus.registered, RegistrationStatus.failed, RegistrationStatus.no_source}
)


async def run_template_registration(
    *,
    db: Session,
    template_row_id: uuid.UUID,
    tenant_id: uuid.UUID,
    presenton,
    object_store: ObjectStore,
) -> None:
    """Register (or record `no_source` if there was never a PPTX) the template at
    `template_row_id`.

    Keyed on the row's own physical id, not `logical_id` + `version` -- templates
    have no edit/version-bump flow today, so this is unambiguous, and it means a
    concurrent version bump (if one is ever added) can never race this job onto
    the wrong row the way looking up "latest" could.
    """
    template = db.get(Template, template_row_id)
    if template is None or template.tenant_id != tenant_id:
        logger.warning(
            "template_registration_row_missing", extra={"template_row_id": str(template_row_id)}
        )
        return

    if template.registration_status in _TERMINAL:
        logger.info(
            "template_registration_noop_already_terminal",
            extra={
                "template_id": str(template.logical_id),
                "status": template.registration_status.value,
            },
        )
        return

    pptx_bytes = (
        object_store.get_bytes(key=template.source_pptx_uri) if template.source_pptx_uri else None
    )

    # Presenton has no tenant concept -- namespacing at the engine boundary is
    # what keeps two tenants' "Acme Brand" templates from colliding there. The
    # stored `Template.name` stays the plain human name; only the engine call
    # sees the namespaced one, same split the synchronous version had.
    namespace = tenant_namespace(db, tenant_id)
    registration = await presenton.register_template(
        name=f"{namespace}__{template.name}",
        pptx_bytes=pptx_bytes,
        pptx_filename=(
            template.source_pptx_uri.rsplit("/", 1)[-1] if template.source_pptx_uri else None
        ),
    )

    template.presenton_template_ref = registration.ref
    template.registration_status = registration.status
    template.registration_error = registration.error
    template.slide_image_urls = registration.slide_image_urls
    # TM-4: auto-approve on success -- the manual Approve step is gone, so this is
    # the only place `status` transitions away from `draft`.
    if registration.status is RegistrationStatus.registered:
        template.status = RegistryStatus.approved
    db.add(template)
    db.flush()
    logger.info(
        "template_registration_finished",
        extra={
            "template_id": str(template.logical_id),
            "registration_status": registration.status.value,
            "error": registration.error,
        },
    )
