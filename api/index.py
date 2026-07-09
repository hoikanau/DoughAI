"""Vercel entrypoint: exposes the FastAPI app for the Python/ASGI runtime."""

from web.app import app  # noqa: F401
