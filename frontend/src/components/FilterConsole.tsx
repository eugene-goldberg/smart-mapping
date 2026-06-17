import React from 'react'
import { useStore } from '@/store'
import { api } from '@/api/client'

interface Props {
  onFindAnswer: (conceptId: number) => void
  activeFindConceptId: number | null
}

export function FilterConsole({ onFindAnswer, activeFindConceptId }: Props) {
  const { state, dispatch } = useStore()

  async function onCustomerGroupChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const customerSiteId = parseInt(e.target.value)
    if (customerSiteId) {
      try {
        const sites = await api.sites(customerSiteId)
        dispatch({ type: 'SET_SITES', payload: sites })
      } catch {
        dispatch({ type: 'SET_SITES', payload: [] })
      }
    } else {
      dispatch({ type: 'SET_SITES', payload: [] })
    }
  }

  return (
    <div className="filter-console">
      <span className="filter-label">Filter Console</span>

      <select className="filter-select" onChange={onCustomerGroupChange} defaultValue="">
        <option value="">All Customers (Global)</option>
        {state.customerGroups.map((g) => (
          <option key={g.customerSiteId} value={g.customerSiteId}>
            {g.customerName}
          </option>
        ))}
      </select>

      <select
        className="filter-select"
        disabled={state.sites.length === 0}
        defaultValue=""
      >
        <option value="">
          {state.sites.length === 0 ? 'Select Group first...' : 'All Operational Sites'}
        </option>
        {state.sites.map((s) => (
          <option key={s.siteId} value={s.siteId}>
            {s.siteName}
          </option>
        ))}
      </select>

      <select className="filter-select" defaultValue="">
        <option value="">All Periods (Latest)</option>
        {state.periods.map((p) => {
          const pStr = p.toString()
          const formatted =
            pStr.length === 6 ? `${pStr.substring(0, 4)}-${pStr.substring(4)}` : pStr
          return (
            <option key={p} value={p}>
              {formatted}
            </option>
          )
        })}
      </select>

      <button
        className="find-answer-btn"
        disabled={!activeFindConceptId || !state.selectedTaxonomy}
        onClick={() => activeFindConceptId && onFindAnswer(activeFindConceptId)}
      >
        Find Best Answer
      </button>
    </div>
  )
}
