import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import bootstrap
from app.models import AuditEvent, Role, User
from app.security import verify_password


def test_idempotent_bootstrap(factory, monkeypatch: pytest.MonkeyPatch, password: str) -> None:
    monkeypatch.setattr(bootstrap, "SessionLocal", factory)
    assert bootstrap.bootstrap_admin("Owner@example.com", "Owner", password)
    with factory() as db:
        user = db.scalar(select(User))
        original_hash = user.password_hash
        assert verify_password(password, original_hash)
        assert user.role == Role.ADMIN
    assert not bootstrap.bootstrap_admin("OWNER@example.com", "Replacement", "different-password")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        user = db.scalar(select(User))
        assert user.name == "Owner" and user.password_hash == original_hash
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_bootstrap_will_not_promote_or_add_users(
    factory,
    monkeypatch: pytest.MonkeyPatch,
    user: User,
    db: Session,
    password: str,
) -> None:
    monkeypatch.setattr(bootstrap, "SessionLocal", factory)
    user.role = Role.VIEWER
    db.commit()
    with pytest.raises(ValueError, match="not an active administrator"):
        bootstrap.bootstrap_admin(user.email, user.name, password)
    with pytest.raises(ValueError, match="empty users table"):
        bootstrap.bootstrap_admin("second@example.com", "Second", password)
