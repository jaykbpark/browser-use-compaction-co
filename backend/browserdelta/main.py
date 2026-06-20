from fastapi import FastAPI

from browserdelta.api.routes_runs import router as runs_router


app = FastAPI(title="BrowserDelta API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(runs_router, prefix="/api")
