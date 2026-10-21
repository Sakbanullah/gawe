"""Service wiring for request handlers."""

from __future__ import annotations

from dataclasses import replace

from fastapi import Request

from ..llm.client import LLMClient
from ..master_cv.store import MasterCvStore
from ..profile.store import ProfileStore
from ..security.consent import ConsentStore
from ..services.discovery_service import DiscoveryService
from ..services.profile_service import ProfileService
from ..services.tasks import TaskStore


def llm_client(request: Request) -> LLMClient:
    base = request.app.state.llm_client
    # Always attach: the store itself decides whether consent applies (fake
    # providers are exempt), so no request path can reach a provider ungated.
    consent = ConsentStore(request.state.db, request.app.state.config)
    return replace(base, connection=request.state.db, consent_store=consent)


def master_cv_store(request: Request) -> MasterCvStore:
    return MasterCvStore(request.state.db, request.app.state.config.data_dir)


def profile_store(request: Request) -> ProfileStore:
    return ProfileStore(request.state.db)


def task_store(request: Request) -> TaskStore:
    return TaskStore(request.state.db)


def consent_store(request: Request) -> ConsentStore:
    return ConsentStore(request.state.db, request.app.state.config)


def profile_service(request: Request) -> ProfileService:
    return ProfileService(
        request.state.db,
        master_cv_store(request),
        profile_store(request),
        task_store(request),
        llm_client(request),
        request.app.state.config.root_dir,
    )


def discovery_service(request: Request) -> DiscoveryService:
    settings = request.app.state.config.discovery
    return DiscoveryService(
        request.state.db,
        profile_store(request),
        task_store(request),
        fetcher=request.app.state.discovery_fetcher,
        limiter=request.app.state.discovery_limiter,
        max_workers=settings.max_workers,
        max_run_seconds=settings.max_run_seconds,
        document_fetcher=request.app.state.manual_url_fetcher,
    )
