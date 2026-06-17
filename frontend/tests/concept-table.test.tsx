import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { ConceptTable } from '../src/components/ConceptTable'
import { StoreProvider, useStore } from '../src/store'
import type { Concept, Taxonomy } from '../src/types'

const TAXONOMY: Taxonomy = {
  taxonomy_id: 1, name: 'GAAP 2024',
  uuid: 'abcd1234-5678-0000-0000-000000000000', created: '2024-01-01',
}

const ABSTRACT_CONCEPT: Concept = {
  taxonomyConceptId: 10, identifier: 'BalanceSheetAbstract', name: null, type: null,
  presentationType: null, periodType: null, subGroup: 'Balance Sheet', isAbstract: true,
  mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
  classification: 'Abstract',
}

const MAPPED_CONCEPT: Concept = {
  taxonomyConceptId: 11, identifier: 'Assets', name: 'Total Assets', type: 'monetary',
  presentationType: null, periodType: 'instant', subGroup: 'Balance Sheet', isAbstract: false,
  mappedStatus: 'Mapped', mappedPositionId: 42, mappedPositionName: 'SoFi Total Assets Position',
  classification: 'Quantitative',
}

const UNMAPPED_CONCEPT: Concept = {
  taxonomyConceptId: 12, identifier: 'Revenue', name: 'Net Revenue', type: 'monetary',
  presentationType: null, periodType: 'duration', subGroup: null, isAbstract: false,
  mappedStatus: 'Unmapped', mappedPositionId: null, mappedPositionName: null,
  classification: 'Narrative',
}

function Seeder({ concepts, withTaxonomy = true }: { concepts: Concept[]; withTaxonomy?: boolean }) {
  const { dispatch } = useStore()
  useEffect(() => {
    if (withTaxonomy) dispatch({ type: 'SET_SELECTED_TAXONOMY', payload: TAXONOMY })
    dispatch({ type: 'SET_CONCEPTS', payload: concepts })
  }, [dispatch])
  return <ConceptTable onFindAnswer={vi.fn()} onOpenPrediction={vi.fn()} />
}

function renderTable(concepts: Concept[], withTaxonomy = true) {
  return render(
    <StoreProvider>
      <Seeder concepts={concepts} withTaxonomy={withTaxonomy} />
    </StoreProvider>,
  )
}

describe('ConceptTable', () => {
  it('shows empty-state when no taxonomy selected', () => {
    render(
      <StoreProvider>
        <ConceptTable onFindAnswer={vi.fn()} onOpenPrediction={vi.fn()} />
      </StoreProvider>,
    )
    expect(screen.getByText('Select a Taxonomy to Begin')).toBeInTheDocument()
  })

  it('abstract row shows Structural badge and no action buttons', async () => {
    renderTable([ABSTRACT_CONCEPT])
    await vi.waitFor(() => expect(screen.getByText('Structural')).toBeInTheDocument())
    expect(screen.queryByText('Link')).not.toBeInTheDocument()
    expect(screen.queryByText('Find Answer')).not.toBeInTheDocument()
  })

  it('mapped row shows mapped position sub-line and Link (Mapped) button', async () => {
    renderTable([MAPPED_CONCEPT])
    await vi.waitFor(() => expect(screen.getByText(/SoFi Total Assets Position/)).toBeInTheDocument())
    expect(screen.getByText('Link (Mapped)')).toBeInTheDocument()
  })

  it('unmapped row shows Link button (not Link (Mapped))', async () => {
    renderTable([UNMAPPED_CONCEPT])
    await vi.waitFor(() => expect(screen.getByText('Link')).toBeInTheDocument())
    expect(screen.queryByText('Link (Mapped)')).not.toBeInTheDocument()
  })

  it('classification badge text is present for quantitative concept', async () => {
    renderTable([MAPPED_CONCEPT])
    await vi.waitFor(() => expect(screen.getByText('Quantitative')).toBeInTheDocument())
  })

  it('classification badge text is present for narrative concept', async () => {
    renderTable([UNMAPPED_CONCEPT])
    await vi.waitFor(() => expect(screen.getByText('Narrative')).toBeInTheDocument())
  })

  it('empty filtered concepts renders empty state', async () => {
    renderTable([])
    await vi.waitFor(() =>
      expect(screen.getByText('No concepts match your current filters')).toBeInTheDocument(),
    )
  })
})
