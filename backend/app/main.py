from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import runs

app = FastAPI(title="GhostLib", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(runs.router)


@app.get("/health")
def health():
    return {"status": "ok", "project": "GhostLib"}
