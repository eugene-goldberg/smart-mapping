import { useState, useEffect, useCallback } from 'react'
import type { Concept, Candidate, LlmRanking } from '@/types'
import { api } from '@/api/client'

interface Props {
  concept: Concept | null
  taxonomyId: number | null
  onClose: () => void
  onChanged: () => void
  onToast: (msg: string, type?: 'success' | 'error') => void
}

type Tab = 'candidates' | 'llm' | 'context'

export function PredictionModal({ concept, taxonomyId, onClose, onChanged, onToast }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>('candidates')
  const [candidates, setCandidates] = useState<Candidate[] | null>(null)
  const [candidatesLoading, setCandidatesLoading] = useState(false)
  const [llmRankings, setLlmRankings] = useState<LlmRanking[] | null>(null)
  const [llmLoading, setLlmLoading] = useState(false)
  const [contextText, setContextText] = useState<string>('Loading Context Payload...')
  const [llmCache, setLlmCache] = useState<Record<string, LlmRanking[]>>({})

  // Reset state when concept changes
  useEffect(() => {
    if (!concept || !taxonomyId) return
    setActiveTab('candidates')
    setCandidates(null)
    setLlmRankings(null)
    setContextText('Loading Context Payload...')
    setCandidatesLoading(true)

    // Fetch candidates
    api
      .predictions(taxonomyId, concept.taxonomyConceptId)
      .then((c) => setCandidates(c))
      .catch(() => setCandidates([]))
      .finally(() => setCandidatesLoading(false))

    // Fetch context in background
    api
      .llmContext(taxonomyId, concept.taxonomyConceptId)
      .then((ctx) => setContextText(ctx))
      .catch(() => setContextText('Error: Failed to contact context compilation endpoint.'))
  }, [concept, taxonomyId])

  const handleLlmTab = useCallback(async () => {
    if (!concept || !taxonomyId) return
    setActiveTab('llm')
    const cacheKey = `${taxonomyId}_${concept.taxonomyConceptId}`
    if (llmCache[cacheKey]) {
      setLlmRankings(llmCache[cacheKey])
      return
    }
    setLlmLoading(true)
    try {
      const results = await api.llmPredictions(taxonomyId, concept.taxonomyConceptId)
      setLlmCache((prev) => ({ ...prev, [cacheKey]: results.rankings }))
      setLlmRankings(results.rankings)
    } catch {
      setLlmRankings([])
    } finally {
      setLlmLoading(false)
    }
  }, [concept, taxonomyId, llmCache])

  async function handleMap(positionId: number) {
    if (!concept) return
    try {
      await api.createMapping(positionId, concept.taxonomyConceptId)
      onToast('Persisted: Concept successfully mapped to selected Position.', 'success')
      onChanged()
      onClose()
    } catch (err) {
      onToast(`Error persisting mapping: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error')
    }
  }

  async function handleUnmap(positionId: number) {
    if (!concept) return
    try {
      await api.deleteMapping(positionId, concept.taxonomyConceptId)
      onToast('Removed: Concept mapping deleted from SoFi database.', 'success')
      onChanged()
      onClose()
    } catch (err) {
      onToast(`Error removing mapping: ${err instanceof Error ? err.message : 'Unknown error'}`, 'error')
    }
  }

  function handleCopy() {
    navigator.clipboard.writeText(contextText).catch(() => {})
  }

  if (!concept) return null

  const clsClass =
    concept.classification === 'Quantitative'
      ? 'class-quantitative'
      : concept.classification === 'Narrative'
        ? 'class-narrative'
        : concept.classification === 'Choice'
          ? 'class-choice'
          : 'class-abstract'

  const currentMappedId = concept.mappedPositionId

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-box">
        {/* Header */}
        <div className="modal-header">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <span className={`badge-classification ${clsClass}`}>{concept.classification}</span>
            </div>
            <div className="modal-title">{concept.identifier}</div>
            {concept.subGroup && <div className="modal-subtitle">{concept.subGroup}</div>}
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            &times;
          </button>
        </div>

        {/* Tabs */}
        <div className="modal-tabs">
          <button
            className={`tab-btn${activeTab === 'candidates' ? ' active' : ''}`}
            onClick={() => setActiveTab('candidates')}
          >
            Heuristic Candidates
          </button>
          <button
            className={`tab-btn${activeTab === 'llm' ? ' active' : ''}`}
            onClick={handleLlmTab}
          >
            LLM Reranking
          </button>
          <button
            className={`tab-btn${activeTab === 'context' ? ' active' : ''}`}
            onClick={() => setActiveTab('context')}
          >
            LLM Context Preview
          </button>
        </div>

        {/* Body */}
        <div className="modal-body">
          {/* Heuristic Candidates Tab */}
          {activeTab === 'candidates' && (
            <div>
              {candidatesLoading && (
                <div className="empty-state">
                  <div className="loading-spinner" />
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Recalculating similarity coefficients...
                  </p>
                </div>
              )}
              {!candidatesLoading && candidates !== null && (
                <>
                  {/* Currently mapped but not in top candidates */}
                  {concept.mappedStatus === 'Mapped' &&
                    currentMappedId &&
                    !candidates.some((c) => c.positionId === currentMappedId) && (
                      <div
                        className="candidate-card"
                        style={{
                          borderColor: 'var(--success-green)',
                          background: 'hsla(145, 80%, 45%, 0.08)',
                        }}
                      >
                        <div className="candidate-info">
                          <div
                            style={{
                              fontSize: '0.72rem',
                              color: 'var(--success-green)',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              letterSpacing: '0.5px',
                              marginBottom: 2,
                            }}
                          >
                            &bull; Currently Mapped Position
                          </div>
                          <div className="candidate-name">{concept.mappedPositionName}</div>
                          <div className="candidate-meta">
                            <span>ID: {currentMappedId}</span>
                            <span className="candidate-type-badge">Active</span>
                          </div>
                        </div>
                        <div className="candidate-score-block">
                          <button
                            className="btn-map btn-unmap-action"
                            onClick={() => handleUnmap(currentMappedId)}
                          >
                            Unmap
                          </button>
                        </div>
                      </div>
                    )}

                  {candidates.length === 0 && (
                    <div className="empty-state">
                      <p>No valid candidate positions found in the SoFi index database for this concept.</p>
                    </div>
                  )}

                  {candidates.map((c) => {
                    const isMapped = currentMappedId === c.positionId
                    return (
                      <div
                        key={c.positionId}
                        className="candidate-card"
                        style={
                          isMapped
                            ? {
                                borderColor: 'var(--success-green)',
                                background: 'hsla(145, 80%, 45%, 0.08)',
                              }
                            : undefined
                        }
                      >
                        <div className="candidate-info">
                          {isMapped && (
                            <div
                              style={{
                                fontSize: '0.72rem',
                                color: 'var(--success-green)',
                                fontWeight: 700,
                                textTransform: 'uppercase',
                                letterSpacing: '0.5px',
                                marginBottom: 2,
                              }}
                            >
                              &bull; Currently Mapped
                            </div>
                          )}
                          <div className="candidate-name">{c.positionName}</div>
                          <div className="candidate-meta">
                            <span>ID: {c.positionId}</span>
                            <span className="candidate-type-badge">{c.positionTypeName}</span>
                            <span>
                              Unit: <strong>{c.unitClassName}</strong>
                            </span>
                          </div>
                          <div className="breakdown-pills">
                            <span className="breakdown-pill" title="Keyword match overlap similarity">
                              Lexical: {c.breakdown.lexical}%
                            </span>
                            <span className="breakdown-pill" title="Matching requirements (numeric vs non-numeric units)">
                              Unit: {c.breakdown.unit}%
                            </span>
                            <span className="breakdown-pill" title="Temporal alignment check">
                              Period: {c.breakdown.temporal}%
                            </span>
                            <span
                              className={`breakdown-pill${c.breakdown.structural > 0 ? ' structural-boost' : ''}`}
                              title="Ancestor mapping proximity heuristics"
                            >
                              Hierarchy: {c.breakdown.structural}%
                            </span>
                          </div>
                        </div>
                        <div className="candidate-score-block">
                          <div className="score-percent">{c.score}%</div>
                          {isMapped ? (
                            <button
                              className="btn-map btn-unmap-action"
                              onClick={() => handleUnmap(c.positionId)}
                            >
                              Unmap
                            </button>
                          ) : (
                            <button className="btn-map" onClick={() => handleMap(c.positionId)}>
                              Map
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </>
              )}
            </div>
          )}

          {/* LLM Reranking Tab */}
          {activeTab === 'llm' && (
            <div>
              {llmLoading && (
                <div className="empty-state">
                  <div className="loading-spinner" />
                  <p style={{ color: 'var(--text-secondary)' }}>
                    Querying Azure OpenAI model deployment...
                  </p>
                </div>
              )}
              {!llmLoading && llmRankings !== null && (
                <>
                  {llmRankings.length === 0 && (
                    <div className="empty-state">
                      <p>No rankings returned from the LLM model.</p>
                    </div>
                  )}
                  {llmRankings.map((r) => (
                    <div key={r.positionId} className="llm-rank-card">
                      <div className="llm-rank-header">
                        <div className="llm-rank-badge">{r.rank}</div>
                        <div className="llm-rank-name">{r.positionName}</div>
                      </div>
                      <div className="llm-reasoning">{r.reasoning}</div>
                      {r.suggestedRename && (
                        <div className="llm-rename-banner">
                          &#128221; Suggested rename: <strong>{r.suggestedRename}</strong>
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {/* LLM Context Preview Tab */}
          {activeTab === 'context' && (
            <div>
              <button className="copy-btn" onClick={handleCopy}>
                &#128203; Copy to Clipboard
              </button>
              <pre className="context-preview">{contextText}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
