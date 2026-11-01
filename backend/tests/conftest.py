import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables)
from app.auth import ratelimit
from app.core.config import settings
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    ratelimit.reset_all()
    monkeypatch.setattr(settings, "login_max_failures", 3)
    monkeypatch.setattr(settings, "login_ip_max_attempts", 50)
    monkeypatch.setattr(settings, "password_min_length", 10)
    monkeypatch.setattr(settings, "session_idle_minutes", 60)
    monkeypatch.setattr(settings, "session_absolute_hours", 12)
    monkeypatch.setattr(settings, "customer_checks_per_minute", 20)

    # The TestClient is deliberately not used as a context manager,
    # so the startup hook never touches the real database file.
    yield TestClient(app)

    app.dependency_overrides.clear()
    ratelimit.reset_all()