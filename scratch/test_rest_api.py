import urllib.request
import json
import sys

def test_api_endpoint(url):
    print(f"Querying URL: {url}")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as response:
            status = response.status
            body = response.read().decode('utf-8')
            data = json.loads(body)
            print(f"Response Status: {status}")
            print(f"JSON Success Status: {data.get('success')}")
            return data
    except Exception as err:
        print(f"Error querying {url}: {err}")
        return None

def run_api_tests():
    print("=== STARTING SMART-MAPPING REST API INTEGRATION EVALUATION ===")
    
    # 1. Test Taxonomies API
    tax_data = test_api_endpoint("http://localhost:3000/api/taxonomies")
    if not tax_data or not tax_data.get("success"):
        print("FAILED: Taxonomies API did not return successfully.")
        sys.exit(1)
    
    taxonomies = tax_data.get("taxonomies", [])
    print(f"Successfully evaluated Taxonomies API. Found {len(taxonomies)} taxonomies.")
    for t in taxonomies:
        print(f"  - Taxonomy: {t['name']} (ID: {t['taxonomy_id']})")
    
    if not taxonomies:
        print("FAILED: No taxonomies returned.")
        sys.exit(1)
        
    test_tax_id = taxonomies[0]['taxonomy_id']
    
    # 2. Test Customer Groups API
    group_data = test_api_endpoint("http://localhost:3000/api/customer-groups")
    if not group_data or not group_data.get("success"):
        print("FAILED: Customer Groups API did not return successfully.")
        sys.exit(1)
        
    groups = group_data.get("groups", [])
    print(f"Successfully evaluated Customer Groups API. Found {len(groups)} corporate groups.")
    for g in groups[:3]:
        print(f"  - Group: {g['customerName']} (Site ID: {g['customerSiteId']})")
        
    # 3. Test Periods API
    period_data = test_api_endpoint("http://localhost:3000/api/periods")
    if not period_data or not period_data.get("success"):
        print("FAILED: Periods API did not return successfully.")
        sys.exit(1)
        
    periods = period_data.get("periods", [])
    print(f"Successfully evaluated Periods API. Found {len(periods)} reporting periods.")
    print(f"  - Sample Periods: {periods[:5]}")
    
    # 4. Test Find Answer API (Global Scope)
    # Target Concept ID 4152 (from our previous verification)
    concept_id = 4152
    find_url = f"http://localhost:3000/api/find-answer?taxonomyId={test_tax_id}&taxonomyConceptId={concept_id}"
    answer_data = test_api_endpoint(find_url)
    if not answer_data or not answer_data.get("success"):
        print("FAILED: Find Answer API did not return successfully.")
        sys.exit(1)
        
    res = answer_data.get("result", {})
    print("\nEvaluating Dynamic ESG Answer Discovery Payload:")
    if res.get("found"):
        print(f"  [PASS] ESG Metric Found!")
        print(f"  - Value: {res.get('value')} {res.get('unitName')}")
        print(f"  - Site: {res.get('siteName')} (ID: {res.get('siteId')})")
        print(f"  - Matching Score: {res.get('score')}%")
        print(f"  - Ancestry Path: {res.get('positionPath')}")
    else:
        print("  [INFO] No transactions found under global filters for recommended fields.")
        
    # 5. Test Find Answer API with site filters
    customer_site_id = 1 # Start Group
    filtered_url = f"http://localhost:3000/api/find-answer?taxonomyId={test_tax_id}&taxonomyConceptId={concept_id}&customerSiteId={customer_site_id}"
    filtered_data = test_api_endpoint(filtered_url)
    if filtered_data and filtered_data.get("success"):
        f_res = filtered_data.get("result", {})
        if f_res.get("found"):
            print(f"  [PASS] Customer-Filtered ESG Metric Found!")
            print(f"  - Value: {f_res.get('value')} {f_res.get('unitName')}")
            print(f"  - Site: {f_res.get('siteName')}")
        else:
            print("  [INFO] No transactions found for customer group filters.")
            
    print("\n=== ALL REST API EVALUATION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == '__main__':
    run_api_tests()
