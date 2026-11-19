from fastapi import FastAPI

app = FastAPI(title="겜누리 API")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
