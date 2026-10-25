"""Production policy plus one-origin hosting of the built Vite frontend."""

import os
from pathlib import Path
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from backend.production.config import hosts, flag
from backend.production.limits import actor, check_enabled, db
from backend.production.security import rate_limit

PUBLIC = {"/health", "/ready", "/auth/login", "/auth/register", "/auth/demo-info"}


class SPA(StaticFiles):
    async def get_response(self, path, scope):
        if scope.get("aura_api"):
            return JSONResponse({"detail": "Endpoint not found."}, 404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as error:
            if error.status_code != 404:
                raise
            return await super().get_response("index.html", scope)
        except Exception as error:
            # StaticFiles raises Starlette's base HTTPException.
            if getattr(error, "status_code", None) != 404:
                raise
            return await super().get_response("index.html", scope)


class APIPrefix:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (
            scope["path"] == "/api" or scope["path"].startswith("/api/")
        ):
            scope = dict(scope)
            scope["path"] = scope["path"][4:] or "/"
            scope["raw_path"] = scope["path"].encode()
            scope["aura_api"] = True
        await self.app(scope, receive, send)


def install(app, dist=None):
    from backend.auth_routes import get_current_student

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts())

    @app.middleware("http")
    async def policy(request, call_next):
        token = None
        try:
            path = request.url.path
            if path == "/auth/register" and not flag("AURA_ALLOW_REGISTRATION"):
                raise HTTPException(
                    403,
                    {
                        "code": "registration_closed",
                        "message": "Use the demo account provided with the hackathon entry.",
                    },
                )
            is_api = bool(request.scope.get("aura_api")) or path.startswith(
                (
                    "/auth/",
                    "/study/",
                    "/agents/",
                    "/courses",
                    "/chat",
                    "/preparation-jobs",
                    "/sources/",
                )
            )
            if is_api and request.method != "OPTIONS":
                auth = request.headers.get("authorization", "")
                if path not in PUBLIC:
                    if not auth.lower().startswith("bearer "):
                        raise HTTPException(
                            401,
                            "Sign in to access your study workspace.",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                    student = await run_in_threadpool(
                        get_current_student,
                        HTTPAuthorizationCredentials(
                            scheme="Bearer", credentials=auth[7:].strip()
                        ),
                    )
                    request.state.production_student = student
                    token = actor.set(student["student_id"])
                    await run_in_threadpool(
                        rate_limit, "user:" + str(student["student_id"])
                    )
                    if (
                        student.get("is_demo")
                        and request.method == "POST"
                        and (
                            path.endswith("/sources")
                            or path.endswith("/preparation-jobs")
                        )
                    ):
                        raise HTTPException(
                            403,
                            {
                                "code": "demo_synthetic_only",
                                "message": "The shared demo uses synthetic materials only. Use a personal account to upload your own files.",
                            },
                        )
                else:
                    await run_in_threadpool(
                        rate_limit,
                        "login:"
                        + str(request.client.host if request.client else "unknown"),
                        True,
                    )
                length = request.headers.get("content-length", "0")
                try:
                    too_large = int(length) > 102 * 1024 * 1024
                except ValueError:
                    too_large = True
                if too_large:
                    raise HTTPException(413, "Choose a file smaller than 100 MiB.")
                if request.method == "POST" and (
                    path
                    in (
                        "/chat",
                        "/study/tools",
                        "/study/generation-jobs",
                        "/agents/runs",
                    )
                    or path.endswith("/figure")
                ):
                    await run_in_threadpool(check_enabled)
            response = await call_next(request)
        except HTTPException as error:
            response = JSONResponse(
                {"detail": error.detail},
                status_code=error.status_code,
                headers=error.headers,
            )
        except Exception as error:
            # Do not leak host paths, database URLs or provider messages.
            import logging

            logging.getLogger(__name__).warning(
                "production_request=failed error_type=%s", type(error).__name__
            )
            response = JSONResponse(
                {"detail": "Aura is temporarily unavailable. Your saved work is kept."},
                503,
            )
        finally:
            if token is not None:
                actor.reset(token)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
                "X-Frame-Options": "SAMEORIGIN",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-src 'self' blob:; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'",
            }
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.get("/ready")
    def ready():
        try:
            with db() as cur:
                cur.execute("SELECT 1 FROM aura_deployment_control WHERE id=1")
                if not cur.fetchone():
                    raise RuntimeError("Initialization incomplete")
            return {"status": "ready"}
        except Exception:
            return JSONResponse({"status": "not_ready"}, 503)

    directory = Path(dist or os.getenv("AURA_STATIC_DIR", "dist")).resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError(
            "Build the Vite frontend before starting the production app."
        )
    app.mount("/", SPA(directory=directory, html=True), name="frontend")
    return APIPrefix(app)
