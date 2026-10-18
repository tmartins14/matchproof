from importlib.metadata import version

from fastapi import FastAPI

app = FastAPI(title="Matchproof API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": version("matchproof-api")}
