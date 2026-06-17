import re
import json
import db

def classify_concept_type(type_str, identifier):
    """
    Capability 1: Standard Classifications of XBRL Taxonomy Concepts
    """
    if not type_str:
        return 'Other'
    
    type_lower = type_str.lower()
    id_lower = identifier.lower()

    # Quantitative Types
    if any(term in type_lower for term in [
        'decimal', 'monetary', 'percent', 'integer', 'volume', 
        'mass', 'area', 'shares', 'energy'
    ]):
        return 'Quantitative'

    # Narrative Types
    if 'textblock' in type_lower or 'string' in type_lower:
        # Short unique code or identifiers are classified as Compliance Metadata
        if any(term in id_lower for term in ['lei', 'identifier', 'code']):
            return 'Metadata'
        return 'Narrative'

    # Choice / Enumeration Types
    if 'enumeration' in type_lower or 'boolean' in type_lower:
        return 'Choice'

    return 'Other'

def infer_unit_class_from_concept(identifier, type_str):
    """
    Inferred unit classes from Concept identifiers or data types
    """
    text = f"{identifier}_{type_str or ''}".lower()
    unit_classes = []

    # Match mass/emissions/CO2 (Mass = 10, GWP = 48, 84)
    if any(term in text for term in ['emission', 'co2', 'gas', 'ghg', 'carbon', 'mass', 'waste']):
        unit_classes.extend([10, 48, 84])
    # Match currency/monetary (Currency = 40)
    if any(term in text for term in ['monetary', 'revenue', 'cost', 'currency', 'eur', 'usd', 'price']):
        unit_classes.append(40)
    # Match energy (Energy = 7)
    if any(term in text for term in ['energy', 'electricity', 'fuel', 'coal', 'gas', 'power', 'kwh', 'mwh']):
        unit_classes.append(7)
    # Match employee/people count (Employees = 6, Number = 38)
    if any(term in text for term in ['employee', 'people', 'staff', 'headcount', 'number', 'count']):
        unit_classes.extend([6, 38])
    # Match percent/fraction (Percent = 3)
    if any(term in text for term in ['percent', 'ratio', 'fraction', 'rate']):
        unit_classes.append(3)
    # Match area (Area = 1)
    if any(term in text for term in ['area', 'sqft', 'sqm', 'hectare', 'footprint']):
        unit_classes.append(1)
    # Match volume (Volume = 17)
    if any(term in text for term in ['volume', 'litre', 'water', 'liquid', 'gas', 'm3']):
        unit_classes.append(17)
    # Match distance (Distance = 4)
    if any(term in text for term in ['distance', 'km', 'mile', 'haul']):
        unit_classes.append(4)

    return unit_classes

def tokenize_string(s):
    """
    Tokenizes camelCase, PascalCase, snake_case, and namespaces, omitting stop words.
    """
    if not s:
        return []
    
    # Split snake_case, namespaces and special separations
    words = re.sub(r'[:_#]', ' ', s).split()
    
    # Split camelCase / PascalCase
    tokens = []
    for word in words:
        split = re.sub(r'([a-z])([A-Z])', r'\1 \2', word).split()
        tokens.extend(split)

    stop_words = {'esrs', 'gri', 'item', 'type', 'the', 'and', 'for', 'with', 'explanatory'}
    return [
        t.lower() for t in tokens 
        if len(t) > 2 and t.lower() not in stop_words
    ]

def calculate_lexical_overlap(concept_tokens, position_tokens):
    """
    Calculates Jaccard similarity and partial substring match overlaps
    """
    if not concept_tokens or not position_tokens:
        return 0.0
    
    concept_set = set(concept_tokens)
    position_set = set(position_tokens)

    intersection = 0.0
    for token in position_set:
        if token in concept_set:
            intersection += 1.0
        else:
            # Add a partial boost if substrings are related
            for c_token in concept_set:
                if token in c_token or c_token in token:
                    intersection += 0.5
                    break

    union = len(concept_set) + len(position_set) - int(intersection)
    return intersection / union if union > 0 else 0.0

def get_classified_concepts(taxonomy_id):
    """
    Capabilities 1 Engine: Fetch and classify all taxonomy concepts
    """
    # Load concepts and check mapping status along with mapped position details if any
    sql = """
        SELECT 
          tc.taxonomy_concept_id, 
          tc.identifier, 
          tc.name, 
          tc.type, 
          tc.presentation_type, 
          tc.period_type, 
          tc.sub_group, 
          tc.is_abstract,
          (SELECT ptc.position_id FROM position_taxonomy_concept ptc WHERE ptc.taxonomy_concept_id = tc.taxonomy_concept_id LIMIT 1) as mapped_position_id,
          (SELECT pd.name 
           FROM position_dict pd 
           JOIN position p ON pd.position_id = p.position_id AND pd.term_start = p.term_start
           WHERE pd.position_id = (SELECT ptc.position_id FROM position_taxonomy_concept ptc WHERE ptc.taxonomy_concept_id = tc.taxonomy_concept_id LIMIT 1) 
             AND pd.language_id = 2 
             AND p.term_end IS NULL
           LIMIT 1) as mapped_position_name
        FROM taxonomy_concept tc
        WHERE tc.taxonomy_id = %s
        ORDER BY tc.is_abstract DESC, tc.identifier ASC
    """
    concepts = db.query(sql, (taxonomy_id,))

    result = []
    for c in concepts:
        is_abstract = c['is_abstract'] == 1 or c['is_abstract'] is True
        has_mapping = c['mapped_position_id'] is not None
        
        result.append({
            'taxonomyConceptId': c['taxonomy_concept_id'],
            'identifier': c['identifier'],
            'name': c['name'],
            'type': c['type'],
            'presentationType': c['presentation_type'],
            'periodType': c['period_type'],
            'subGroup': c['sub_group'],
            'isAbstract': is_abstract,
            'mappedStatus': 'Mapped' if has_mapping else 'Unmapped',
            'mappedPositionId': c['mapped_position_id'],
            'mappedPositionName': c['mapped_position_name'],
            'classification': 'Abstract Group' if is_abstract else classify_concept_type(c['type'], c['identifier'])
        })
    return result

def find_parent_in_tree(tree_node, target_identifier, current_parent=None):
    """
    Locates a concept's parent node identifier recursively in the presentation tree
    """
    node_id = tree_node.get('nodeId') or tree_node.get('id')
    if node_id == target_identifier:
        return current_parent

    children = tree_node.get('children')
    if children and isinstance(children, list):
        for child in children:
            parent = find_parent_in_tree(child, target_identifier, tree_node)
            if parent:
                return parent
    return None

def predict_candidate_positions(taxonomy_id, taxonomy_concept_id, limit=5):
    """
    Capabilities 2 Engine: Predict the best candidate Position for a concept
    """
    # 1. Fetch target concept
    concept_sql = "SELECT * FROM taxonomy_concept WHERE taxonomy_concept_id = %s AND taxonomy_id = %s"
    concept_rows = db.query(concept_sql, (taxonomy_concept_id, taxonomy_id))
    if not concept_rows:
        raise Exception(f"Concept with ID {taxonomy_concept_id} not found in taxonomy {taxonomy_id}")
    
    concept = concept_rows[0]
    
    is_quantitative = classify_concept_type(concept['type'], concept['identifier']) == 'Quantitative'
    concept_tokens = tokenize_string(concept['identifier'])
    inferred_unit_classes = infer_unit_class_from_concept(concept['identifier'], concept['type'])

    # 2. Fetch active temporal slice of all positions, fully compatible with ONLY_FULL_GROUP_BY
    positions_sql = """
        SELECT 
          p.position_id,
          pd.name as position_name,
          pd.description as position_desc,
          p.position_type as position_type_id,
          pt.position_type_name,
          p.unit_class_id,
          ucd.name as unit_class_name,
          p.answer_type
        FROM position p
        JOIN position_index pi ON p.position_id = pi.position_id
        JOIN position_dict pd ON p.position_id = pd.position_id AND p.term_start = pd.term_start
        JOIN position_types pt ON p.position_type = pt.position_type_id
        LEFT JOIN unit_class_dict ucd ON p.unit_class_id = ucd.unit_class_id AND ucd.language_id = 2
        WHERE pd.language_id = 2
          AND p.term_end IS NULL
    """
    positions = db.query(positions_sql)

    # 3. Structural Heuristics Prep: Load the Taxonomy Presentation JSON Tree
    tax_sql = "SELECT presentation FROM taxonomy WHERE taxonomy_id = %s"
    taxonomy_rows = db.query(tax_sql, (taxonomy_id,))
    
    parent_concept_node = None
    if taxonomy_rows and taxonomy_rows[0].get('presentation'):
        presentation_tree = taxonomy_rows[0]['presentation']
        if isinstance(presentation_tree, str):
            try:
                presentation_tree = json.loads(presentation_tree)
            except Exception:
                presentation_tree = None
        
        if presentation_tree:
            parent_concept_node = find_parent_in_tree(presentation_tree, concept['identifier'])

    # Load existing database mappings to resolve parent concept maps
    active_parent_mappings = []
    if parent_concept_node:
        parent_id = parent_concept_node.get('id') or parent_concept_node.get('nodeId')
        parent_mappings_sql = """
            SELECT ptc.position_id
            FROM position_taxonomy_concept ptc
            JOIN taxonomy_concept tc ON ptc.taxonomy_concept_id = tc.taxonomy_concept_id
            WHERE tc.identifier = %s AND tc.taxonomy_id = %s
        """
        active_parent_mappings = db.query(parent_mappings_sql, (parent_id, taxonomy_id))

    scored_candidates = []

    for pos in positions:
        # Score factors (0.0 to 1.0)
        s_lexical = 0.0
        s_unit = 0.5  # Neutral starting weight
        s_temporal = 0.5
        s_structural = 0.0

        # A. Lexical Overlap
        pos_tokens = tokenize_string(f"{pos['position_name']} {pos['position_desc'] or ''}")
        s_lexical = calculate_lexical_overlap(concept_tokens, pos_tokens)

        # B. Unit Class Compatibility
        if is_quantitative:
            if pos['unit_class_id']:
                if inferred_unit_classes:
                    if pos['unit_class_id'] in inferred_unit_classes:
                        s_unit = 1.0  # Exact match
                    else:
                        s_unit = 0.05  # Heavy mismatch penalty
                else:
                    s_unit = 0.7  # Numeric matched with generic quantitative
            else:
                s_unit = 0.2  # Quantitative concept needs a numeric unit, position has none
        else:
            # Qualitative / Narrative / Choice
            if pos['unit_class_id']:
                s_unit = 0.1  # Numeric position for text/boolean concept is highly unlikely
            else:
                s_unit = 0.8  # Non-numeric matched with non-numeric

        # C. Temporal / Period Style Alignment
        period_lower = (concept['period_type'] or '').lower()
        is_flow_or_indicator = pos['position_type_name'] in ['Flow', 'Indicator']
        if period_lower == 'duration':
            s_temporal = 0.9 if is_flow_or_indicator else 0.4
        elif period_lower == 'instant':
            s_temporal = 0.8 if not is_flow_or_indicator else 0.3

        # D. Structural Heuristics propagation (using closure table position_path)
        if parent_concept_node and active_parent_mappings:
            parent_pos_ids = [m['position_id'] for m in active_parent_mappings]
            
            # Query position_path closure table to check if this position has any mapped parent as ancestor
            # PyMySQL requires IN (%s, %s...) placeholder formatting. 
            # If parent_pos_ids has entries, let's construct placeholders safely.
            placeholders = ', '.join(['%s'] * len(parent_pos_ids))
            ancestor_sql = f"""
                SELECT COUNT(*) as count 
                FROM position_path 
                WHERE descendant_position_id = %s AND ancestor_position_id IN ({placeholders})
            """
            params = [pos['position_id']] + parent_pos_ids
            path_check = db.query(ancestor_sql, params)
            if path_check and path_check[0]['count'] > 0:
                s_structural = 1.0  # Transitive ancestral boost!

        # Weighted final score calculation
        # w1 = 0.5 (Lexical), w2 = 0.3 (Unit), w3 = 0.1 (Temporal), w4 = 0.1 (Structural)
        final_score = (s_lexical * 0.5) + (s_unit * 0.3) + (s_temporal * 0.1) + (s_structural * 0.1)

        scored_candidates.append({
            'positionId': pos['position_id'],
            'positionName': pos['position_name'],
            'positionTypeName': pos['position_type_name'],
            'unitClassName': pos['unit_class_name'] or 'N/A',
            'score': round(final_score * 100.0, 1),
            'breakdown': {
                'lexical': int(round(s_lexical * 100.0)),
                'unit': int(round(s_unit * 100.0)),
                'temporal': int(round(s_temporal * 100.0)),
                'structural': int(round(s_structural * 100.0))
            }
        })

    # Sort candidates by final score descending
    scored_candidates.sort(key=lambda x: x['score'], reverse=True)

    return scored_candidates[:limit]

def resolve_position_path_names(path_str):
    """
    Resolves a raw materialized path (e.g. '/1/15/22') into localized English names.
    """
    if not path_str:
        return "N/A"
    parts = [p.strip() for p in path_str.split('/') if p.strip()]
    if not parts:
        return "N/A"
    try:
        placeholders = ', '.join(['%s'] * len(parts))
        sql = f"""
            SELECT pd.position_id, pd.name 
            FROM position_dict pd
            JOIN position p ON pd.position_id = p.position_id AND pd.term_start = p.term_start
            WHERE pd.position_id IN ({placeholders}) 
              AND pd.language_id = 2 
              AND p.term_end IS NULL
        """
        rows = db.query(sql, tuple(int(x) for x in parts))
        name_map = {r['position_id']: r['name'] for r in rows}
        resolved = [name_map.get(int(x), f"ID {x}") for x in parts]
        return " / ".join(resolved)
    except Exception as e:
        print(f"Error resolving path names: {e}")
        return path_str

def find_best_answer(taxonomy_id, taxonomy_concept_id, customer_site_id=None, site_id=None, period=None):
    """
    Finds the best possible actual ESG answer value for a given taxonomy concept
    based on computed predictions and temporal transaction data.
    """
    # 1. Fetch top candidate recommendations (up to 20 to widen the transaction search)
    candidates = predict_candidate_positions(taxonomy_id, taxonomy_concept_id, limit=20)
    if not candidates:
        return {'found': False, 'candidates': []}

    # Load existing direct mappings to check for direct matches
    mappings_sql = "SELECT position_id FROM position_taxonomy_concept WHERE taxonomy_concept_id = %s"
    mapped_rows = db.query(mappings_sql, (taxonomy_concept_id,))
    mapped_pos_ids = {m['position_id'] for m in mapped_rows}

    # Compute historic baseline preference for this customer if a customer context exists
    historic_preferences = {}
    resolved_customer_id = customer_site_id
    
    # If customer group isn't provided but a site_id is, resolve the customer (root ancestor site)
    if not resolved_customer_id and site_id:
        try:
            # Query parent site until parent_site_id IS NULL to find root ancestor
            root_sql = """
                SELECT ancestor_site_id 
                FROM site_path 
                WHERE descendant_site_id = %s
                  AND ancestor_site_id IN (SELECT site_id FROM site WHERE parent_site_id IS NULL)
                LIMIT 1
            """
            root_res = db.query(root_sql, (site_id,))
            if root_res:
                resolved_customer_id = root_res[0]['ancestor_site_id']
        except Exception as e:
            print(f"Error resolving root customer site ID: {e}")

    if resolved_customer_id:
        try:
            cand_ids = [c['positionId'] for c in candidates]
            placeholders = ', '.join(['%s'] * len(cand_ids))
            pref_sql = f"""
                SELECT 
                  t.position_id, 
                  COUNT(DISTINCT LEFT(t.term_start, 4)) as distinct_years,
                  COUNT(*) as total_transactions
                FROM transaction t
                WHERE t.position_id IN ({placeholders})
                  AND t.site_id IN (SELECT descendant_site_id FROM site_path WHERE ancestor_site_id = %s)
                GROUP BY t.position_id
            """
            pref_params = cand_ids + [resolved_customer_id]
            prefs = db.query(pref_sql, tuple(pref_params))
            # Map position_id to its historic metrics
            historic_preferences = {p['position_id']: p for p in prefs}
        except Exception as e:
            print(f"Error calculating historic preferences: {e}")

    # 2. Iterate through candidates in ranked order to find the first one with matching data
    for cand in candidates:
        pos_id = cand['positionId']

        sql = """
            SELECT 
              t.transaction_id, 
              t.quantity, 
              t.answer_text, 
              t.occurrence_date, 
              t.term_start as period,
              sd.name as site_name,
              p.path as position_path,
              ucd.name as unit_name
            FROM transaction t
            JOIN position p ON t.position_id = p.position_id 
              AND p.term_start <= t.term_start 
              AND (p.term_end IS NULL OR p.term_end >= t.term_start)
            JOIN site_dict sd ON t.site_id = sd.site_id AND sd.language_id = 2
            LEFT JOIN unit_class_dict ucd ON p.unit_class_id = ucd.unit_class_id AND ucd.language_id = 2
            WHERE t.position_id = %s
        """
        params = [pos_id]

        if site_id:
            sql += " AND t.site_id = %s"
            params.append(site_id)
        elif customer_site_id:
            sql += " AND t.site_id IN (SELECT descendant_site_id FROM site_path WHERE ancestor_site_id = %s)"
            params.append(customer_site_id)

        if period:
            sql += " AND t.term_start = %s"
            params.append(period)

        sql += " ORDER BY t.occurrence_date DESC, t.transaction_id DESC LIMIT 1"

        res = db.query(sql, tuple(params))
        if res:
            row = res[0]
            val = row['quantity'] if row['quantity'] is not None else row['answer_text']
            
            # Skip if both are None
            if val is None:
                continue

            # Resolve confidence
            if pos_id in mapped_pos_ids:
                confidence = 'Mapped Direct Answer'
            elif cand['score'] >= 80.0:
                confidence = 'High Confidence Prediction'
            elif cand['score'] >= 50.0:
                confidence = 'Medium Confidence Prediction'
            else:
                confidence = 'Low Confidence Prediction'

            resolved_path = resolve_position_path_names(row['position_path'])

            # Render datetime safely
            occ_date_str = None
            if row['occurrence_date']:
                try:
                    occ_date_str = row['occurrence_date'].strftime('%Y-%m-%d')
                except Exception:
                    occ_date_str = str(row['occurrence_date'])

            # Parse historic preference details
            pref_meta = historic_preferences.get(pos_id)
            distinct_years = pref_meta['distinct_years'] if pref_meta else 0
            total_trans = pref_meta['total_transactions'] if pref_meta else 0

            return {
                'found': True,
                'positionId': pos_id,
                'positionName': cand['positionName'],
                'positionTypeName': cand['positionTypeName'],
                'score': cand['score'],
                'breakdown': cand['breakdown'],
                'value': val,
                'isNumeric': row['quantity'] is not None,
                'unitName': row['unit_name'] or 'N/A',
                'period': row['period'],
                'occurrenceDate': occ_date_str,
                'siteName': row['site_name'],
                'positionPath': resolved_path,
                'confidence': confidence,
                'historicPreference': {
                    'distinctYears': distinct_years,
                    'totalTransactions': total_trans,
                    'isPreferred': distinct_years >= 2
                }
            }

    # If no candidate has data, attach historic baseline insights to recommendations
    recs = []
    for cand in candidates[:5]:
        pos_id = cand['positionId']
        pref_meta = historic_preferences.get(pos_id)
        distinct_years = pref_meta['distinct_years'] if pref_meta else 0
        total_trans = pref_meta['total_transactions'] if pref_meta else 0
        
        recs.append({
            **cand,
            'historicPreference': {
                'distinctYears': distinct_years,
                'totalTransactions': total_trans,
                'isPreferred': distinct_years >= 2
            }
        })

    return {
        'found': False,
        'candidates': recs
    }


