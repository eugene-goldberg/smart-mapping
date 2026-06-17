import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useEffect } from 'react'
import { Sidebar } from '../src/components/Sidebar'
import { StoreProvider, useStore } from '../src/store'
import type { Taxonomy, Concept } from '../src/types'

vi.mock('../src/api/client', () => ({
  api: {
    concepts: vi.fn(async () => []),
  },
}))

const TAXONOMIES: Taxonomy[] = [
  { taxonomy_id: 1, name: 'GAAP 2024', uuid: 'abcd1234-5678-0000-0000-000000000000', created: '2024-01-01' },
  { taxonomy_id: 2, name: 'IFRS 2024', uuid: 'efgh5678-0000-0000-0000-000000000000', created: '2024-01-01' },
]

const CONCEPTS: Concept[] = [
  {
    taxonomyConceptId: 1, identifier: 'Assets', name: 'Total Assets', type: 'monetary',
    presentationType: null, periodType: 'instant', subGroup: 'Balance Sheet', isAbstract: false,
    mappedStatus: 'Mapped', mappedPositionId: 10, mappedPositionName: 'Total Assets Position',
    classification: 'Quantitative',
  },
  {
    taxonomyConceptId: 2, identifier: 'Revenue', name: 'Revenue', type: 'monetary',
    presentationType: null, periodType: 'duration', subGroup: 'Income Statement', isAbstract: false,
    mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
    classification: 'Quantitative',
  },
  {
    taxonomyConceptId: 3, identifier: 'Notes', name: 'Notes', type: 'text',
    presentationType: null, periodType: 'duration', subGroup: null, isAbstract: false,
    mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
    classification: 'Narrative',
  },
  {
    taxonomyConceptId: 4, identifier: 'AbstractGroup', name: null, type: null,
    presentationType: null, periodType: null, subGroup: null, isAbstract: true,
    mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
    classification: 'Abstract',
  },
]

function Seeder({ concepts, taxonomies }: { concepts: Concept[]; taxonomies: Taxonomy[] }) {
  const { dispatch } = useStore()
  useEffect(() => {
    dispatch({ type: 'SET_TAXONOMIES', payload: taxonomies })
    dispatch({ type: 'SET_CONCEPTS', payload: concepts })
  }, [dispatch])
  return <Sidebar />
}

function renderSidebar(concepts: Concept[] = []) {
  return render(
    <StoreProvider>
      <Seeder concepts={concepts} taxonomies={TAXONOMIES} />
    </StoreProvider>,
  )
}

describe('Sidebar', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders all six filter badges with correct counts', async () => {
    renderSidebar(CONCEPTS)
    await vi.waitFor(() => {
      expect(screen.getByTestId('badge-all').textContent).toBe('4')
    })
    expect(screen.getByTestId('badge-quantitative').textContent).toBe('2')
    expect(screen.getByTestId('badge-narrative').textContent).toBe('1')
    expect(screen.getByTestId('badge-choice').textContent).toBe('0')
    expect(screen.getByTestId('badge-unmapped').textContent).toBe('2')
    expect(screen.getByTestId('badge-mapped').textContent).toBe('1')
  })

  it('shows taxonomy options', async () => {
    renderSidebar()
    await vi.waitFor(() => {
      expect(screen.getByText('GAAP 2024 (UUID: abcd1234...)')).toBeInTheDocument()
    })
    expect(screen.getByText('IFRS 2024 (UUID: efgh5678...)')).toBeInTheDocument()
  })

  it('active filter button has active class', () => {
    renderSidebar(CONCEPTS)
    const allBtn = screen.getByText('All Concepts').closest('button')!
    expect(allBtn.className).toContain('active')
  })

  it('clicking Narrative filter sets it active', () => {
    renderSidebar(CONCEPTS)
    const narrativeBtn = screen.getByText('Narrative').closest('button')!
    fireEvent.click(narrativeBtn)
    expect(narrativeBtn.className).toContain('active')
  })
})
