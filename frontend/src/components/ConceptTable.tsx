
import { useStore } from '@/store'
import type { Concept } from '@/types'

interface Props {
  onFindAnswer: (conceptId: number) => void
  onOpenPrediction: (conceptId: number) => void
}

function classificationClass(cls: string): string {
  if (cls === 'Quantitative') return 'class-quantitative'
  if (cls === 'Narrative') return 'class-narrative'
  if (cls === 'Choice') return 'class-choice'
  return 'class-abstract'
}

function ConceptRow({
  concept,
  onFindAnswer,
  onOpenPrediction,
}: {
  concept: Concept
  onFindAnswer: (id: number) => void
  onOpenPrediction: (id: number) => void
}) {
  const isAbstract = concept.isAbstract

  return (
    <tr>
      <td>
        <div className="concept-identifier">{concept.identifier}</div>
        {concept.subGroup && <div className="concept-subgroup">{concept.subGroup}</div>}
        {concept.mappedStatus === 'Mapped' && concept.mappedPositionName && (
          <div className="concept-mapped-sub">&#x2714; {concept.mappedPositionName}</div>
        )}
      </td>
      <td>
        {concept.type && (
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{concept.type}</span>
        )}
        {concept.presentationType && (
          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
            {concept.presentationType}
          </div>
        )}
      </td>
      <td>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          {concept.periodType ?? '—'}
        </span>
      </td>
      <td>
        {isAbstract ? (
          <span className="badge-classification class-abstract">Structural</span>
        ) : (
          <>
            <span className={`badge-classification ${classificationClass(concept.classification)}`}>
              {concept.classification}
            </span>
            <div style={{ marginTop: 4 }}>
              <span
                className={`badge-status ${concept.mappedStatus === 'Mapped' ? 'status-mapped' : 'status-unmapped'}`}
              >
                {concept.mappedStatus}
              </span>
            </div>
          </>
        )}
      </td>
      <td>
        {!isAbstract && (
          <div className="action-cell">
            <button
              className="btn-predict"
              onClick={() => onOpenPrediction(concept.taxonomyConceptId)}
            >
              {concept.mappedStatus === 'Mapped' ? 'Link (Mapped)' : 'Link'}
            </button>
            <button
              className="btn-review"
              onClick={() => onFindAnswer(concept.taxonomyConceptId)}
            >
              Find Answer
            </button>
          </div>
        )}
      </td>
    </tr>
  )
}

export function ConceptTable({ onFindAnswer, onOpenPrediction }: Props) {
  const { state } = useStore()
  const { filteredConcepts, selectedTaxonomy } = state

  if (!selectedTaxonomy) {
    return (
      <div className="table-wrapper">
        <table>
          <tbody>
            <tr>
              <td colSpan={5}>
                <div className="empty-state">
                  <div className="empty-state-icon">&#128202;</div>
                  <h3>Select a Taxonomy to Begin</h3>
                  <p>Choose an XBRL taxonomy from the sidebar to view and map concepts.</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    )
  }

  if (filteredConcepts.length === 0) {
    return (
      <div className="table-wrapper">
        <table>
          <tbody>
            <tr>
              <td colSpan={5}>
                <div className="empty-state">
                  <div className="empty-state-icon">&#128269;</div>
                  <h3>No concepts match your current filters</h3>
                  <p>Try adjusting the filter or search query.</p>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="table-wrapper">
      <table>
        <thead>
          <tr>
            <th>Concept Identifier</th>
            <th>Data Type</th>
            <th>Period Style</th>
            <th>Classification</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredConcepts.map((concept) => (
            <ConceptRow
              key={concept.taxonomyConceptId}
              concept={concept}
              onFindAnswer={onFindAnswer}
              onOpenPrediction={onOpenPrediction}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
