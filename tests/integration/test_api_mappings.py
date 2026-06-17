from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def _first_concrete_concept():
    tax = client.get("/api/taxonomies").json()["taxonomies"]
    tid = tax[0]["taxonomy_id"]
    concepts = client.get(f"/api/concepts/{tid}").json()["concepts"]
    concrete = [c for c in concepts if not c["isAbstract"]]
    return tid, concrete[0]


def test_post_mapping_validation_missing_fields():
    r = client.post("/api/mappings", json={})
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_post_mapping_nonexistent_position():
    _, concept = _first_concrete_concept()
    r = client.post("/api/mappings", json={"positionId": 999999999, "taxonomyConceptId": concept["taxonomyConceptId"]})
    assert r.status_code == 404
    assert r.json()["success"] is False


def test_map_then_unmap_roundtrip():
    tid, concept = _first_concrete_concept()
    cid = concept["taxonomyConceptId"]
    cands = client.get(f"/api/predictions/{tid}/{cid}").json()["candidates"]
    pid = cands[0]["positionId"]

    created = client.post("/api/mappings", json={"positionId": pid, "taxonomyConceptId": cid})
    assert created.status_code == 200 and created.json()["success"] is True

    deleted = client.delete(f"/api/mappings/{pid}/{cid}")
    assert deleted.status_code == 200 and deleted.json()["success"] is True
