import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router

app = FastAPI(title="Smart-Mapping")
app.include_router(router)

# Serve the built React SPA from backend/static (produced by `vite build`).
# Falls back to the legacy public/ assets if the build output is absent, so
# the server still works before the first frontend build.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
_PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "public")
_SPA_DIR = _STATIC_DIR if os.path.isdir(_STATIC_DIR) else _PUBLIC_DIR
if os.path.isdir(_SPA_DIR):
    app.mount("/", StaticFiles(directory=_SPA_DIR, html=True), name="spa")
