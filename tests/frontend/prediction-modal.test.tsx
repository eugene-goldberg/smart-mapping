import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { PredictionModal } from '../src/components/PredictionModal'
import type { Concept, Candidate, LlmResults } from '../src/types'

const CONCEPT: Concept = {
  taxonomyConceptId: 5, identifier: 'Assets', name: 'Total Assets', type: 'monetary',
  presentationType: null, periodType: 'instant', subGroup: 'Balance Sheet', isAbstract: false,
  mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
  classification: 'Quantitative',
}

const CANDIDATES: Candidate[] = [
  {
    positionId: 101, positionName: 'SoFi Assets Position', positionTypeName: 'Balance Sheet Item',
    unitClassName: 'USD', score: 87,
    breakdown: { lexical: 72, unit: 95, temporal: 80, structural: 15 },
  },
  {
    positionId: 102, positionName: 'Other Assets', positionTypeName: 'Balance Sheet Item',
    unitClassName: 'USD', score: 63,
    breakdown: { lexical: 55, unit: 80, temporal: 60, structural: 0 },
  },
]

const LLM_RESULTS: LlmResults = {
  targetConcept: 'Assets',
  rankings: [
    { positionId: 101, positionName: 'SoFi Assets Position', rank: 1, reasoning: 'Strong keyword match and unit alignment.', suggestedRename: null },
    { positionId: 102, positionName: 'Other Assets', rank: 2, reasoning: 'Partial match on semantic context.', suggestedRename: 'Total Other Assets' },
  ],
}

vi.mock('../src/api/client', () => ({
  api: {
    predictions: vi.fn(async () => CANDIDATES),
    llmPredictions: vi.fn(async () => LLM_RESULTS),
    llmContext: vi.fn(async () => 'Context payload text'),
    createMapping: vi.fn(async () => {}),
    deleteMapping: vi.fn(async () => {}),
  },
}))

const mockOnClose = vi.fn()
const mockOnChanged = vi.fn()
const mockOnToast = vi.fn()

function renderModal(concept: Concept | null = CONCEPT) {
  return render(
    <PredictionModal
      concept={concept}
      taxonomyId={1}
      onClose={mockOnClose}
      onChanged={mockOnChanged}
      onToast={mockOnToast}
    />,
  )
}

describe('PredictionModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    cleanup()
  })

  it('renders nothing when concept is null', () => {
    const { container } = renderModal(null)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows heuristic candidates with scores after loading', async () => {
    renderModal()
    await waitFor(() => expect(screen.getByText('SoFi Assets Position')).toBeInTheDocument())
    expect(screen.getByText('87%')).toBeInTheDocument()
    expect(screen.getByText('63%')).toBeInTheDocument()
  })

  it('renders breakdown pills for each candidate', async () => {
    renderModal()
    await waitFor(() => expect(screen.getByText('SoFi Assets Position')).toBeInTheDocument())
    // First candidate breakdown
    expect(screen.getByText('Lexical: 72%')).toBeInTheDocument()
    expect(screen.getByText('Unit: 95%')).toBeInTheDocument()
    expect(screen.getByText('Period: 80%')).toBeInTheDocument()
    expect(screen.getByText('Hierarchy: 15%')).toBeInTheDocument()
    // Second candidate
    expect(screen.getByText('Lexical: 55%')).toBeInTheDocument()
    expect(screen.getByText('Unit: 80%')).toBeInTheDocument()
  })

  it('switching to LLM tab triggers exactly one llmPredictions call and renders rankings', async () => {
    const { api } = await import('../src/api/client')
    renderModal()
    const llmTab = screen.getByText('LLM Reranking')
    fireEvent.click(llmTab)
    await waitFor(() => expect(screen.getByText('Strong keyword match and unit alignment.')).toBeInTheDocument())
    expect(api.llmPredictions).toHaveBeenCalledTimes(1)
    expect(api.llmPredictions).toHaveBeenCalledWith(1, 5)
    expect(screen.getByText('SoFi Assets Position')).toBeInTheDocument()
  })

  it('LLM tab shows suggestedRename banner when present', async () => {
    renderModal()
    fireEvent.click(screen.getByText('LLM Reranking'))
    await waitFor(() => expect(screen.getByText(/Total Other Assets/)).toBeInTheDocument())
  })

  it('clicking LLM tab twice only fetches once (cache)', async () => {
    const { api } = await import('../src/api/client')
    renderModal()
    const llmTab = screen.getByText('LLM Reranking')
    fireEvent.click(llmTab)
    await waitFor(() => expect(screen.getByText('Strong keyword match and unit alignment.')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Heuristic Candidates'))
    fireEvent.click(screen.getByText('LLM Reranking'))
    await waitFor(() => expect(screen.getByText('Strong keyword match and unit alignment.')).toBeInTheDocument())
    expect(api.llmPredictions).toHaveBeenCalledTimes(1)
  })

  it('clicking Map calls createMapping with correct ids', async () => {
    const { api } = await import('../src/api/client')
    renderModal()
    await waitFor(() => expect(screen.getByText('SoFi Assets Position')).toBeInTheDocument())
    const mapButtons = screen.getAllByText('Map')
    fireEvent.click(mapButtons[0])
    await waitFor(() => expect(api.createMapping).toHaveBeenCalledWith(101, 5))
    expect(mockOnToast).toHaveBeenCalledWith(
      'Persisted: Concept successfully mapped to selected Position.',
      'success',
    )
  })

  it('shows context text in context preview tab', async () => {
    renderModal()
    fireEvent.click(screen.getByText('LLM Context Preview'))
    await waitFor(() => expect(screen.getByText('Context payload text')).toBeInTheDocument())
  })
})
