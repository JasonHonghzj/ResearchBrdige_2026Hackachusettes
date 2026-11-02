"""Shared HTTP client with an explicit ASGI lifespan and clean shutdown."""
import pytest


@pytest.fixture(scope="session")
def client():
    # Keep non-HTTP tests independent of the web stack during collection.
    from fastapi.testclient import TestClient

    from app import app

    with TestClient(app) as test_client:
        yield test_client
