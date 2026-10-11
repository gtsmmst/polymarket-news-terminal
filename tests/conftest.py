"""
Test bootstrap. Must run before any `app.*` import because app.config reads the
environment at import time.

- DATABASE_PATH -> a throwaway SQLite file so tests never touch data/app.db
- SCHEDULER_ENABLED=0 -> the background refresh loop (which does network I/O)
  is never started by the FastAPI lifespan.
- ANTHROPIC_API_KEY cleared -> the optional LLM hook is a no-op.
"""
import os
import tempfile

_TMP_DIR = tempfile.mkdtemp(prefix="pmnt-test-")
os.environ["DATABASE_PATH"] = os.path.join(_TMP_DIR, "test.db")
os.environ["SCHEDULER_ENABLED"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
