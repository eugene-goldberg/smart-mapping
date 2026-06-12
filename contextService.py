import db
import mappingEngine

def get_human_workflow():
    """
    Returns the markdown formatted list of steps a human operator takes when
    matching taxonomy concepts to positions.
    """
    return (
        "### 1. Human Operator Selection Workflow\n"
        "When matching regulatory ESG questions to internal operational database positions, "
        "human operators follow these steps in order:\n\n"
        "1. **Clear Naming Verification:** Ensure analytics and positions are named clearly so they describe the full content/requirement contained within.\n"
        "2. **Keyword Match Search:** Search for key words in the question, identifying positions/analytics which share those key words.\n"
        "3. **Semantic Alignment Check:** Evaluate if the position name (or names combined if there are multiple) clearly answers all parts of the question. If it matches fully, link them.\n"
        "4. **Detailed Description Fallback:** If the name alone is ambiguous, check the description and help text fields of the position to see if the detailed specifications clarify compatibility.\n"
        "5. **Candidate Iteration:** If a candidate fails validation, check the next candidate position and repeat the evaluation steps.\n"
        "6. **Naming Adjustment Flag:** If no position fits the concept and there is a struggle to match, flag that the position/analytic name needs adjusting/refining.\n"
    )

def get_tool_definitions():
    """
    Returns simulated/available tools descriptions that the agent uses.
    """
    return (
        "### 2. Available Database & Retrieval Tools\n"
        "The agent has access to the following operational tools to inspect the environment:\n\n"
        "*   `query_database(sql, params)`: Executes custom SQL reads against the SoFi database.\n"
        "*   `search_positions(query_text)`: Performs lexical keyword matches over the 2,537 available positions.\n"
        "*   `get_position_lineage(position_id)`: Fetches ancestral breadcrumbs and sub-tree descendants via the transitive closure table.\n"
        "*   `check_transaction_activity(position_id, site_id, period)`: Verifies if a candidate position contains actual operational measurements for a specific site and timeframe.\n"
    )

def get_few_shot_examples(taxonomy_id, limit=3):
    """
    Fetches actual validated mapping examples from the database for few-shot learning.
    """
    sql = """
        SELECT 
            tc.identifier as concept_identifier,
            tc.name as concept_name,
            tc.type as concept_type,
            tc.period_type as concept_period_type,
            pd.name as position_name,
            pd.description as position_desc,
            pt.position_type_name as position_type,
            p.path as position_path
        FROM position_taxonomy_concept ptc
        JOIN taxonomy_concept tc ON ptc.taxonomy_concept_id = tc.taxonomy_concept_id
        JOIN position p ON ptc.position_id = p.position_id
        JOIN position_dict pd ON p.position_id = pd.position_id AND p.term_start = pd.term_start
        JOIN position_types pt ON p.position_type = pt.position_type_id
        WHERE tc.taxonomy_id = %s
          AND pd.language_id = 2
          AND p.term_end IS NULL
        LIMIT %s
    """
    try:
        rows = db.query(sql, (taxonomy_id, limit))
    except Exception as e:
        print(f"Error fetching few-shot examples: {e}")
        rows = []

    markdown = "### 3. Historical Few-Shot Mapping Examples (Human Approved)\n"
    if not rows:
        # Fallback to rich default ESG examples if the taxonomy has no mappings yet
        markdown += (
            "Below are examples illustrating the human matching logic:\n\n"
            "**Example 1:**\n"
            "- **Taxonomy Concept:** `esrs_TotalElectricityConsumption` (Type: Quantitative, Period: duration)\n"
            "- **Mapped Position:** `Standard Grid` (Type: Flow, Path: `/SIL Testing/SIL Total Energy/SIL Total Electricity/Standard Grid`)\n"
            "- **Description:** Measures electricity drawn from public grid supplies.\n"
            "- **Human Logic Rationale:** The concept requires total electricity consumption. The position 'Standard Grid' represents grid electricity inputs. They share the energy context and represent standard grid flows.\n\n"
            "**Example 2:**\n"
            "- **Taxonomy Concept:** `esrs_DescriptionOfScopeOfKeyAction` (Type: Narrative, Period: duration)\n"
            "- **Mapped Position:** `CIText1` (Type: Text, Path: `/Base Data/CIText1`)\n"
            "- **Description:** Free-text explanation of climate change actions.\n"
            "- **Human Logic Rationale:** The concept asks for narrative text about action scopes. The position is a non-numeric 'Text' type field designed for explanatory logs, providing a clear match for descriptive requirements.\n"
        )
        return markdown

    for i, r in enumerate(rows):
        resolved_path = mappingEngine.resolve_position_path_names(r['position_path'])
        desc = r['position_desc'] or 'N/A'
        markdown += (
            f"**Example {i+1}:**\n"
            f"- **Taxonomy Concept:** `{r['concept_identifier']}` (Type: {r['concept_type']}, Period: {r['concept_period_type']})\n"
            f"- **Mapped Position:** `{r['position_name']}` (Type: {r['position_type']}, Path: `{resolved_path}`)\n"
            f"- **Description:** {desc}\n"
            f"- **Human Logic Rationale:** The human operator mapped this position because it shares the '{r['concept_name']}' context, matches the operational unit properties, and correctly aligns with temporal periods.\n\n"
        )
    return markdown

def assemble_llm_context(taxonomy_id, concept_id):
    """
    Main orchestrator that returns the full markdown prompt payload.
    """
    # 1. Fetch Target Concept Info
    concept_sql = "SELECT * FROM taxonomy_concept WHERE taxonomy_concept_id = %s AND taxonomy_id = %s"
    concept_rows = db.query(concept_sql, (concept_id, taxonomy_id))
    if not concept_rows:
        raise Exception(f"Concept {concept_id} not found in taxonomy {taxonomy_id}")
    concept = concept_rows[0]
    
    classification = 'Abstract Group' if concept['is_abstract'] else mappingEngine.classify_concept_type(concept['type'], concept['identifier'])
    
    # 2. Get Candidates from Heuristic Engine
    candidates = mappingEngine.predict_candidate_positions(taxonomy_id, concept_id, limit=5)

    # 3. Build Markdown Parts
    workflow_md = get_human_workflow()
    tools_md = get_tool_definitions()
    few_shot_md = get_few_shot_examples(taxonomy_id, limit=3)
    
    # Format Target Concept Details
    target_md = (
        "### 4. Target Query Concept to Evaluate\n"
        f"- **Identifier:** `{concept['identifier']}`\n"
        f"- **Concept Name:** `{concept['name']}`\n"
        f"- **Data Type:** `{concept['type']}`\n"
        f"- **Classification:** `{classification}`\n"
        f"- **Period Type:** `{concept['period_type']}`\n\n"
    )

    # Format Candidates Details
    candidates_md = "### 5. Candidate Positions (Heuristically Retrieved)\n"
    if not candidates:
        candidates_md += "No candidate positions retrieved by the heuristic engine.\n\n"
    else:
        for idx, c in enumerate(candidates):
            # Fetch path and description for richness
            pos_info = db.query("""
                SELECT p.path, pd.description 
                FROM position p
                JOIN position_dict pd ON p.position_id = pd.position_id AND p.term_start = pd.term_start
                WHERE p.position_id = %s AND pd.language_id = 2 AND p.term_end IS NULL
                LIMIT 1
            """, (c['positionId'],))
            
            raw_path = pos_info[0]['path'] if pos_info else ''
            desc = pos_info[0]['description'] if pos_info else 'N/A'
            resolved_path = mappingEngine.resolve_position_path_names(raw_path)
            
            candidates_md += (
                f"**Candidate #{idx+1}:**\n"
                f"- **Position ID:** `{c['positionId']}`\n"
                f"- **Position Name:** `{c['positionName']}`\n"
                f"- **Type:** `{c['positionTypeName']}`\n"
                f"- **Path Lineage:** `{resolved_path}`\n"
                f"- **Unit Class Limit:** `{c['unitClassName']}`\n"
                f"- **Description:** {desc}\n"
                f"- **Heuristic Matching Score:** {c['score']}% (Lexical: {c['breakdown']['lexical']}%, Unit: {c['breakdown']['unit']}%, Temporal: {c['breakdown']['temporal']}%, Structural: {c['breakdown']['structural']}%)\n\n"
            )

    # Format Prompt Instruction
    instruction_md = (
        "### 6. System Prompt Instructions for LLM Reranker\n"
        "You are an expert ESG taxonomy matching assistant. Analyze the **Target Query Concept** against the **Candidate Positions** using the **Human Operator Selection Workflow**.\n\n"
        "**Your Task:**\n"
        "1. Apply the keyword-matching and semantic alignment steps (evaluating names, parent nodes, paths, and descriptions).\n"
        "2. Adjust/rank the candidates based on how fully their metadata answers the concept's reporting requirement.\n"
        "3. Provide natural-language reasoning justifying your rankings (specifically explaining why the top candidates match or do not match).\n"
        "4. Flag any candidates whose names are confusing or need modification using the `suggestedRename` attribute.\n\n"
        "**Expected Output JSON Schema:**\n"
        "```json\n"
        "{\n"
        "  \"targetConcept\": \"<concept_identifier>\",\n"
        "  \"rankings\": [\n"
        "    {\n"
        "      \"positionId\": 123,\n"
        "      \"positionName\": \"<position_name>\",\n"
        "      \"rank\": 1,\n"
        "      \"reasoning\": \"<explanation_referencing_workflow_steps>\",\n"
        "      \"suggestedRename\": \"<optional_new_name_if_adjustment_needed_else_null>\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "```\n"
    )

    # Combine everything
    full_payload = (
        "# ESG Taxonomy-to-Position Context engineered Prompt\n\n"
        "This context payload was compiled dynamically by the SoFi TS Smart-Mapping harness.\n\n"
        f"{workflow_md}\n"
        f"{tools_md}\n"
        f"{few_shot_md}\n"
        f"{target_md}\n"
        f"{candidates_md}\n"
        f"{instruction_md}"
    )

    return full_payload
