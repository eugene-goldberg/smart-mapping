import React from 'react'
import { useStore } from '@/store'
import type { FilterType } from '@/types'
import { api } from '@/api/client'

const NAV_FILTERS: { label: string; filter: FilterType; countKey: string }[] = [
  { label: 'All Concepts', filter: 'all', countKey: 'all' },
  { label: 'Quantitative', filter: 'Quantitative', countKey: 'quantitative' },
  { label: 'Narrative', filter: 'Narrative', countKey: 'narrative' },
  { label: 'Choice', filter: 'Choice', countKey: 'choice' },
  { label: 'Unmapped', filter: 'Unmapped', countKey: 'unmapped' },
  { label: 'Mapped', filter: 'Mapped', countKey: 'mapped' },
]

export function Sidebar() {
  const { state, dispatch } = useStore()

  const counts = {
    all: state.concepts.length,
    quantitative: state.concepts.filter((c) => c.classification === 'Quantitative').length,
    narrative: state.concepts.filter((c) => c.classification === 'Narrative').length,
    choice: state.concepts.filter((c) => c.classification === 'Choice').length,
    unmapped: state.concepts.filter((c) => c.mappedStatus === 'Unmapped' && !c.isAbstract).length,
    mapped: state.concepts.filter((c) => c.mappedStatus === 'Mapped' && !c.isAbstract).length,
  }

  async function onTaxonomyChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const taxId = parseInt(e.target.value)
    const tax = state.taxonomies.find((t) => t.taxonomy_id === taxId)
    if (!tax) return
    dispatch({ type: 'SET_SELECTED_TAXONOMY', payload: tax })
    try {
      const concepts = await api.concepts(taxId)
      dispatch({ type: 'SET_CONCEPTS', payload: concepts })
    } catch (err) {
      console.error('Failed to load concepts:', err)
    }
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <h1>SoFi Smart-Mapping</h1>
        <p>XBRL Taxonomy Classification Engine</p>
      </div>

      <div className="taxonomy-selector-wrapper">
        <div className="taxonomy-selector-label">Active Taxonomy</div>
        <select
          className="filter-select"
          style={{ width: '100%' }}
          value={state.selectedTaxonomy?.taxonomy_id ?? ''}
          onChange={onTaxonomyChange}
        >
          <option value="" disabled>
            Select an XBRL Taxonomy...
          </option>
          {state.taxonomies.map((t) => (
            <option key={t.taxonomy_id} value={t.taxonomy_id}>
              {t.name} (UUID: {t.uuid.substring(0, 8)}...)
            </option>
          ))}
        </select>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-section-label">Classification Filters</div>
        {NAV_FILTERS.map(({ label, filter, countKey }) => (
          <button
            key={filter}
            className={`nav-btn${state.activeFilter === filter ? ' active' : ''}`}
            onClick={() => dispatch({ type: 'SET_FILTER', payload: filter })}
          >
            <span>{label}</span>
            <span className="nav-badge" data-testid={`badge-${countKey}`}>
              {counts[countKey as keyof typeof counts]}
            </span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-footer-text">
          SoFi Financial Data Platform
          <br />
          Smart-Mapping v2.0
        </div>
      </div>
    </aside>
  )
}
