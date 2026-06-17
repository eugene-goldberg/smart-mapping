import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { StoreProvider } from '../../frontend/src/store'
import { App } from '../../frontend/src/App'
import type { Taxonomy, CustomerGroup } from '../../frontend/src/types'

const TAXONOMIES: Taxonomy[] = [
  { taxonomy_id: 1, name: 'GAAP 2024', uuid: 'abcd1234-0000-0000-0000-000000000000', created: '2024-01-01' },
]

const CUSTOMER_GROUPS: CustomerGroup[] = [
  { customerSiteId: 10, customerName: 'Acme Corp' },
]

vi.mock('../../frontend/src/api/client', () => ({
  api: {
    taxonomies: vi.fn(async () => TAXONOMIES),
    customerGroups: vi.fn(async () => CUSTOMER_GROUPS),
    periods: vi.fn(async () => [202312, 202309]),
    concepts: vi.fn(async () => []),
    predictions: vi.fn(async () => []),
    llmPredictions: vi.fn(async () => ({ targetConcept: '', rankings: [] })),
    llmContext: vi.fn(async () => ''),
    sites: vi.fn(async () => []),
    findAnswer: vi.fn(async () => ({ found: false })),
    createMapping: vi.fn(async () => {}),
    deleteMapping: vi.fn(async () => {}),
  },
}))

function renderApp() {
  return render(
    <StoreProvider>
      <App />
    </StoreProvider>,
  )
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads taxonomies on mount and populates sidebar select', async () => {
    renderApp()
    await waitFor(() => {
      expect(screen.getByText('GAAP 2024 (UUID: abcd1234...)')).toBeInTheDocument()
    })
  })

  it('loads customer groups on mount', async () => {
    const { api } = await import('../../frontend/src/api/client')
    renderApp()
    await waitFor(() => {
      expect(api.customerGroups).toHaveBeenCalled()
    })
  })

  it('loads periods on mount', async () => {
    const { api } = await import('../../frontend/src/api/client')
    renderApp()
    await waitFor(() => {
      expect(api.periods).toHaveBeenCalled()
    })
  })

  it('renders sidebar brand and nav filters', async () => {
    renderApp()
    expect(screen.getByText('SoFi Smart-Mapping')).toBeInTheDocument()
    expect(screen.getByText('All Concepts')).toBeInTheDocument()
    expect(screen.getByText('Quantitative')).toBeInTheDocument()
    expect(screen.getByText('Narrative')).toBeInTheDocument()
  })

  it('renders search input', async () => {
    renderApp()
    expect(screen.getByPlaceholderText(/Search concepts/)).toBeInTheDocument()
  })
})
