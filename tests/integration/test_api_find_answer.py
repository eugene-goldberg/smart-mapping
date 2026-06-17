from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_find_answer_requires_params():
    r = client.get("/api/find-answer")
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_find_answer_returns_result_shape():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    tid = tax[0]["taxonomy_id"]
    concepts = client.get(f"/api/concepts/{tid}").json()["concepts"]
    cid = [c for c in concepts if not c["isAbstract"]][0]["taxonomyConceptId"]
    r = client.get(f"/api/find-answer?taxonomyId={tid}&taxonomyConceptId={cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "found" in body["result"]
