
from fastapi import FastAPI

from backend.auth_routes import router as auth_router

app = FastAPI(
    title="Aura Authentication API",
    description="Registration and login endpoints for Aura",
    version="1.0.0",
)

app.include_router(auth_router)


@app.get("/")
def home():
    return {"message": "Aura Authentication API is running"}

