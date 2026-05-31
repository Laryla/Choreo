import pytest
from choreo.auth.jwt import create_access_token, create_refresh_token, verify_token


def test_access_token_roundtrip():
    token = create_access_token("user-123")
    assert verify_token(token) == "user-123"


def test_refresh_token_roundtrip():
    token = create_refresh_token("user-456")
    assert verify_token(token) == "user-456"


def test_invalid_token_raises():
    with pytest.raises(Exception):
        verify_token("not.a.real.token")


def test_tampered_token_raises():
    token = create_access_token("user-789")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(Exception):
        verify_token(tampered)
