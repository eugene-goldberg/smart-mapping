from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_taxonomies_envelope():
    r = client.get("/api/taxonomies")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["taxonomies"], list)
    if body["taxonomies"]:
        row = body["taxonomies"][0]
        assert "taxonomy_id" in row and "name" in row and "uuid" in row


def test_concepts_envelope():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    if not tax:
        return
    tid = tax[0]["taxonomy_id"]
    r = client.get(f"/api/concepts/{tid}")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["concepts"], list)
    if body["concepts"]:
        c = body["concepts"][0]
        for key in ("taxonomyConceptId", "identifier", "classification", "mappedStatus", "isAbstract"):
            assert key in c


def test_customer_groups_periods():
    g = client.get("/api/customer-groups").json()
    assert g["success"] is True and isinstance(g["groups"], list)
    p = client.get("/api/periods").json()
    assert p["success"] is True and isinstance(p["periods"], list)
