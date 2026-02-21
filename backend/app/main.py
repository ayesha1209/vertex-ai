import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db.mongo import client
from app.routes.documents import router as documents_router

# Enable logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Vertex COA & Quotation Generator",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    app.include_router(documents_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/health/db")
    async def health_db() -> dict:
        """Check MongoDB connection. Use this to debug MONGODB_URI."""
        try:
            client.admin.command("ping")
            return {"ok": True, "message": "MongoDB connection OK"}
        except Exception as e:
            err_msg = str(e)
            if "password" in err_msg.lower() or "auth" in err_msg.lower():
                err_msg = "Authentication failed. Check username and password in MONGODB_URI."
            elif "SSL" in err_msg or "TLS" in err_msg or "handshake" in err_msg:
                err_msg = "SSL/TLS error. Common on Windows: try updating certifi (pip install -U certifi) or Python/OpenSSL."
            elif "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
                err_msg = "Connection timed out. Check network and Atlas Network Access (allow your IP)."
            return {"ok": False, "error": err_msg[:500]}

    return app


app = create_app()

