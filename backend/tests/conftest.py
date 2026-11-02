from __future__ import annotations

import os
import atexit
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Configure an isolated workspace before importing the application. The app reads configuration at
# import time, so this must happen at module import rather than inside a fixture.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="cfai-stage1-tests-"))
atexit.register(shutil.rmtree, _TEST_ROOT, ignore_errors=True)
os.environ["CFAI_DATA_DIR"] = str(_TEST_ROOT / "data")
os.environ["CFAI_MEDIA_DIR"] = str(_TEST_ROOT / "media")
os.environ["CFAI_DB_PATH"] = str(_TEST_ROOT / "data" / "creativeforge.db")
os.environ["CFAI_SECRETS_PATH"] = str(_TEST_ROOT / "data" / "secrets.json")
os.environ["CFAI_TEMP_DIR"] = str(_TEST_ROOT / "media" / "tmp")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def brand(client):
    response = client.post(
        "/api/brands",
        json={
            "name": "Northstar Coffee",
            "industry": "Food and beverage",
            "description": "A small-batch coffee roaster.",
            "products": "Whole-bean coffee and subscriptions.",
            "audience": "Home brewers who care about freshness.",
            "voice": "Warm, precise and unfussy.",
            "colors": ["#C7FF2F", "#161616"],
            "website": "https://example.test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def project(client, brand):
    response = client.post(
        "/api/projects",
        json={
            "type": "general",
            "name": "Autumn roast launch",
            "description": "Launch the autumn single-origin release.",
            "brand_id": brand["id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
