from pathlib import Path
import hmac

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.routes import runs

app = FastAPI(title="GhostLib", version="0.2.0")


@app.middleware("http")
async def require_hosted_api_token(request, call_next):
    if (config.HOSTED_MODE and request.url.path.startswith("/api/")
            and request.url.path != "/api/health" and request.method != "OPTIONS"):
        if not config.API_TOKEN:
            return JSONResponse(
                status_code=503,
                content={"detail": "Hosted API access is disabled until GHOSTLIB_API_TOKEN is configured."},
            )
        expected = f"Bearer {config.API_TOKEN}"
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied, expected):
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"detail": "A valid GhostLib access token is required."},
            )
    return await call_next(request)


# Add CORS after the auth middleware so browsers receive CORS headers on auth errors too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(config.CORS_ORIGINS),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["WWW-Authenticate"],
)
app.include_router(runs.router)


@app.get("/health")
def health():
    return {"status": "ok", "project": "GhostLib"}


# `ghostlib ui`: serve the built dashboard (frontend/dist) from the same origin as the API.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="dashboard")
