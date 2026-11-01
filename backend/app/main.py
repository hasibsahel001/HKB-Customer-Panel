import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import actions, audit_log, auth, customer, maintenance, users
from app.core.errors import InvalidInput
from app.db import init_db

logging.basicConfig(level=logging.INFO)

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


def mount_frontend(application: FastAPI, dist: Path) -> bool:
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return False

    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

    @application.get("/{path:path}", include_in_schema=False)
    def single_page(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and dist in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return True


app = FastAPI(title="HKB Customer Panel", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(audit_log.router)
app.include_router(customer.router)
app.include_router(actions.router)
app.include_router(maintenance.router)


@app.exception_handler(InvalidInput)
async def invalid_input_handler(request, exc: InvalidInput):
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_input", "message": str(exc)}},
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


mount_frontend(app, FRONTEND_DIST)