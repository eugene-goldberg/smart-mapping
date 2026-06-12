/**
 * Sofi Smart-Mapping Application Client Controller
 * Responsive state-management, multi-factor breakdowns, and DB writeback persistence.
 */

// 1. Core State
const state = {
  taxonomies: [],
  concepts: [],
  filteredConcepts: [],
  selectedTaxonomy: null,
  activeFilter: 'all',
  searchQuery: '',
  activeConcept: null
};

// 2. DOM Elements Cache
const DOM = {
  taxonomySelector: document.getElementById('taxonomy_selector'),
  taxonomyTitle: document.getElementById('taxonomy_title'),
  taxonomySubtitle: document.getElementById('taxonomy_subtitle'),
  conceptsTableBody: document.getElementById('concepts_table_body'),
  conceptSearch: document.getElementById('concept_search'),
  
  // Navigation filters
  filterAll: document.getElementById('filter_all'),
  filterQuantitative: document.getElementById('filter_quantitative'),
  filterNarrative: document.getElementById('filter_narrative'),
  filterChoice: document.getElementById('filter_choice'),
  filterUnmapped: document.getElementById('filter_unmapped'),
  filterMapped: document.getElementById('filter_mapped'),
  navButtons: document.querySelectorAll('.nav-btn'),

  // Count badges
  countAll: document.getElementById('count_all'),
  countQuantitative: document.getElementById('count_quantitative'),
  countNarrative: document.getElementById('count_narrative'),
  countChoice: document.getElementById('count_choice'),
  countUnmapped: document.getElementById('count_unmapped'),
  countMapped: document.getElementById('count_mapped'),

  // Modal elements
  predictionModal: document.getElementById('prediction_modal'),
  closeModalBtn: document.getElementById('close_modal_btn'),
  modalConceptClassification: document.getElementById('modal_concept_classification'),
  modalConceptName: document.getElementById('modal_concept_name'),
  modalConceptSubgroup: document.getElementById('modal_concept_subgroup'),
  candidatesList: document.getElementById('candidates_list'),
  tabCandidatesBtn: document.getElementById('tab_candidates_btn'),
  tabLlmPredictionsBtn: document.getElementById('tab_llm_predictions_btn'),
  tabLlmContextBtn: document.getElementById('tab_llm_context_btn'),
  contentCandidates: document.getElementById('content_candidates'),
  contentLlmPredictions: document.getElementById('content_llm_predictions'),
  contentLlmContext: document.getElementById('content_llm_context'),
  llmCandidatesList: document.getElementById('llm_candidates_list'),
  copyContextBtn: document.getElementById('copy_context_btn'),
  contextPreviewCode: document.getElementById('context_preview_code'),
  
  // Answer console filters
  customerGroupSelect: document.getElementById('customer_group_select'),
  operationalSiteSelect: document.getElementById('operational_site_select'),
  periodSelect: document.getElementById('period_select'),

  // Answer modal elements
  answerModal: document.getElementById('answer_modal'),
  closeAnswerModalBtn: document.getElementById('close_answer_modal_btn'),
  answerConfidenceBadge: document.getElementById('answer_confidence_badge'),
  answerConceptName: document.getElementById('answer_concept_name'),
  answerConceptSubgroup: document.getElementById('answer_concept_subgroup'),
  answerValueDisplay: document.getElementById('answer_value_display'),
  answerUnitDisplay: document.getElementById('answer_unit_display'),
  answerMetaDisplay: document.getElementById('answer_meta_display'),
  answerSourcePosition: document.getElementById('answer_source_position'),
  answerSourceType: document.getElementById('answer_source_type'),
  answerMatchingScore: document.getElementById('answer_matching_score'),
  answerOccurrenceDate: document.getElementById('answer_occurrence_date'),
  answerResolvedPath: document.getElementById('answer_resolved_path'),

  // Toast notifications container
  toastCenter: document.getElementById('toast_center')
};

// 3. Application Initialization
window.addEventListener('DOMContentLoaded', async () => {
  initEventListeners();
  await loadTaxonomies();
  await loadFilterConsoleData();
});

// 4. Register Action Listeners
function initEventListeners() {
  // Taxonomy selection change
  DOM.taxonomySelector.addEventListener('change', async (e) => {
    const taxId = parseInt(e.target.value);
    const tax = state.taxonomies.find(t => t.taxonomy_id === taxId);
    if (tax) {
      state.selectedTaxonomy = tax;
      await loadConcepts(taxId);
    }
  });

  // Search input matching
  DOM.conceptSearch.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.toLowerCase().trim();
    applyFiltersAndRender();
  });

  // Sidebar filters integration
  DOM.navButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      // Update visual active classes
      DOM.navButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      state.activeFilter = btn.getAttribute('data-filter');
      applyFiltersAndRender();
    });
  });

  // Customer Group change triggers sub-sites load
  DOM.customerGroupSelect.addEventListener('change', async (e) => {
    const customerSiteId = e.target.value;
    if (customerSiteId) {
      await loadOperationalSites(parseInt(customerSiteId));
    } else {
      DOM.operationalSiteSelect.innerHTML = '<option value="" selected>Select Group first...</option>';
      DOM.operationalSiteSelect.disabled = true;
    }
  });

  // Modal actions (Smart Mapping)
  DOM.closeModalBtn.addEventListener('click', closeModal);
  DOM.predictionModal.addEventListener('click', (e) => {
    if (e.target === DOM.predictionModal) {
      closeModal();
    }
  });

  // Prediction modal tab switching
  DOM.tabCandidatesBtn.addEventListener('click', () => {
    DOM.tabCandidatesBtn.classList.add('active');
    DOM.tabLlmPredictionsBtn.classList.remove('active');
    DOM.tabLlmContextBtn.classList.remove('active');
    DOM.contentCandidates.style.display = 'block';
    DOM.contentLlmPredictions.style.display = 'none';
    DOM.contentLlmContext.style.display = 'none';
  });

  DOM.tabLlmPredictionsBtn.addEventListener('click', () => {
    DOM.tabCandidatesBtn.classList.remove('active');
    DOM.tabLlmPredictionsBtn.classList.add('active');
    DOM.tabLlmContextBtn.classList.remove('active');
    DOM.contentCandidates.style.display = 'none';
    DOM.contentLlmPredictions.style.display = 'block';
    DOM.contentLlmContext.style.display = 'none';
    
    // Trigger lazy-load fetch for LLM model scoring
    triggerLlmReranking();
  });

  DOM.tabLlmContextBtn.addEventListener('click', () => {
    DOM.tabCandidatesBtn.classList.remove('active');
    DOM.tabLlmPredictionsBtn.classList.remove('active');
    DOM.tabLlmContextBtn.classList.add('active');
    DOM.contentCandidates.style.display = 'none';
    DOM.contentLlmPredictions.style.display = 'none';
    DOM.contentLlmContext.style.display = 'block';
  });

  // Prompt clipboard copy action
  DOM.copyContextBtn.addEventListener('click', () => {
    const text = DOM.contextPreviewCode.textContent;
    navigator.clipboard.writeText(text).then(() => {
      const originalText = DOM.copyContextBtn.textContent;
      DOM.copyContextBtn.textContent = 'Copied!';
      DOM.copyContextBtn.style.background = 'var(--success-green)';
      showToast('LLM Context copied to clipboard.', 'success');
      setTimeout(() => {
        DOM.copyContextBtn.textContent = originalText;
        DOM.copyContextBtn.style.background = 'var(--accent-purple)';
      }, 2000);
    }).catch(err => {
      console.error('Failed to copy text: ', err);
      showToast('Failed to copy to clipboard.', 'error');
    });
  });

  // Modal actions (Answer Discovery)
  DOM.closeAnswerModalBtn.addEventListener('click', closeAnswerModal);
  DOM.answerModal.addEventListener('click', (e) => {
    if (e.target === DOM.answerModal) {
      closeAnswerModal();
    }
  });
}

// 5. Load Registered Taxonomies
async function loadTaxonomies() {
  try {
    const response = await fetch('/api/taxonomies');
    const data = await response.json();
    
    if (data.success && data.taxonomies.length > 0) {
      state.taxonomies = data.taxonomies;
      
      // Populate select dropdown options
      DOM.taxonomySelector.innerHTML = '<option value="" disabled selected>Select an XBRL Taxonomy...</option>';
      data.taxonomies.forEach(t => {
        const option = document.createElement('option');
        option.value = t.taxonomy_id;
        option.textContent = `${t.name} (UUID: ${t.uuid.substring(0, 8)}...)`;
        DOM.taxonomySelector.appendChild(option);
      });
    } else {
      DOM.taxonomySelector.innerHTML = '<option value="" disabled>No taxonomies found in DB.</option>';
      showToast('No taxonomies found. Make sure taxonomy tables are loaded.', 'error');
    }
  } catch (err) {
    console.error('Error fetching taxonomies:', err);
    showToast('Failed to connect to backend server.', 'error');
  }
}

// 6. Fetch classified concepts for visual listing
async function loadConcepts(taxonomyId) {
  try {
    // Show spinner in table body
    DOM.conceptsTableBody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-state">
          <div class="loading-spinner"></div>
          <h3>Classifying Taxonomy Concepts...</h3>
          <p>Running heuristics & structural matches against SoFi databases...</p>
        </td>
      </tr>
    `;

    const response = await fetch(`/api/concepts/${taxonomyId}`);
    const data = await response.json();

    if (data.success) {
      state.concepts = data.concepts;
      
      // Update Taxonomy header descriptions
      DOM.taxonomyTitle.textContent = state.selectedTaxonomy.name;
      DOM.taxonomySubtitle.textContent = `Taxonomy UUID: ${state.selectedTaxonomy.uuid} | Exposing ${data.concepts.length} semantic elements.`;
      
      // Recalculate sidebar badge numbers
      updateSidebarBadges();
      
      // Apply active filter and render
      applyFiltersAndRender();
    } else {
      showToast('Error: ' + data.error, 'error');
    }
  } catch (err) {
    console.error('Error loading concepts:', err);
    showToast('Failed to fetch concept classifications.', 'error');
  }
}

// 7. Update Filter Statistics Badges
function updateSidebarBadges() {
  const counts = {
    all: state.concepts.length,
    quantitative: state.concepts.filter(c => c.classification === 'Quantitative').length,
    narrative: state.concepts.filter(c => c.classification === 'Narrative').length,
    choice: state.concepts.filter(c => c.classification === 'Choice').length,
    unmapped: state.concepts.filter(c => c.mappedStatus === 'Unmapped' && !c.isAbstract).length,
    mapped: state.concepts.filter(c => c.mappedStatus === 'Mapped' && !c.isAbstract).length
  };

  DOM.countAll.textContent = counts.all;
  DOM.countQuantitative.textContent = counts.quantitative;
  DOM.countNarrative.textContent = counts.narrative;
  DOM.countChoice.textContent = counts.choice;
  DOM.countUnmapped.textContent = counts.unmapped;
  DOM.countMapped.textContent = counts.mapped;
}

// 8. Filters & Search logic
function applyFiltersAndRender() {
  // A. Filter by Category type
  let result = state.concepts;

  if (state.activeFilter === 'Quantitative') {
    result = result.filter(c => c.classification === 'Quantitative');
  } else if (state.activeFilter === 'Narrative') {
    result = result.filter(c => c.classification === 'Narrative');
  } else if (state.activeFilter === 'Choice') {
    result = result.filter(c => c.classification === 'Choice');
  } else if (state.activeFilter === 'Unmapped') {
    result = result.filter(c => c.mappedStatus === 'Unmapped' && !c.isAbstract);
  } else if (state.activeFilter === 'Mapped') {
    result = result.filter(c => c.mappedStatus === 'Mapped' && !c.isAbstract);
  }

  // B. Apply Text Search query matching
  if (state.searchQuery) {
    result = result.filter(c => 
      c.identifier.toLowerCase().includes(state.searchQuery) ||
      (c.name && c.name.toLowerCase().includes(state.searchQuery)) ||
      (c.subGroup && c.subGroup.toLowerCase().includes(state.searchQuery))
    );
  }

  state.filteredConcepts = result;
  renderConceptsTable();
}

// 9. Render Concepts Table Row Elements
function renderConceptsTable() {
  if (state.filteredConcepts.length === 0) {
    DOM.conceptsTableBody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-state">
          <div class="empty-state-icon">&#128269;</div>
          <h3>No matching concepts found</h3>
          <p>Try clearing your text filters or selecting a different sidebar status.</p>
        </td>
      </tr>
    `;
    return;
  }

  DOM.conceptsTableBody.innerHTML = '';
  
  state.filteredConcepts.forEach(c => {
    const tr = document.createElement('tr');
    
    // Class names matching classification styling
    let classStyle = 'class-abstract';
    if (c.classification === 'Quantitative') classStyle = 'class-quantitative';
    else if (c.classification === 'Narrative') classStyle = 'class-narrative';
    else if (c.classification === 'Choice') classStyle = 'class-choice';
    else if (c.classification === 'Metadata') classStyle = 'class-abstract';

    // Status badges
    let statusBadge = '';
    if (!c.isAbstract) {
      const statusClass = c.mappedStatus === 'Mapped' ? 'status-mapped' : 'status-unmapped';
      statusBadge = `<span class="badge-status ${statusClass}">${c.mappedStatus}</span>`;
    }

    // Action button based on state
    let actionBtn = '';
    if (c.isAbstract) {
      actionBtn = `<span style="color: var(--text-muted); font-size: 0.8rem; font-style: italic;">Structural</span>`;
    } else {
      const mapBtnText = c.mappedStatus === 'Mapped' ? 'Link (Mapped)' : 'Link';
      const mapBtnClass = c.mappedStatus === 'Mapped' ? 'btn-review' : 'btn-predict';
      
      actionBtn = `
        <div class="action-btn-group">
          <button class="action-btn btn-find-answer" onclick="findBestAnswer(${c.taxonomyConceptId})">
            Find Answer
          </button>
          <button class="action-btn ${mapBtnClass}" onclick="openPredictionModal(${c.taxonomyConceptId})">
            ${mapBtnText}
          </button>
        </div>
      `;
    }

    // Handle mapping info display
    let mappingText = '';
    if (c.mappedStatus === 'Mapped' && c.mappedPositionName) {
      mappingText = `
        <div class="mapped-info-sub">
          <span class="mapped-arrow">&rdsh;</span> Mapped to: <strong>${c.mappedPositionName}</strong> (ID: ${c.mappedPositionId})
        </div>
      `;
    }

    tr.innerHTML = `
      <td>
        <div class="concept-id-cell" title="${c.identifier}">${c.identifier}</div>
        <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 3px;">
          ${c.subGroup || 'General Schema Group'}
        </div>
        ${mappingText}
      </td>
      <td>
        <span class="badge-type" title="Schema data type">${c.type || 'N/A'}</span>
      </td>
      <td>
        <span style="font-size: 0.85rem; color: var(--text-secondary); text-transform: capitalize;">
          ${c.periodType || 'N/A'}
        </span>
      </td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <span class="badge-classification ${classStyle}">${c.classification}</span>
          ${statusBadge}
        </div>
      </td>
      <td style="text-align: center;">
        ${actionBtn}
      </td>
    `;
    
    DOM.conceptsTableBody.appendChild(tr);
  });
}

// 10. Open Smart Mapping Predictions Modal Dialog
async function openPredictionModal(taxonomyConceptId) {
  const concept = state.concepts.find(c => c.taxonomyConceptId === taxonomyConceptId);
  if (!concept) return;

  state.activeConcept = concept;
  
  // Set modal header details
  DOM.modalConceptName.textContent = concept.identifier;
  DOM.modalConceptSubgroup.textContent = `Sub-group: ${concept.subGroup || 'Standard Common Elements'} | Type: ${concept.type || 'N/A'}`;
  
  // Classification badge styles
  DOM.modalConceptClassification.textContent = concept.classification;
  DOM.modalConceptClassification.className = 'modal-label';
  if (concept.classification === 'Quantitative') {
    DOM.modalConceptClassification.classList.add('class-quantitative');
  } else if (concept.classification === 'Narrative') {
    DOM.modalConceptClassification.classList.add('class-narrative');
  } else if (concept.classification === 'Choice') {
    DOM.modalConceptClassification.classList.add('class-choice');
  } else {
    DOM.modalConceptClassification.classList.add('class-abstract');
  }

  // Reset tab active states to Heuristic Candidates as default
  DOM.tabCandidatesBtn.classList.add('active');
  DOM.tabLlmPredictionsBtn.classList.remove('active');
  DOM.tabLlmContextBtn.classList.remove('active');
  DOM.contentCandidates.style.display = 'block';
  DOM.contentLlmPredictions.style.display = 'none';
  DOM.contentLlmContext.style.display = 'none';
  DOM.contextPreviewCode.textContent = 'Loading Context Payload...';
  DOM.llmCandidatesList.innerHTML = '';

  // Clear candidates list and show loading state
  DOM.candidatesList.innerHTML = `
    <div class="empty-state" style="padding: 40px 0;">
      <div class="loading-spinner"></div>
      <p style="margin-top: 15px; color: var(--text-secondary);">Recalculating similarity coefficients, unit weights, temporal periods, and closure structural hierarchy matches...</p>
    </div>
  `;
  
  DOM.predictionModal.classList.add('active');

  // Trigger Context compilation in the background
  fetch(`/api/llm-context/${state.selectedTaxonomy.taxonomy_id}/${taxonomyConceptId}`)
    .then(res => res.json())
    .then(data => {
      if (data.success) {
        DOM.contextPreviewCode.textContent = data.context;
      } else {
        DOM.contextPreviewCode.textContent = `Error compiling context: ${data.error}`;
      }
    })
    .catch(err => {
      console.error('Error fetching context:', err);
      DOM.contextPreviewCode.textContent = 'Error: Failed to contact context compilation endpoint.';
    });

  try {
    const response = await fetch(`/api/predictions/${state.selectedTaxonomy.taxonomy_id}/${taxonomyConceptId}`);
    const data = await response.json();

    if (data.success) {
      renderCandidates(data.candidates);
    } else {
      DOM.candidatesList.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">&#9888;</div>
          <h3>Failed to calculate matches</h3>
          <p>${data.error}</p>
        </div>
      `;
    }
  } catch (err) {
    console.error('Error fetching predictions:', err);
    DOM.candidatesList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">&#9888;</div>
        <h3>Failed to fetch predictions</h3>
        <p>Could not contact server API endpoint.</p>
      </div>
    `;
  }
}

// 11. Render Candidate Lists and Score breakdowns
function renderCandidates(candidates) {
  DOM.candidatesList.innerHTML = '';
  
  const currentMappedId = state.activeConcept.mappedPositionId;

  // If currently mapped, add a prominent display of the active mapping at the top
  if (state.activeConcept.mappedStatus === 'Mapped') {
    const isCandidateInList = candidates.some(c => c.positionId === currentMappedId);
    
    // If mapped position isn't in the top 5 list, fetch or display it as a separate highlighted row
    if (!isCandidateInList) {
      const activeCard = document.createElement('div');
      activeCard.className = 'candidate-card';
      activeCard.style.borderColor = 'var(--success-green)';
      activeCard.style.background = 'hsla(145, 80%, 45%, 0.08)';
      
      activeCard.innerHTML = `
        <div class="candidate-info">
          <div style="font-size: 0.72rem; color: var(--success-green); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">
            &nbsp;&bull;&nbsp; Currently Mapped Position
          </div>
          <div class="candidate-name">${state.activeConcept.mappedPositionName}</div>
          <div class="candidate-meta">
            <span>ID: ${currentMappedId}</span>
            <span class="candidate-type-badge">Active</span>
          </div>
        </div>
        <div class="candidate-score-block">
          <button class="btn-map btn-unmap-action" onclick="unmapPosition(${currentMappedId}, ${state.activeConcept.taxonomyConceptId})">
            Unmap
          </button>
        </div>
      `;
      DOM.candidatesList.appendChild(activeCard);
    }
  }

  if (candidates.length === 0) {
    DOM.candidatesList.innerHTML += `
      <div class="empty-state" style="padding: 30px 0;">
        <p>No valid candidate positions found in the SoFi index database for this concept.</p>
      </div>
    `;
    return;
  }

  candidates.forEach(c => {
    const isCurrentlyMappedHere = currentMappedId === c.positionId;
    const card = document.createElement('div');
    card.className = 'candidate-card';
    
    if (isCurrentlyMappedHere) {
      card.style.borderColor = 'var(--success-green)';
      card.style.background = 'hsla(145, 80%, 45%, 0.08)';
    }

    // Build the tooltip/breakdown analysis text
    const breakdownTooltip = `Lexical: ${c.breakdown.lexical}% | Unit Match: ${c.breakdown.unit}% | Temporal: ${c.breakdown.temporal}% | Hierarchy Boost: ${c.breakdown.structural}%`;
    
    // Action button
    const mapActionHtml = isCurrentlyMappedHere
      ? `<button class="btn-map btn-unmap-action" onclick="unmapPosition(${c.positionId}, ${state.activeConcept.taxonomyConceptId})">Unmap</button>`
      : `<button class="btn-map" onclick="mapPosition(${c.positionId}, ${state.activeConcept.taxonomyConceptId})">Map</button>`;

    // Add subtag for currently mapped
    const currentMappedLabel = isCurrentlyMappedHere 
      ? `<div style="font-size: 0.72rem; color: var(--success-green); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">&bull; Currently Mapped</div>` 
      : '';

    card.innerHTML = `
      <div class="candidate-info">
        ${currentMappedLabel}
        <div class="candidate-name">${c.positionName}</div>
        <div class="candidate-meta">
          <span>ID: ${c.positionId}</span>
          <span class="candidate-type-badge">${c.positionTypeName}</span>
          <span>Unit: <strong>${c.unitClassName}</strong></span>
        </div>
        <div class="breakdown-pills" style="margin-top: 8px; display: flex; gap: 6px; font-size: 0.65rem; color: var(--text-muted);">
          <span style="background: hsla(0,0%,100%,0.05); padding: 2px 6px; border-radius: 4px;" title="Keyword match overlap similarity">Lexical: ${c.breakdown.lexical}%</span>
          <span style="background: hsla(0,0%,100%,0.05); padding: 2px 6px; border-radius: 4px;" title="Matching requirements (numeric vs non-numeric units)">Unit: ${c.breakdown.unit}%</span>
          <span style="background: hsla(0,0%,100%,0.05); padding: 2px 6px; border-radius: 4px;" title="Temporal alignment check">Period: ${c.breakdown.temporal}%</span>
          <span style="background: hsla(0,0%,100%,0.05); padding: 2px 6px; border-radius: 4px; ${c.breakdown.structural > 0 ? 'color: var(--accent-purple); font-weight: bold; background: hsla(270,95%,65%,0.15);' : ''}" title="Ancestor mapping proximity heuristics">Hierarchy: ${c.breakdown.structural}%</span>
        </div>
      </div>
      <div class="candidate-score-block">
        <div class="score-percent" title="${breakdownTooltip}">${c.score}%</div>
        ${mapActionHtml}
      </div>
    `;
    DOM.candidatesList.appendChild(card);
  });
}

// 12. Create position taxonomy concept mapping persistence
async function mapPosition(positionId, taxonomyConceptId) {
  try {
    const response = await fetch('/api/mappings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ positionId, taxonomyConceptId })
    });

    const data = await response.json();
    if (data.success) {
      showToast('Persisted: Concept successfully mapped to selected Position.', 'success');
      closeModal();
      
      // Reload positions schema to show new mappings
      await loadConcepts(state.selectedTaxonomy.taxonomy_id);
    } else {
      showToast('Error persisting mapping: ' + data.error, 'error');
    }
  } catch (err) {
    console.error('Error saving mapping:', err);
    showToast('Failed to send mapping persistent transaction.', 'error');
  }
}

// 13. Remove mapping persistence
async function unmapPosition(positionId, taxonomyConceptId) {
  try {
    const response = await fetch(`/api/mappings/${positionId}/${taxonomyConceptId}`, {
      method: 'DELETE'
    });

    const data = await response.json();
    if (data.success) {
      showToast('Removed: Concept mapping deleted from SoFi database.', 'success');
      closeModal();
      
      // Reload positions schema
      await loadConcepts(state.selectedTaxonomy.taxonomy_id);
    } else {
      showToast('Error removing mapping: ' + data.error, 'error');
    }
  } catch (err) {
    console.error('Error deleting mapping:', err);
    showToast('Failed to delete mapping transaction.', 'error');
  }
}

// 14. Close Modal View
function closeModal() {
  DOM.predictionModal.classList.remove('active');
  state.activeConcept = null;
}

// 15. Premium toast alert center
function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  const icon = type === 'success' ? '&#9989;' : '&#9888;';
  
  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${icon}</span>
    <span>${message}</span>
  `;
  
  DOM.toastCenter.appendChild(toast);
  
  // Slide out after 3.5 seconds
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.35s cubic-bezier(0.4, 0, 0.2, 1) forwards';
    setTimeout(() => {
      toast.remove();
    }, 400);
  }, 3500);
}

// 16. Load Customer Groups and periods on startup
async function loadFilterConsoleData() {
  try {
    // A. Fetch Customer Groups
    const groupRes = await fetch('/api/customer-groups');
    const groupData = await groupRes.json();
    if (groupData.success) {
      DOM.customerGroupSelect.innerHTML = '<option value="" selected>All Customers (Global)</option>';
      groupData.groups.forEach(g => {
        const option = document.createElement('option');
        option.value = g.customerSiteId;
        option.textContent = g.customerName;
        DOM.customerGroupSelect.appendChild(option);
      });
    }

    // B. Fetch Transaction Periods
    const periodRes = await fetch('/api/periods');
    const periodData = await periodRes.json();
    if (periodData.success) {
      DOM.periodSelect.innerHTML = '<option value="" selected>All Periods (Latest)</option>';
      periodData.periods.forEach(p => {
        const option = document.createElement('option');
        option.value = p;
        const pStr = p.toString();
        const formatted = pStr.length === 6 ? `${pStr.substring(0, 4)}-${pStr.substring(4)}` : pStr;
        option.textContent = formatted;
        DOM.periodSelect.appendChild(option);
      });
    }
  } catch (err) {
    console.error('Error loading filter console options:', err);
  }
}

// 17. Load Operational Sites under a selected customer group
async function loadOperationalSites(customerSiteId) {
  try {
    DOM.operationalSiteSelect.innerHTML = '<option value="">Loading sites...</option>';
    DOM.operationalSiteSelect.disabled = true;

    const res = await fetch(`/api/sites/${customerSiteId}`);
    const data = await res.json();
    if (data.success && data.sites.length > 0) {
      DOM.operationalSiteSelect.innerHTML = '<option value="" selected>All Operational Sites</option>';
      data.sites.forEach(s => {
        const option = document.createElement('option');
        option.value = s.siteId;
        option.textContent = s.siteName;
        DOM.operationalSiteSelect.appendChild(option);
      });
      DOM.operationalSiteSelect.disabled = false;
    } else {
      DOM.operationalSiteSelect.innerHTML = '<option value="" selected>No sub-sites found.</option>';
      DOM.operationalSiteSelect.disabled = true;
    }
  } catch (err) {
    console.error('Error loading sub-sites:', err);
    DOM.operationalSiteSelect.innerHTML = '<option value="" selected>Error loading sites</option>';
  }
}

// 18. Find Best Answer dynamically querying transactions
async function findBestAnswer(taxonomyConceptId) {
  const concept = state.concepts.find(c => c.taxonomyConceptId === taxonomyConceptId);
  if (!concept) return;

  state.activeConcept = concept;

  // Populate basic modal content and show loading states
  DOM.answerConceptName.textContent = concept.identifier;
  DOM.answerConceptSubgroup.textContent = `Sub-group: ${concept.subGroup || 'Standard Common Elements'} | Type: ${concept.type || 'N/A'}`;
  
  DOM.answerValueDisplay.textContent = 'Calculating...';
  DOM.answerUnitDisplay.textContent = '';
  DOM.answerMetaDisplay.textContent = 'Searching 545,000+ ESG transactions in the SoFi database...';
  
  DOM.answerSourcePosition.textContent = '--';
  DOM.answerSourceType.textContent = '--';
  DOM.answerMatchingScore.textContent = '--';
  DOM.answerOccurrenceDate.textContent = '--';
  DOM.answerResolvedPath.innerHTML = '';
  
  // Set neutral badge
  DOM.answerConfidenceBadge.textContent = 'Searching...';
  DOM.answerConfidenceBadge.className = 'modal-label';

  DOM.answerModal.classList.add('active');

  try {
    const customerSiteId = DOM.customerGroupSelect.value;
    const siteId = DOM.operationalSiteSelect.value;
    const period = DOM.periodSelect.value;

    let url = `/api/find-answer?taxonomyId=${state.selectedTaxonomy.taxonomy_id}&taxonomyConceptId=${taxonomyConceptId}`;
    if (customerSiteId) url += `&customerSiteId=${customerSiteId}`;
    if (siteId) url += `&siteId=${siteId}`;
    if (period) url += `&period=${period}`;

    const response = await fetch(url);
    const data = await response.json();

    if (data.success && data.result.found) {
      const res = data.result;
      
      // Giant Card Display
      DOM.answerValueDisplay.textContent = res.value;
      DOM.answerUnitDisplay.textContent = res.unitName || 'N/A';
      
      const pStr = res.period.toString();
      const formattedPeriod = pStr.length === 6 ? `${pStr.substring(0, 4)}-${pStr.substring(4)}` : pStr;
      DOM.answerMetaDisplay.textContent = `Recorded at ${res.siteName} for period ${formattedPeriod}`;

      // Metadata Grid
      DOM.answerSourcePosition.textContent = res.positionName;
      DOM.answerSourceType.textContent = res.positionTypeName;
      
      if (res.historicPreference && res.historicPreference.isPreferred) {
        DOM.answerMatchingScore.innerHTML = `${res.score}% Match <span class="badge-status status-mapped" style="margin-left: 6px; font-size: 0.72rem; padding: 2px 8px; border-radius: 6px;">★ Historic Preferred</span>`;
      } else {
        DOM.answerMatchingScore.textContent = `${res.score}% Match`;
      }
      
      DOM.answerOccurrenceDate.textContent = res.occurrenceDate || 'N/A';

      // Path breadcrumbs
      DOM.answerResolvedPath.innerHTML = '';
      if (res.positionPath) {
        const pathParts = res.positionPath.split('/').map(p => p.trim()).filter(Boolean);
        pathParts.forEach((part, idx) => {
          const chip = document.createElement('span');
          chip.className = 'path-chip';
          chip.textContent = part;
          DOM.answerResolvedPath.appendChild(chip);

          if (idx < pathParts.length - 1) {
            const separator = document.createElement('span');
            separator.className = 'path-separator';
            separator.innerHTML = '&rsaquo;';
            DOM.answerResolvedPath.appendChild(separator);
          }
        });
      }

      // Confidence badge
      DOM.answerConfidenceBadge.textContent = res.confidence;
      DOM.answerConfidenceBadge.className = 'modal-label';
      if (res.confidence === 'Mapped Direct Answer') {
        DOM.answerConfidenceBadge.classList.add('label-success');
      } else if (res.confidence === 'High Confidence Prediction') {
        DOM.answerConfidenceBadge.classList.add('label-info');
      } else if (res.confidence === 'Medium Confidence Prediction') {
        DOM.answerConfidenceBadge.classList.add('label-warning');
      } else {
        DOM.answerConfidenceBadge.classList.add('label-danger');
      }

      showToast('Answer retrieved successfully from transactions!', 'success');
    } else {
      // Not found! Let's display recommended fields
      DOM.answerValueDisplay.textContent = 'No Data';
      DOM.answerUnitDisplay.textContent = '';
      DOM.answerMetaDisplay.textContent = 'No transactions recorded under the chosen filters.';
      
      DOM.answerConfidenceBadge.textContent = 'Data Missing';
      DOM.answerConfidenceBadge.className = 'modal-label label-danger';

      DOM.answerResolvedPath.innerHTML = `
        <div style="color: var(--text-muted); font-size: 0.85rem; font-style: italic;">
          No operational records exist for this metric. You can collect it in the following recommended positions.
        </div>
      `;

      if (data.result.candidates && data.result.candidates.length > 0) {
        const firstCand = data.result.candidates[0];
        DOM.answerSourcePosition.textContent = firstCand.positionName;
        DOM.answerSourceType.textContent = firstCand.positionTypeName;
        
        if (firstCand.historicPreference && firstCand.historicPreference.isPreferred) {
          DOM.answerMatchingScore.innerHTML = `${firstCand.score}% Score <span class="badge-status status-mapped" style="margin-left: 6px; font-size: 0.72rem; padding: 2px 8px; border-radius: 6px;">★ Historic Preferred</span>`;
        } else {
          DOM.answerMatchingScore.textContent = `${firstCand.score}% Score`;
        }
        
        DOM.answerOccurrenceDate.textContent = 'N/A';
      }

      showToast('No transaction data found for this concept and filters.', 'error');
    }
  } catch (err) {
    console.error('Error finding answer:', err);
    DOM.answerValueDisplay.textContent = 'Error';
    DOM.answerMetaDisplay.textContent = 'Failed to retrieve values due to an unexpected API failure.';
    showToast('Failed to fetch best answer.', 'error');
  }
}

// 19. Close Answer Modal
function closeAnswerModal() {
  DOM.answerModal.classList.remove('active');
  state.activeConcept = null;
}

// 20. LLM Reranking & Rationale Evaluation (Phase 3)
let llmPredictionsCache = {};

async function triggerLlmReranking() {
  const conceptId = state.activeConcept.taxonomyConceptId;
  const taxonomyId = state.selectedTaxonomy.taxonomy_id;
  const cacheKey = `${taxonomyId}_${conceptId}`;
  
  if (llmPredictionsCache[cacheKey]) {
    renderLlmCandidates(llmPredictionsCache[cacheKey]);
    return;
  }
  
  DOM.llmCandidatesList.innerHTML = `
    <div class="empty-state" style="padding: 40px 0;">
      <div class="loading-spinner"></div>
      <p style="margin-top: 15px; color: var(--text-secondary);">Querying Azure OpenAI model deployment...</p>
      <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 5px;">Evaluating candidates against human rules & compiling reasoning rationale...</p>
    </div>
  `;
  
  try {
    const response = await fetch(`/api/llm-predictions/${taxonomyId}/${conceptId}`);
    const data = await response.json();
    
    if (data.success && data.results && data.results.rankings) {
      llmPredictionsCache[cacheKey] = data.results.rankings;
      renderLlmCandidates(data.results.rankings);
    } else {
      const errorText = data.error || (data.results && data.results.error) || 'Failed to score candidates';
      DOM.llmCandidatesList.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">&#9888;</div>
          <h3>LLM Evaluation Failed</h3>
          <p>${errorText}</p>
        </div>
      `;
    }
  } catch (err) {
    console.error('Error fetching LLM predictions:', err);
    DOM.llmCandidatesList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">&#9888;</div>
        <h3>Failed to fetch LLM reranking</h3>
        <p>Could not connect to backend endpoint.</p>
      </div>
    `;
  }
}

function renderLlmCandidates(rankings) {
  DOM.llmCandidatesList.innerHTML = '';
  
  if (!rankings || rankings.length === 0) {
    DOM.llmCandidatesList.innerHTML = `
      <div class="empty-state" style="padding: 30px 0;">
        <p>No rankings returned from the LLM model.</p>
      </div>
    `;
    return;
  }
  
  rankings.forEach(r => {
    const card = document.createElement('div');
    card.className = 'candidate-card';
    card.style.flexDirection = 'column';
    card.style.alignItems = 'stretch';
    card.style.gap = '10px';
    
    // Highlight if suggested rename is present
    let renameLabel = '';
    if (r.suggestedRename) {
      renameLabel = `
        <div style="background: hsla(35, 90%, 55%, 0.12); border: 1px solid var(--warning-orange); padding: 8px 12px; border-radius: 6px; font-size: 0.8rem; color: var(--warning-orange); margin-top: 5px;">
          <strong>💡 Recommended Naming Adjustment:</strong> Rename candidate to <code>"${r.suggestedRename}"</code>
        </div>
      `;
    }
    
    card.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid hsla(0,0%,100%,0.05); padding-bottom: 8px;">
        <div class="candidate-info">
          <div style="font-size: 0.72rem; color: var(--accent-purple); font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 2px;">
            Rank #${r.rank} Candidate
          </div>
          <div class="candidate-name">${r.positionName}</div>
          <div class="candidate-meta">
            <span>ID: ${r.positionId}</span>
          </div>
        </div>
        <div>
          <button class="btn-map" onclick="mapPosition(${r.positionId}, ${state.activeConcept.taxonomyConceptId})">Map</button>
        </div>
      </div>
      <div style="font-size: 0.82rem; color: var(--text-secondary); line-height: 1.4; padding: 4px 0;">
        <strong>LLM Rationale:</strong> ${r.reasoning}
      </div>
      ${renameLabel}
    `;
    
    DOM.llmCandidatesList.appendChild(card);
  });
}

