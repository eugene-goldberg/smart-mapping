import os
from flask import Flask, jsonify, request, send_from_directory
import db
import mappingEngine

app = Flask(__name__, static_folder='public', static_url_path='')

# 1. Serve static frontend assets from 'public' directory
@app.route('/')
def index():
    return app.send_static_file('index.html')

# Flask serves index.css and app.js automatically because static_url_path='' and static_folder='public'
# But let's add a robust fallback just in case:
@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)

# 2. GET /api/taxonomies - Fetch registered taxonomies and localized English names
@app.route('/api/taxonomies', methods=['GET'])
def get_taxonomies():
    try:
        sql = """
            SELECT t.taxonomy_id, td.name, t.uuid, t.created 
            FROM taxonomy t 
            JOIN taxonomy_dict td ON t.taxonomy_id = td.taxonomy_id 
            WHERE td.language_id = 2
        """
        taxonomies = db.query(sql)
        return jsonify({'success': True, 'taxonomies': taxonomies})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 3. GET /api/concepts/:taxonomyId - Get classified concepts for visual listing
@app.route('/api/concepts/<int:taxonomy_id>', methods=['GET'])
def get_concepts(taxonomy_id):
    try:
        concepts = mappingEngine.get_classified_concepts(taxonomy_id)
        return jsonify({'success': True, 'concepts': concepts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 4. GET /api/predictions/:taxonomyId/:conceptId - Predict candidates with breakdowns
@app.route('/api/predictions/<int:taxonomy_id>/<int:concept_id>', methods=['GET'])
def get_predictions(taxonomy_id, concept_id):
    try:
        candidates = mappingEngine.predict_candidate_positions(taxonomy_id, concept_id, 5)
        return jsonify({'success': True, 'candidates': candidates})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 5. POST /api/mappings - Create an active mapping association
@app.route('/api/mappings', methods=['POST'])
def save_mapping():
    data = request.json or {}
    position_id = data.get('positionId')
    taxonomy_concept_id = data.get('taxonomyConceptId')

    if not position_id or not taxonomy_concept_id:
        return jsonify({'success': False, 'error': 'positionId and taxonomyConceptId are required.'}), 400

    try:
        # A. Validate existence of position
        pos_check = db.query('SELECT position_id FROM position_index WHERE position_id = %s', (position_id,))
        if not pos_check:
            return jsonify({'success': False, 'error': f"Position with ID {position_id} does not exist."}), 404

        # B. Validate existence and namespace of taxonomy concept
        concept_check = db.query('SELECT taxonomy_concept_id, identifier FROM taxonomy_concept WHERE taxonomy_concept_id = %s', (taxonomy_concept_id,))
        if not concept_check:
            return jsonify({'success': False, 'error': f"Taxonomy concept with ID {taxonomy_concept_id} does not exist."}), 404

        identifier = concept_check[0]['identifier']
        if not identifier or len(identifier) < 3:
            return jsonify({'success': False, 'error': 'Taxonomy concept identifier is invalid.'}), 400

        # C. Write to join table (using INSERT IGNORE to prevent duplicate index exceptions)
        db.query("""
            INSERT IGNORE INTO position_taxonomy_concept (position_id, taxonomy_concept_id) 
            VALUES (%s, %s)
        """, (position_id, taxonomy_concept_id))

        print(f"Saved mapping: Position {position_id} <-> Concept {taxonomy_concept_id} ({identifier})")
        return jsonify({'success': True, 'message': 'Mapping successfully persisted.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 6. DELETE /api/mappings/:positionId/:conceptId - Remove an association
@app.route('/api/mappings/<int:position_id>/<int:concept_id>', methods=['DELETE'])
def delete_mapping(position_id, concept_id):
    try:
        db.query("""
            DELETE FROM position_taxonomy_concept 
            WHERE position_id = %s AND taxonomy_concept_id = %s
        """, (position_id, concept_id))

        print(f"Deleted mapping: Position {position_id} <-> Concept {concept_id}")
        return jsonify({'success': True, 'message': 'Mapping successfully removed.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 7. GET /api/customer-groups - Fetch top-level corporate sites
@app.route('/api/customer-groups', methods=['GET'])
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
        groups = db.query(sql)
        return jsonify({'success': True, 'groups': groups})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 8. GET /api/sites/:customer_site_id - Fetch all operational sub-sites under customer hierarchy
@app.route('/api/sites/<int:customer_site_id>', methods=['GET'])
def get_sub_sites(customer_site_id):
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
        sites = db.query(sql, (customer_site_id,))
        return jsonify({'success': True, 'sites': sites})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 9. GET /api/periods - Fetch distinct transaction periods (limited to top 50)
@app.route('/api/periods', methods=['GET'])
def get_periods():
    try:
        sql = "SELECT DISTINCT term_start as period FROM transaction ORDER BY period DESC LIMIT 50"
        rows = db.query(sql)
        periods = [r['period'] for r in rows]
        return jsonify({'success': True, 'periods': periods})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 10. GET /api/find-answer - Predictive ESG value query resolver
@app.route('/api/find-answer', methods=['GET'])
def find_answer():
    taxonomy_id = request.args.get('taxonomyId', type=int)
    taxonomy_concept_id = request.args.get('taxonomyConceptId', type=int)
    customer_site_id = request.args.get('customerSiteId', type=int)
    site_id = request.args.get('siteId', type=int)
    period = request.args.get('period', type=int)

    if not taxonomy_id or not taxonomy_concept_id:
        return jsonify({'success': False, 'error': 'taxonomyId and taxonomyConceptId are required parameters.'}), 400

    try:
        result = mappingEngine.find_best_answer(
            taxonomy_id=taxonomy_id,
            taxonomy_concept_id=taxonomy_concept_id,
            customer_site_id=customer_site_id,
            site_id=site_id,
            period=period
        )
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 11. GET /api/llm-context/:taxonomyId/:conceptId - Fetch compiled LLM prompt context
@app.route('/api/llm-context/<int:taxonomy_id>/<int:concept_id>', methods=['GET'])
def get_llm_context(taxonomy_id, concept_id):
    try:
        import contextService
        context = contextService.assemble_llm_context(taxonomy_id, concept_id)
        return jsonify({'success': True, 'context': context})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 12. GET /api/llm-predictions/:taxonomyId/:conceptId - Get LLM reranked candidates and justifications
@app.route('/api/llm-predictions/<int:taxonomy_id>/<int:concept_id>', methods=['GET'])
def get_llm_predictions(taxonomy_id, concept_id):
    try:
        import llmService
        results = llmService.query_llm_rerank(taxonomy_id, concept_id)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Start Flask Development Server
if __name__ == '__main__':
    PORT = int(os.environ.get('PORT', 3000))
    print(f"Smart-Mapping Python service running locally at http://localhost:{PORT}")
    print("Press Ctrl+C to terminate server.")
    app.run(host='0.0.0.0', port=PORT, debug=True)

