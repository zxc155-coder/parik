"""Top-level ASGI entrypoint for production deployments.

Re-exports the FastAPI app from `app.asgi` so platforms that auto-detect
`main:app` (Fly.io, Railway, Render, …) can boot it directly.
"""

from app.asgi import app  # noqa: F401
