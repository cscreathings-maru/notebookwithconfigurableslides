"""Test harness.

Runs the real app against a throwaway file-backed SQLite database so the tenancy
and RBAC guards are exercised end-to-end without Postgres/Redis/engines. Dev-mode
OIDC lets tests mint HS256 bearer tokens signed with the master secret.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator

# IMPORTANT: configure the environment BEFORE importing any src module, because
# src.core.db builds the engine from Settings at import time.
_TMP_DB = os.path.join(tempfile.gettempdir(), f"orch_test_{uuid.uuid4().hex}.db")
os.environ.update(
    DATABASE_URL=f"sqlite+pysqlite:///{_TMP_DB}",
    ORCH_SECRET_KEY="test-secret-key",
    OIDC_DEV_MODE="true",
    # This suite validates the full multi-tenant SaaS path (auth, RBAC, tenant
    # isolation, metering). Lite mode bypasses those, so pin it off here; the
    # lite bypass is a deployment toggle, exercised separately.
    LITE_MODE="false",
    ENVIRONMENT="test",
    LOG_LEVEL="WARNING",
)

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.core.db import SessionLocal, engine  # noqa: E402
from src.main import app  # noqa: E402
from src.models import (  # noqa: E402
    Base,
    Job,
    JobStatus,
    JobType,
    Tenant,
    TenantStatus,
    User,
    UserRole,
    UserStatus,
)


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    if os.path.exists(_TMP_DB):
        os.remove(_TMP_DB)


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    # Delete children before parents to satisfy FK constraints. Optional models
    # (added by later slices) are cleaned only once they exist.
    import src.models as models

    ordered_names = ["Source", "Outline", "Generation", "Project", "Job", "User", "Tenant"]
    with SessionLocal() as db:
        for name in ordered_names:
            model = getattr(models, name, None)
            if model is not None:
                db.query(model).delete()
        db.commit()


@pytest.fixture
def client() -> TestClient:
    # Plain instantiation (no context manager) so the Arq/Redis lifespan is skipped.
    return TestClient(app)


def _token(subject: str) -> str:
    return jwt.encode({"sub": subject}, "test-secret-key", algorithm="HS256")


def auth(subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(subject)}"}


class Fixtures:
    """Container for seeded ids/subjects used across tests."""

    tenant_a: uuid.UUID
    tenant_b: uuid.UUID
    admin_a_sub: str
    author_a_sub: str
    viewer_a_sub: str
    user_b_sub: str
    admin_b_sub: str
    job_b_id: uuid.UUID


@pytest.fixture
def seed() -> Fixtures:
    """Two tenants; tenant A has an admin and a viewer; tenant B owns a job."""
    fx = Fixtures()
    with SessionLocal() as db:
        tenant_a = Tenant(name="Acme", slug="acme", status=TenantStatus.active)
        tenant_b = Tenant(name="Globex", slug="globex", status=TenantStatus.active)
        db.add_all([tenant_a, tenant_b])
        db.flush()

        admin_a = User(
            tenant_id=tenant_a.id,
            email="admin@acme.id",
            oidc_subject="oidc|admin-a",
            role=UserRole.admin,
            status=UserStatus.active,
        )
        author_a = User(
            tenant_id=tenant_a.id,
            email="author@acme.id",
            oidc_subject="oidc|author-a",
            role=UserRole.author,
            status=UserStatus.active,
        )
        viewer_a = User(
            tenant_id=tenant_a.id,
            email="viewer@acme.id",
            oidc_subject="oidc|viewer-a",
            role=UserRole.viewer,
            status=UserStatus.active,
        )
        user_b = User(
            tenant_id=tenant_b.id,
            email="author@globex.id",
            oidc_subject="oidc|author-b",
            role=UserRole.author,
            status=UserStatus.active,
        )
        admin_b = User(
            tenant_id=tenant_b.id,
            email="admin@globex.id",
            oidc_subject="oidc|admin-b",
            role=UserRole.admin,
            status=UserStatus.active,
        )
        db.add_all([admin_a, author_a, viewer_a, user_b, admin_b])
        db.flush()

        job_b = Job(
            tenant_id=tenant_b.id,
            type=JobType.ingest,
            status=JobStatus.queued,
            attempts=0,
            idempotency_key="globex-key-1",
            progress={"step": "queued", "percent": 0},
        )
        db.add(job_b)
        db.flush()

        fx.tenant_a = tenant_a.id
        fx.tenant_b = tenant_b.id
        fx.admin_a_sub = admin_a.oidc_subject
        fx.author_a_sub = author_a.oidc_subject
        fx.viewer_a_sub = viewer_a.oidc_subject
        fx.user_b_sub = user_b.oidc_subject
        fx.admin_b_sub = admin_b.oidc_subject
        fx.job_b_id = job_b.id
        db.commit()
    return fx
