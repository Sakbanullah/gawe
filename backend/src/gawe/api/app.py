"""FastAPI application: local API plus built SPA assets."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from .. import API_VERSION, __version__
from ..config import Config, resolve_api_key
from ..db import repo
from ..jobs.fetch import HostRateLimiter
from ..llm.client import LLMClient
from ..llm.providers.openai_compatible import OpenAICompatibleProvider
from ..llm.providers.synthetic import SyntheticExtractProvider
from ..security import csrf
from ..security.consent import ConsentStore
from ..services.tasks import TaskStore
from .errors import ApiError, error_payload, payload_for
from .routes import (
    applications,
    discovery,
    documents,
    exports,
    import_browser,
    matches,
    overview,
    session,
    settings,
    setup,
    sources,
    tasks,
)

logger = logging.getLogger(__name__)

FRONTEND_FALLBACK = "index.html"

# The browser extension cannot hold the SPA's cookie pair: it posts from a
# `chrome-extension://` page. That single path authenticates with its own bearer
# token plus an extension-only Origin check instead, and every other mutating
# route keeps the CSRF pair.
EXTENSION_IMPORT_PATH = "/api/import/browser"


def _is_extension_import(request: Request) -> bool:
    # Method matters: only the extension's own POST may skip the SPA pair.
    # Exempting the path alone would also drop CSRF from any future GET/PUT
    # handler added under /api/import/browser.
    return (
        request.url.path == EXTENSION_IMPORT_PATH and request.method.upper() == "POST"
    )


def _reap_orphan_tasks(config: Config) -> None:
    """Fail every unfinished task at startup; nothing owns them yet."""
    conn = repo.connect(config.database)
    try:
        tasks = TaskStore(conn)
        tasks.reap_stale(exclude=set(), older_than_s=0)
        conn.commit()
    finally:
        conn.close()



def _make_provider(config: Config):
    provider_config = config.llm.providers.get(config.llm.active_provider)
    if provider_config is None or provider_config.type == "fake":
        return SyntheticExtractProvider()
    return OpenAICompatibleProvider(
        provider_config.base_url or "",
        api_key=resolve_api_key(provider_config.api_key_ref),
        provider_id=config.llm.active_provider,
    )


def build_llm_client(
    config: Config, connection: repo.Connection | None = None, provider=None
) -> LLMClient:
    provider = provider or _make_provider(config)
    consent = None
    if connection is not None and config.privacy.cloud_consent_required:
        consent = ConsentStore(connection, config)
    return LLMClient(config=config, provider=provider, consent_store=consent, connection=connection)


def create_app(
    config: Config,
    connection: repo.Connection | None = None,
    llm_client: LLMClient | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if connection is not None:
            await run_in_threadpool(repo.migrate, connection)
        else:
            await run_in_threadpool(repo.ensure_schema, config.database)
            startup = await run_in_threadpool(repo.connect, config.database)
            try:
                await run_in_threadpool(repo.migrate, startup)
            finally:
                await run_in_threadpool(startup.close)
        # A task row says nothing about who owns it. After a crash or restart no
        # process owns any `queued`/`processing` row, so fail them now instead of
        # leaving a workspace locked forever.
        await run_in_threadpool(_reap_orphan_tasks, config)
        scheduler = None
        # The scheduler only runs against a real database connection of its own.
        # An injected connection means tests or an embedded caller, who drive runs
        # themselves.
        if connection is None and config.discovery.scheduler_enabled:
            from ..services.scheduler import DiscoveryScheduler

            scheduler = DiscoveryScheduler(config)
            scheduler.start()
        try:
            yield
        finally:
            if scheduler is not None:
                await run_in_threadpool(scheduler.stop)

    app = FastAPI(
        title="Gawe",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.config = config
    app.state.db = connection
    app.state.sessions = {}
    app.state.llm_client = llm_client or build_llm_client(config)
    app.state.provider_factory = _make_provider
    app.state.discovery_fetcher = None
    app.state.manual_url_fetcher = None
    # One limiter per app: the per-host interval must survive across requests.
    app.state.discovery_limiter = HostRateLimiter()

    # A `chrome-extension://` page is a cross origin for 127.0.0.1, so the browser
    # sends a preflight and blocks the POST without these headers. Only the
    # import path needs it: the SPA is same-origin and never asks. The handler
    # still verifies the token and the extension Origin, so this opens nothing.
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^chrome-extension://[a-p]{32}$",
        allow_methods=["POST"],
        allow_headers=["Content-Type", "X-Gawe-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def db_session(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        if connection is not None:
            request.state.db = connection
            return await call_next(request)
        db = await run_in_threadpool(repo.connect, config.database)
        request.state.db = db
        try:
            response = await call_next(request)
        except Exception:
            await run_in_threadpool(db.rollback)
            raise
        finally:
            await run_in_threadpool(db.close)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ()) if part != "body"),
                "code": error.get("type", "invalid"),
                "message": error.get("msg", "Nilai tidak valid."),
            }
            for error in exc.errors()[:50]
        ]
        return JSONResponse(
            status_code=400,
            content=error_payload(
                "validation_failed", "Request tidak valid.", "validation",
                request_id=request.headers.get("X-Request-Id"), details=details,
            ),
        )

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code,
            content=payload_for(exc, request.headers.get("X-Request-Id")),
        )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        if request.method.upper() not in csrf.SAFE_METHODS and not _is_extension_import(request):
            session_id = request.cookies.get(csrf.SESSION_COOKIE)
            active = app.state.sessions.get(session_id)
            try:
                csrf.validate_csrf(
                    request.method,
                    request.headers,
                    request.cookies,
                    active,
                    csrf.allowed_origins(config.server.host, config.server.port),
                )
            except csrf.CsrfError as exc:
                return JSONResponse(
                    status_code=403,
                    content=error_payload(
                        exc.code, "Token CSRF tidak valid.", "security",
                        request_id=request.headers.get("X-Request-Id"),
                    ),
                )
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.error("unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal_error", "Terjadi kesalahan internal.", "server",
                retryable=True, request_id=request.headers.get("X-Request-Id"),
            ),
        )

    app.include_router(session.router)
    app.include_router(overview.router)
    app.include_router(setup.router)
    app.include_router(settings.router)
    app.include_router(sources.router)
    app.include_router(discovery.router)
    app.include_router(matches.router)
    app.include_router(applications.router)
    app.include_router(documents.router)
    app.include_router(exports.router)
    app.include_router(tasks.router)
    app.include_router(import_browser.router)

    dist = config.dist_dir
    if dist.is_dir():
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(
                    status_code=404,
                    content=error_payload("not_found", "Endpoint tidak ditemukan.", "server"),
                )
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            # A missing asset is a 404, not the app shell. Answering index.html
            # for a stale `/assets/index-<hash>.js` gives the browser HTML where
            # it expects JavaScript, and the page renders blank with no clue why.
            if full_path.startswith("assets/") or Path(full_path).suffix:
                return JSONResponse(
                    status_code=404,
                    content=error_payload("not_found", "Aset tidak ditemukan.", "server"),
                )
            index = dist / FRONTEND_FALLBACK
            if index.is_file():
                return FileResponse(index)
            return JSONResponse(
                status_code=404,
                content=error_payload("not_found", "Frontend build tidak ditemukan.", "server"),
            )

    app.state.api_version = API_VERSION
    app.state.request_ids = uuid
    return app
