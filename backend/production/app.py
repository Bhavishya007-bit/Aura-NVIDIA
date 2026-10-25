"""Production entrypoint: configuration and migrations precede app workers."""

import os

os.environ.setdefault("AURA_ENV", "production")
from backend.production.config import validate, enabled

if not enabled():
    raise RuntimeError("Use backend.main for the local development profile.")
validate()
from backend.production.bootstrap import bootstrap

bootstrap()
from backend.production.demo import seed_demo

seed_demo()
from backend.main import app as private_app
from backend.production.web import install

app = install(private_app)
