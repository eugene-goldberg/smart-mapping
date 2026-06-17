from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from . import db, mappingEngine, contextService, llmService

router = APIRouter(prefix="/api")


def _error(message: str, status: int):
    return JSONResponse({"success": False, "error": message}, status_code=status)


@router.get("/taxonomies")
def get_taxonomies():
    try:
        sql = """
            SELECT t.taxonomy_id, td.name, t.uuid, t.created
            FROM taxonomy t
            JOIN taxonomy_dict td ON t.taxonomy_id = td.taxonomy_id
            WHERE td.language_id = 2
        """
        return {"success": True, "taxonomies": db.query(sql)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/concepts/{taxonomy_id}")
def get_concepts(taxonomy_id: int):
    try:
        return {"success": True, "concepts": mappingEngine.get_classified_concepts(taxonomy_id)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/predictions/{taxonomy_id}/{concept_id}")
def get_predictions(taxonomy_id: int, concept_id: int):
    try:
        candidates = mappingEngine.predict_candidate_positions(taxonomy_id, concept_id, 5)
        return {"success": True, "candidates": candidates}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/customer-groups")
def get_customer_groups():
    try:
        sql = """
            SELECT s.site_id as customerSiteId, sd.name as customerName
            FROM site s
            JOIN site_dict sd ON s.site_id = sd.site_id AND s.term_start = sd.term_start
            WHERE s.parent_site_id IS NULL
              AND sd.language_id = 2
              AND s.term_end IS NULL
            ORDER BY sd.name ASC
        """
        return {"success": True, "groups": db.query(sql)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/sites/{customer_site_id}")
def get_sub_sites(customer_site_id: int):
    try:
        sql = """
            SELECT s.site_id as siteId, sd.name as siteName
            FROM site s
            JOIN site_dict sd ON s.site_id = sd.site_id AND s.term_start = sd.term_start
            JOIN site_path sp ON s.site_id = sp.descendant_site_id AND s.term_start = sp.descendant_term_start
            WHERE sp.ancestor_site_id = %s
              AND sd.language_id = 2
              AND s.term_end IS NULL
              AND sp.depth > 0
            ORDER BY sd.name ASC
        """
        return {"success": True, "sites": db.query(sql, (customer_site_id,))}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/periods")
def get_periods():
    try:
        sql = "SELECT DISTINCT term_start as period FROM transaction ORDER BY period DESC LIMIT 50"
        rows = db.query(sql)
        return {"success": True, "periods": [r["period"] for r in rows]}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/llm-context/{taxonomy_id}/{concept_id}")
def get_llm_context(taxonomy_id: int, concept_id: int):
    try:
        return {"success": True, "context": contextService.assemble_llm_context(taxonomy_id, concept_id)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/llm-predictions/{taxonomy_id}/{concept_id}")
def get_llm_predictions(taxonomy_id: int, concept_id: int):
    try:
        return {"success": True, "results": llmService.query_llm_rerank(taxonomy_id, concept_id)}
    except Exception as e:
        return _error(str(e), 500)


@router.get("/find-answer")
def find_answer(
    taxonomyId: int = Query(default=None),
    taxonomyConceptId: int = Query(default=None),
    customerSiteId: int = Query(default=None),
    siteId: int = Query(default=None),
    period: int = Query(default=None),
):
    if not taxonomyId or not taxonomyConceptId:
        return _error("taxonomyId and taxonomyConceptId are required parameters.", 400)
    try:
        result = mappingEngine.find_best_answer(
            taxonomy_id=taxonomyId,
            taxonomy_concept_id=taxonomyConceptId,
            customer_site_id=customerSiteId,
            site_id=siteId,
            period=period,
        )
        return {"success": True, "result": result}
    except Exception as e:
        return _error(str(e), 500)


@router.post("/mappings")
def save_mapping(payload: dict = Body(default={})):
    position_id = payload.get("positionId")
    taxonomy_concept_id = payload.get("taxonomyConceptId")
    if not position_id or not taxonomy_concept_id:
        return _error("positionId and taxonomyConceptId are required.", 400)
    try:
        pos_check = db.query("SELECT position_id FROM position_index WHERE position_id = %s", (position_id,))
        if not pos_check:
            return _error(f"Position with ID {position_id} does not exist.", 404)

        concept_check = db.query(
            "SELECT taxonomy_concept_id, identifier FROM taxonomy_concept WHERE taxonomy_concept_id = %s",
            (taxonomy_concept_id,),
        )
        if not concept_check:
            return _error(f"Taxonomy concept with ID {taxonomy_concept_id} does not exist.", 404)

        identifier = concept_check[0]["identifier"]
        if not identifier or len(identifier) < 3:
            return _error("Taxonomy concept identifier is invalid.", 400)

        db.query(
            "INSERT IGNORE INTO position_taxonomy_concept (position_id, taxonomy_concept_id) VALUES (%s, %s)",
            (position_id, taxonomy_concept_id),
        )
        return {"success": True, "message": "Mapping successfully persisted."}
    except Exception as e:
        return _error(str(e), 500)


@router.delete("/mappings/{position_id}/{concept_id}")
def delete_mapping(position_id: int, concept_id: int):
    try:
        db.query(
            "DELETE FROM position_taxonomy_concept WHERE position_id = %s AND taxonomy_concept_id = %s",
            (position_id, concept_id),
        )
        return {"success": True, "message": "Mapping successfully removed."}
    except Exception as e:
        return _error(str(e), 500)
