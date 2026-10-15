from fastapi import FastAPI
from app.routes import scan, dependencies, migrations, capsule

app = FastAPI(title="GhostLib", version="0.1.0")

app.include_router(scan.router, prefix="/api")
app.include_router(dependencies.router, prefix="/api")
app.include_router(migrations.router, prefix="/api")
app.include_router(capsule.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "project": "GhostLib"}
