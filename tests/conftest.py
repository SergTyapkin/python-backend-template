import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from myapp.main import create_app
from tests.settings import IsolatedSettings


@pytest.fixture
def settings():
    return IsolatedSettings(environment="test")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
async def client(app):
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="https://test"
        ) as client:
            yield client
