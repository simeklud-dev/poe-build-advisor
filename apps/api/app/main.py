from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import advisor

app = FastAPI(title="PoE Build Advisor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(advisor.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
