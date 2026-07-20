"""Testy, které nepotřebují běžící LuaJIT/PoB engine -- validace vstupu v routeru.

End-to-end test s reálným PoB enginem (viz AI_BUILD_ADVISOR_PLAN.md, sekce
"Ověření") patří do samostatného smoke testu spouštěného v Docker image, kde
je LuaJIT skutečně nainstalovaný -- ne sem.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_rejects_link_instead_of_code():
    response = client.post("/advisor/analyze", json={"code": "https://pobb.in/abc123"})
    assert response.status_code == 422


def test_analyze_rejects_invalid_code():
    response = client.post("/advisor/analyze", json={"code": "not-a-real-pob-code"})
    assert response.status_code == 400
