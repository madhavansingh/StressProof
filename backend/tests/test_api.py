"""
Basic tests for FastAPI backend routes.
"""

from fastapi.testclient import TestClient
from stressproof_backend.main import app

client = TestClient(app)


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_list_datasets():
    res = client.get("/datasets")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_post_case_file_unauthorized():
    res = client.post("/case-files", content=b"{}")
    assert res.status_code in (401, 403)
