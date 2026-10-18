import secrets

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("secret", ["", "CHANGE_ME", "x" * 20])
def test_weak_secrets_rejected(secret: str) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret=secret)


def test_secure_cookies_required_in_production() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(jwt_secret=secrets.token_urlsafe(48), app_env="production", cookie_secure=False)


def test_config_defaults() -> None:
    config = Settings(jwt_secret=secrets.token_urlsafe(48))
    assert config.access_token_expire_minutes == 15
    assert config.cookie_secure is False
