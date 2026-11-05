import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .db import Base, SessionLocal, engine
from .models import Role, User
from .routers import auth, dashboard, imports, offers, procurements, rfq, suppliers
from .security import hash_password
from .services import pipeline

log = logging.getLogger("app")


def bootstrap():
    """Create the first SUPER_ADMIN if there are no users. Tables come from Alembic in production."""
    with SessionLocal() as db:
        if not db.scalar(select(User).limit(1)):
            from .services.sessions import norm_phone

            db.add(User(email=settings.bootstrap_admin_email.lower(), name=settings.bootstrap_admin_name, phone=norm_phone(settings.bootstrap_admin_phone) if settings.bootstrap_admin_phone else None,
                        password_hash=hash_password(settings.bootstrap_admin_password), role=Role.SUPER_ADMIN.value))
            db.commit()
            log.warning("Bootstrap admin created: %s (change the password!)", settings.bootstrap_admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)  # dev/test convenience; PostgreSQL uses `alembic upgrade head`
    bootstrap()
    for did in pipeline.requeue_stuck():  # recover documents interrupted by a restart
        asyncio.get_running_loop().run_in_executor(None, pipeline.process_document, did)
    yield


app = FastAPI(title="cp360.uz API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False)
for r in (auth.router, procurements.router, offers.router, suppliers.router, imports.router, dashboard.router, rfq.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    """Also proves the original-file storage is writable: a read-only/foreign-owned volume must not look healthy."""
    from pathlib import Path

    from fastapi.responses import JSONResponse

    try:
        d = Path(settings.storage_dir)
        d.mkdir(parents=True, exist_ok=True)
        probe = d / ".health"
        probe.write_text("ok")
        probe.unlink()
    except OSError as e:
        return JSONResponse({"status": "error", "storage": f"not writable: {e.strerror}"}, status_code=503)
    return {"status": "ok"}
