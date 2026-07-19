"""
Dashboard web + API.

Ejecutar:
    uvicorn web.app:app --host 0.0.0.0 --port 8000

Sirve:
  - GET  /                 -> PWA (dashboard de ofertas)
  - GET  /api/deals        -> últimas ofertas detectadas (JSON)
  - POST /api/push/subscribe -> guarda una suscripción Web Push del navegador
  - GET  /api/vapid-public-key -> llave pública para el frontend
"""
import json
from pathlib import Path

import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import storage

app = FastAPI(title="Deal Tracker")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@app.on_event("startup")
def startup():
    storage.init_db()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.json")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/api/deals")
def get_deals(limit: int = 50):
    return JSONResponse(storage.recent_deals(limit=limit))


@app.get("/api/vapid-public-key")
def vapid_public_key():
    cfg = load_config()
    return {"key": cfg["notifications"]["webpush"].get("vapid_public_key", "")}


@app.post("/api/push/subscribe")
async def push_subscribe(request: Request):
    sub = await request.json()
    storage.save_push_subscription(sub["endpoint"], json.dumps(sub))
    return {"ok": True}
