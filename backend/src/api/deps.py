"""Shared API dependencies that wire tenant-scoped repositories/services.

Repositories are always constructed from the Principal's tenant_id, never from a
request parameter — so isolation holds by construction. Engine clients and the
object store are provided here so tests can override them with fakes.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..auth.dependencies import get_current_principal
from ..auth.principal import Principal
from ..core.db import get_db
from ..engines.llm import LlmClient
from ..engines.open_notebook import OpenNotebookClient
from ..engines.presenton import PresentonClient
from ..generation.repository import GenerationRepository
from ..generation.service import GenerationService
from ..ingestion.repository import ProjectRepository, SourceRepository
from ..ingestion.service import ProjectService, SourceService
from ..jobs.repository import JobRepository
from ..jobs.service import JobService
from ..metering.alerts import AlertSink, get_alert_sink as _get_alert_sink
from ..outline.repository import OutlineRepository
from ..outline.service import OutlineService
from ..registry.repository import ProfileRepository, RegistryUsage, TemplateRepository
from ..registry.service import ProfileService, TemplateService
from ..storage.object_store import ObjectStore, get_object_store as _get_object_store


# --- Engine clients & storage (overridable in tests) ---


def get_open_notebook_client() -> OpenNotebookClient:
    return OpenNotebookClient()


def get_presenton_client() -> PresentonClient:
    return PresentonClient()


def get_llm_client() -> LlmClient:
    return LlmClient()


def get_alert_sink() -> AlertSink:
    return _get_alert_sink()


def get_object_store() -> ObjectStore:
    return _get_object_store()


# --- Jobs ---


def get_job_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> JobRepository:
    return JobRepository(db, principal.tenant_id)


def get_job_service(
    request: Request,
    repo: JobRepository = Depends(get_job_repository),
) -> JobService:
    # The Arq redis pool, if present, is attached to app state at startup.
    enqueuer = getattr(request.app.state, "arq_pool", None)
    return JobService(repo, enqueuer)


# --- Ingestion ---


def get_project_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ProjectRepository:
    return ProjectRepository(db, principal.tenant_id)


def get_source_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> SourceRepository:
    return SourceRepository(db, principal.tenant_id)


def get_project_service(
    repo: ProjectRepository = Depends(get_project_repository),
    on_client: OpenNotebookClient = Depends(get_open_notebook_client),
) -> ProjectService:
    return ProjectService(repo, on_client)


def get_source_service(
    source_repo: SourceRepository = Depends(get_source_repository),
    project_repo: ProjectRepository = Depends(get_project_repository),
    object_store: ObjectStore = Depends(get_object_store),
    job_service: JobService = Depends(get_job_service),
) -> SourceService:
    return SourceService(
        source_repo=source_repo,
        project_repo=project_repo,
        object_store=object_store,
        job_service=job_service,
    )


# --- Registry (profiles + templates) ---


def get_profile_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> ProfileRepository:
    return ProfileRepository(db, principal.tenant_id)


def get_template_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> TemplateRepository:
    return TemplateRepository(db, principal.tenant_id)


def get_registry_usage(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> RegistryUsage:
    return RegistryUsage(db, principal.tenant_id)


def get_template_service(
    repo: TemplateRepository = Depends(get_template_repository),
    usage: RegistryUsage = Depends(get_registry_usage),
    presenton: PresentonClient = Depends(get_presenton_client),
    object_store: ObjectStore = Depends(get_object_store),
) -> TemplateService:
    return TemplateService(
        repo=repo, usage=usage, presenton=presenton, object_store=object_store
    )


def get_profile_service(
    repo: ProfileRepository = Depends(get_profile_repository),
    template_repo: TemplateRepository = Depends(get_template_repository),
    usage: RegistryUsage = Depends(get_registry_usage),
) -> ProfileService:
    return ProfileService(repo=repo, template_repo=template_repo, usage=usage)


# --- Outline + Generation ---


def get_outline_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> OutlineRepository:
    return OutlineRepository(db, principal.tenant_id)


def get_generation_repository(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> GenerationRepository:
    return GenerationRepository(db, principal.tenant_id)


def get_outline_service(
    repo: OutlineRepository = Depends(get_outline_repository),
    project_repo: ProjectRepository = Depends(get_project_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    on_client: OpenNotebookClient = Depends(get_open_notebook_client),
    llm: LlmClient = Depends(get_llm_client),
) -> OutlineService:
    return OutlineService(
        repo=repo,
        project_repo=project_repo,
        profile_repo=profile_repo,
        on_client=on_client,
        llm=llm,
    )


def get_generation_service(
    gen_repo: GenerationRepository = Depends(get_generation_repository),
    outline_repo: OutlineRepository = Depends(get_outline_repository),
    source_repo: SourceRepository = Depends(get_source_repository),
    profile_repo: ProfileRepository = Depends(get_profile_repository),
    template_repo: TemplateRepository = Depends(get_template_repository),
    job_service: JobService = Depends(get_job_service),
    alert_sink: AlertSink = Depends(get_alert_sink),
) -> GenerationService:
    return GenerationService(
        gen_repo=gen_repo,
        outline_repo=outline_repo,
        source_repo=source_repo,
        profile_repo=profile_repo,
        template_repo=template_repo,
        job_service=job_service,
        alert_sink=alert_sink,
    )
