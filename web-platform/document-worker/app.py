"""Vercel entrypoint for the isolated CareerFlow document worker."""

from document_worker.main import app

__all__ = ["app"]
