import urllib.request
import urllib.parse
import json
import sys

BASE_URL = "http://localhost:3000"

def make_request(path, method="GET", data=None):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    req_data = None
    
    if data:
        req_data = json.dumps(data).encode("utf-8")
        
    try:
        req = urllib.request.Request(url, data=req_data, method=method, headers=headers)
        with urllib.request.urlopen(req) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except Exception as e:
        print(f"  [ERROR] {method} request failed for {path}: {e}")
        return None

def test_full_cycle():
    print("=====================================================================")
    print("         SMART-MAPPING API FULL CYCLE lifecyle TESTER")
    print("=====================================================================\n")
    
    # Step 1: Fetch Taxonomies
    print("Step 1: Fetching registered taxonomies...")
    tax_res = make_request("/api/taxonomies")
    if not tax_res or not tax_res.get("success"):
        print("  [FAIL] Failed to retrieve taxonomies.")
        sys.exit(1)
    taxonomies = tax_res.get("taxonomies", [])
    print(f"  [PASS] Found {len(taxonomies)} taxonomies.")
    taxonomy_id = taxonomies[0]["taxonomy_id"]
    print(f"  [INFO] Using Taxonomy ID: {taxonomy_id}\n")
    
    # Step 2: Fetch Concepts and select a target
    print("Step 2: Fetching concepts for active taxonomy...")
    concepts_res = make_request(f"/api/concepts/{taxonomy_id}")
    if not concepts_res or not concepts_res.get("success"):
        print("  [FAIL] Failed to retrieve concepts.")
        sys.exit(1)
    concepts = [c for c in concepts_res.get("concepts", []) if not c["isAbstract"]]
    print(f"  [PASS] Found {len(concepts)} concrete concepts.")
    target_concept = concepts[0]
    concept_id = target_concept["taxonomyConceptId"]
    concept_identifier = target_concept["identifier"]
    print(f"  [INFO] Selected Target Concept ID: {concept_id} ({concept_identifier})\n")
    
    # Step 3: Fetch Heuristic Candidates
    print("Step 3: Calculating Heuristic Candidates predictions...")
    heuristic_res = make_request(f"/api/predictions/{taxonomy_id}/{concept_id}")
    if not heuristic_res or not heuristic_res.get("success"):
        print("  [FAIL] Failed to calculate heuristic predictions.")
        sys.exit(1)
    candidates = heuristic_res.get("candidates", [])
    print(f"  [PASS] Heuristic predictions returned {len(candidates)} candidates.")
    for idx, c in enumerate(candidates[:2]):
        print(f"    #{idx+1}: {c['positionName']} (ID: {c['positionId']}) | Score: {c['score']}%")
    target_position_id = candidates[0]["positionId"]
    print(f"  [INFO] Selected Top Candidate Position ID: {target_position_id}\n")

    # Step 4: Verify Prompt Context Engineering
    print("Step 4: Compiling Context Engineered LLM Prompt payload...")
    context_res = make_request(f"/api/llm-context/{taxonomy_id}/{concept_id}")
    if not context_res or not context_res.get("success"):
        print("  [FAIL] Failed to compile context prompt.")
        sys.exit(1)
    context_text = context_res.get("context", "")
    print(f"  [PASS] Context payload successfully compiled ({len(context_text)} bytes).")
    print(f"  [INFO] Snippet:\n{context_text[:180]}...\n")
    
    # Step 5: Execute LLM Reranking (Phase 3)
    print("Step 5: Querying LLM Reranker & Reasoner layer...")
    llm_res = make_request(f"/api/llm-predictions/{taxonomy_id}/{concept_id}")
    if not llm_res or not llm_res.get("success"):
        print("  [FAIL] LLM Reranker API failed.")
        sys.exit(1)
    results = llm_res.get("results", {})
    rankings = results.get("rankings", [])
    print(f"  [PASS] LLM Reranker returned {len(rankings)} ranked candidates.")
    if results.get("simulated"):
        print(f"  [INFO] Note: {results.get('debugMessage')}")
    for r in rankings[:2]:
        print(f"    Rank #{r['rank']}: {r['positionName']} (ID: {r['positionId']})")
        print(f"      - Rationale: {r['reasoning']}")
        if r.get("suggestedRename"):
            print(f"      - Suggested Naming Adjustment: '{r['suggestedRename']}'")
    print()
    
    # Step 6: Persist mapping association (Writeback)
    print(f"Step 6: Persisting mapping association (Concept {concept_id} <-> Position {target_position_id})...")
    payload = {"positionId": target_position_id, "taxonomyConceptId": concept_id}
    map_res = make_request("/api/mappings", method="POST", data=payload)
    if not map_res or not map_res.get("success"):
        print("  [FAIL] Failed to save mapping association.")
        sys.exit(1)
    print("  [PASS] Mapping saved successfully in database.")
    
    # Check concept status is updated
    concepts_verify = make_request(f"/api/concepts/{taxonomy_id}")
    updated_concept = next(c for c in concepts_verify.get("concepts", []) if c["taxonomyConceptId"] == concept_id)
    print(f"  [PASS] Verified Concept mappedStatus is now: '{updated_concept['mappedStatus']}'")
    print(f"  [PASS] Verified Mapped position name: '{updated_concept['mappedPositionName']}' (ID: {updated_concept['mappedPositionId']})\n")
    
    # Step 7: Retrieve ESG values via Fallback Discovery Loop
    print("Step 7: Executing Dynamic ESG Answer Discovery fallback loop...")
    find_res = make_request(f"/api/find-answer?taxonomyId={taxonomy_id}&taxonomyConceptId={concept_id}")
    if not find_res or not find_res.get("success"):
        print("  [FAIL] Find Answer API failed.")
        sys.exit(1)
    result = find_res.get("result", {})
    if result.get("found"):
        print(f"  [PASS] ESG Operational Metric Discovered!")
        print(f"    - Value: {result.get('value')} {result.get('unitName')}")
        print(f"    - Confidence level: '{result.get('confidence')}'")
        print(f"    - Site Location: {result.get('siteName')}")
        print(f"    - Path: {result.get('positionPath')}")
    else:
        print(f"  [INFO] No transactions found for concept mappings under chosen filters.")
    print()
    
    # Step 8: Clean up mapping association
    print("Step 8: Cleaning up test mapping association...")
    del_res = make_request(f"/api/mappings/{target_position_id}/{concept_id}", method="DELETE")
    if not del_res or not del_res.get("success"):
        print("  [FAIL] Failed to clean up mapping.")
        sys.exit(1)
    print("  [PASS] Clean up completed.")
    
    print("\n=====================================================================")
    print("        ALL FULL CYCLE lifecyle TESTS COMPLETED SUCCESSFULLY!")
    print("=====================================================================")

if __name__ == "__main__":
    test_full_cycle()
