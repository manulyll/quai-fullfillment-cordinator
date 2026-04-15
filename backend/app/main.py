from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import get_settings
from app.routes.me import router as me_router
from app.routes.shortages import router as shortages_router

settings = get_settings()
app = FastAPI(title=settings.app_name)
frontend_dist_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/app-config.js", include_in_schema=False)
async def app_config() -> PlainTextResponse:
    api_base_url = ""
    payload = (
        "window.__APP_CONFIG__ = "
        "{"
        f'API_BASE_URL: "{api_base_url}", '
        f'COGNITO_USER_POOL_ID: "{settings.cognito_user_pool_id}", '
        f'COGNITO_CLIENT_ID: "{settings.cognito_app_client_id}", '
        f'COGNITO_REGION: "{settings.cognito_region}"'
        "};"
    )
    return PlainTextResponse(payload, media_type="application/javascript")


app.include_router(me_router)
app.include_router(shortages_router)

if frontend_dist_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist_dir / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        return FileResponse(frontend_dist_dir / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        # Keep API and docs routes handled by FastAPI routers.
        reserved_prefixes = ("api", "health", "docs", "redoc", "openapi.json", "assets")
        if full_path.startswith(reserved_prefixes):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(frontend_dist_dir / "index.html")
