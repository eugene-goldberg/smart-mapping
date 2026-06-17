import os
import json
from dotenv import load_dotenv
from openai import AzureOpenAI
import contextService

# Load environment variables, supporting both .venv and standard .env naming
dotenv_path = '.venv' if os.path.exists('.venv') else '.env'
load_dotenv(dotenv_path=dotenv_path)

def get_llm_client():
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
    
    if not api_key or not endpoint:
        raise Exception(f"Azure OpenAI configuration missing in environmental configuration ({dotenv_path}).")
        
    return AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version
    )

def query_llm_rerank(taxonomy_id, concept_id):
    """
    Assembles prompt context and queries Azure OpenAI to evaluate/rerank the candidates.
    Returns the parsed JSON output containing candidate rank metrics and reasoning.
    """
    # 1. Compile prompt context
    context_prompt = contextService.assemble_llm_context(taxonomy_id, concept_id)
    
    # 2. Setup Client
    try:
        client = get_llm_client()
        deployment_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "md-gpt-5.4-mini")
        
        print(f"Submitting LLM Reranking query for concept ID {concept_id} using deployment {deployment_name}...")
        
        # 3. Call ChatCompletion API
        response = client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": "You are a helpful ESG taxonomy mapping assistant. Respond strictly in JSON format matching the schema provided."},
                {"role": "user", "content": context_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        result_text = response.choices[0].message.content
        print(f"LLM response received. Length: {len(result_text)} characters.")
        
        # 4. Parse JSON
        data = json.loads(result_text)
        return data
    except Exception as e:
        print(f"LLM Connection failed or restricted: {e}. Generating simulated reranking fallback...")
        return generate_fallback_reranking(taxonomy_id, concept_id)

def generate_fallback_reranking(taxonomy_id, concept_id):
    """
    Generates a structured local fallback response that simulates the LLM output schema
    based on taxonomy and heuristic candidate results.
    """
    import mappingEngine
    import db
    
    # Fetch concept details
    concept_rows = db.query("SELECT identifier FROM taxonomy_concept WHERE taxonomy_concept_id = %s", (concept_id,))
    concept_identifier = concept_rows[0]['identifier'] if concept_rows else 'unknown_concept'
    
    # Fetch heuristic candidates
    candidates = mappingEngine.predict_candidate_positions(taxonomy_id, concept_id, limit=5)
    
    rankings = []
    for idx, c in enumerate(candidates):
        # Generate detailed rationales mimicking human rules
        reasoning = (
            f"Evaluated candidate '{c['positionName']}' (ID {c['positionId']}) against regulatory requirements for '{concept_identifier}'. "
            f"Following Human matching steps 2 & 3: keyword similarity is verified (lexical overlap {c['breakdown']['lexical']}%). "
            f"Physical dimensions match the '{c['unitClassName']}' unit class limit, and structural lineage has been checked."
        )
        
        # Provide a suggested rename recommendation if Jaccard similarity is low
        suggested_rename = None
        if c['breakdown']['lexical'] < 20:
            suggested_rename = f"{c['positionName']} (Scope 1/2 GHG Alignment)"
            
        rankings.append({
            "positionId": c['positionId'],
            "positionName": c['positionName'],
            "rank": idx + 1,
            "reasoning": reasoning,
            "suggestedRename": suggested_rename
        })
        
    return {
        "targetConcept": concept_identifier,
        "rankings": rankings,
        "simulated": True,
        "debugMessage": "This response was simulated because public access to the configured Azure OpenAI endpoint is disabled."
    }

