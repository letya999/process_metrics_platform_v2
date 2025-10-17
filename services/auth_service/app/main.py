from datetime import datetime

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Auth Service", version="1.0.0")

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": "auth_service",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    return app
