"""Smoke a public deployment from a fresh, unauthenticated HTTP session.

Credentials are read from environment variables, never printed or placed in URLs.
"""

import argparse, os
from urllib.parse import urlsplit
import requests


def smoke(url, allow_local=False, login=False):
    parts = urlsplit(url)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError(
            "Use the plain deployment URL without credentials or query parameters."
        )
    if parts.scheme != "https" and not (
        allow_local
        and parts.scheme == "http"
        and parts.hostname in ("localhost", "127.0.0.1", "::1")
    ):
        raise ValueError(
            "Use an HTTPS public URL. --allow-local permits local container checks only."
        )
    base = url.rstrip("/")
    session = requests.Session()
    passed = []

    def check(path, status, label, method="GET", **kwargs):
        response = session.request(
            method, base + path, timeout=30, allow_redirects=False, **kwargs
        )
        if response.status_code != status:
            raise RuntimeError(
                f"{label}: expected HTTP {status}, received HTTP {response.status_code}."
            )
        passed.append(label)
        return response

    page = check("/", 200, "Public sign-in page")
    if "text/html" not in page.headers.get("Content-Type", ""):
        raise RuntimeError("The public URL did not serve the frontend.")
    check("/api/health", 200, "Backend liveness")
    check("/api/ready", 200, "Database readiness")
    check("/api/auth/me", 401, "Signed-out account protection")
    check("/api/courses", 401, "Signed-out material protection")
    if login:
        email = os.getenv("AURA_DEMO_EMAIL", "judge@aura.example.org")
        password = os.environ.get("AURA_DEMO_PASSWORD")
        if not password:
            raise ValueError(
                "Set AURA_DEMO_PASSWORD in your shell to run the login check."
            )
        data = check(
            "/api/auth/login",
            200,
            "Demo sign in",
            method="POST",
            json={"email": email, "password": password},
        ).json()
        session.headers["Authorization"] = "Bearer " + data["access_token"]
        user = check("/api/auth/me", 200, "Demo account profile").json()
        if user.get("is_demo") is not True:
            raise RuntimeError(
                "The supplied account is not flagged as a synthetic demo account."
            )
        courses = check("/api/courses", 200, "Demo workspace").json()["courses"]
        course = courses[0]["course_id"]
        materials = check(
            f"/api/study/materials?course_id={course}",
            200,
            "Demo material availability",
        ).json()["sources"]
        if not any(
            s["source_name"] == "Aura Demo Study Notes.pdf"
            and s["status"] in ("success", "partial", "ready")
            for s in materials
        ):
            raise RuntimeError(
                "The synthetic demo document is not ready yet. Wait for preparation, then rerun."
            )
        check("/api/auth/logout", 200, "Demo sign out", method="POST")
        check("/api/auth/me", 401, "Revoked token rejected")
    return passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--allow-local", action="store_true")
    parser.add_argument("--demo-login", action="store_true")
    args = parser.parse_args()
    try:
        for label in smoke(args.url, args.allow_local, args.demo_login):
            print("PASS:", label)
    except (ValueError, RuntimeError, requests.RequestException) as error:
        # Network exceptions can contain URLs; keep the failure output fixed.
        if isinstance(error, (ValueError, RuntimeError)):
            raise SystemExit(str(error)) from None
        raise SystemExit(
            "Public smoke test could not connect. Check the URL, certificate and service logs."
        ) from None
