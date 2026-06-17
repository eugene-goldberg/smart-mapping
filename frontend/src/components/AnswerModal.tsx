import React, { useEffect, useState } from 'react'
import type { Concept, AnswerResult } from '@/types'
import { api } from '@/api/client'
import { useStore } from '@/store'

interface Props {
  concept: Concept | null
  customerSiteId: string
  siteId: string
  period: string
  onClose: () => void
  onToast: (msg: string, type?: 'success' | 'error') => void
}

export function AnswerModal({ concept, customerSiteId, siteId, period, onClose, onToast }: Props) {
  const { state } = useStore()
  const [result, setResult] = useState<AnswerResult | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!concept || !state.selectedTaxonomy) return
    setResult(null)
    setLoading(true)
    api
      .findAnswer({
        taxonomyId: state.selectedTaxonomy.taxonomy_id,
        taxonomyConceptId: concept.taxonomyConceptId,
        customerSiteId: customerSiteId || undefined,
        siteId: siteId || undefined,
        period: period || undefined,
      })
      .then((r) => setResult(r))
      .catch((err) => {
        onToast(`Failed to fetch answer: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error')
        onClose()
      })
      .finally(() => setLoading(false))
  }, [concept, state.selectedTaxonomy, customerSiteId, siteId, period])

  if (!concept) return null

  const confidence = result?.confidence
  const confidenceClass =
    confidence === 'Mapped Direct Answer'
      ? 'label-success'
      : confidence === 'High Confidence'
        ? 'label-success'
        : confidence === 'Low Confidence'
          ? 'label-warning'
          : confidence === 'Data Missing'
            ? 'label-danger'
            : ''

  const pathParts = result?.positionPath ? result.positionPath.split(' > ') : []

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        <div className="modal-header">
          <div>
            {confidence && (
              <span className={`modal-label ${confidenceClass}`} style={{ marginBottom: 8, display: 'inline-block' }}>
                {confidence}
              </span>
            )}
            {!confidence && loading && (
              <span className="modal-label">Searching...</span>
            )}
            <div className="modal-title">{concept.identifier}</div>
            {concept.subGroup && <div className="modal-subtitle">{concept.subGroup}</div>}
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          {loading && (
            <div className="empty-state">
              <div className="loading-spinner" />
              <p style={{ color: 'var(--text-secondary)' }}>Searching transactions...</p>
            </div>
          )}

          {!loading && result && (
            <>
              {result.found && (
                <>
                  <div className="answer-box">
                    <div className="answer-label">Value</div>
                    <div className="answer-value">
                      {result.value !== undefined ? String(result.value) : '—'}
                    </div>
                    {result.unitName && <div className="answer-unit">{result.unitName}</div>}
                  </div>

                  <div className="answer-box">
                    <div className="answer-label">Source Position</div>
                    <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                      {result.positionName}
                    </div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>
                      {result.positionTypeName}
                      {result.score !== undefined && ` • ${result.score}% Match Score`}
                    </div>
                  </div>

                  {result.occurrenceDate && (
                    <div className="answer-box">
                      <div className="answer-label">Occurrence Date</div>
                      <div style={{ color: 'var(--text-primary)' }}>{result.occurrenceDate}</div>
                    </div>
                  )}

                  {pathParts.length > 0 && (
                    <div className="answer-box">
                      <div className="answer-label">Position Path</div>
                      <div>
                        {pathParts.map((part, idx) => (
                          <React.Fragment key={idx}>
                            <span className="path-part">{part}</span>
                            {idx < pathParts.length - 1 && (
                              <span className="path-separator">&rsaquo;</span>
                            )}
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}

              {!result.found && (
                <div className="empty-state">
                  <div className="empty-state-icon">&#128202;</div>
                  <h3>No Data Found</h3>
                  <p>No transactions recorded under the chosen filters.</p>
                  {result.candidates && result.candidates.length > 0 && (
                    <div style={{ marginTop: 16, textAlign: 'left' }}>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 8 }}>
                        Recommended positions to collect:
                      </div>
                      {result.candidates.slice(0, 3).map((c) => (
                        <div
                          key={c.positionId}
                          style={{
                            padding: '8px 12px',
                            background: 'hsla(220,20%,15%,0.5)',
                            borderRadius: 6,
                            marginBottom: 6,
                            fontSize: '0.8rem',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          {c.positionName} — {c.score}% Score
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
