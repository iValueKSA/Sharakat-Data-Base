"""Native, Docker-free runtime for the Al-Ahsa investment platform.

Provisions and supervises PostgreSQL, a Redis-protocol server, the FastAPI
API (which also serves the UI), the Celery worker and Celery beat on Windows,
Linux and macOS. Entry point: ``python -m sharakat_runtime <command>``.
"""
