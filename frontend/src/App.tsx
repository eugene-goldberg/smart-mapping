import { useEffect, useRef, useState, useCallback } from 'react'
import { useStore } from '@/store'
import { api } from '@/api/client'
import { Sidebar } from '@/components/Sidebar'
import { Header } from '@/components/Header'
import { ConceptTable } from '@/components/ConceptTable'
import { FilterConsole } from '@/components/FilterConsole'
import { PredictionModal } from '@/components/PredictionModal'
import { AnswerModal } from '@/components/AnswerModal'
import { ToastCenter, type ToastMessage } from '@/components/Toast'

let toastCounter = 0

export function App() {
  const { state, dispatch } = useStore()
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const [predictionConceptId, setPredictionConceptId] = useState<number | null>(null)
  const [answerConceptId, setAnswerConceptId] = useState<number | null>(null)

  // Filter console selection refs (for the answer query)
  const customerSiteIdRef = useRef<string>('')
  const siteIdRef = useRef<string>('')
  const periodRef = useRef<string>('')

  const showToast = useCallback((message: string, type: 'success' | 'error' = 'success') => {
    const id = ++toastCounter
    setToasts((prev) => [...prev, { id, message, type }])
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // Bootstrap: load taxonomies and filter console data on mount
  useEffect(() => {
    async function bootstrap() {
      try {
        const taxonomies = await api.taxonomies()
        dispatch({ type: 'SET_TAXONOMIES', payload: taxonomies })
      } catch {
        showToast('Failed to connect to backend server.', 'error')
      }

      try {
        const [groups, periods] = await Promise.all([api.customerGroups(), api.periods()])
        dispatch({ type: 'SET_CUSTOMER_GROUPS', payload: groups })
        dispatch({ type: 'SET_PERIODS', payload: periods })
      } catch {
        // non-fatal — filter console degrades gracefully
      }
    }
    bootstrap()
  }, [dispatch, showToast])

  const predictionConcept = predictionConceptId
    ? state.concepts.find((c) => c.taxonomyConceptId === predictionConceptId) ?? null
    : null

  const answerConcept = answerConceptId
    ? state.concepts.find((c) => c.taxonomyConceptId === answerConceptId) ?? null
    : null

  async function refreshConcepts() {
    if (!state.selectedTaxonomy) return
    try {
      const concepts = await api.concepts(state.selectedTaxonomy.taxonomy_id)
      dispatch({ type: 'SET_CONCEPTS', payload: concepts })
    } catch {
      showToast('Failed to refresh concepts.', 'error')
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div className="app-shell">
        <Sidebar />
        <div className="main-content">
          <Header />

          {state.selectedTaxonomy && (
            <div className="taxonomy-banner">
              <h2>{state.selectedTaxonomy.name}</h2>
              <p>
                Taxonomy UUID: {state.selectedTaxonomy.uuid} | Exposing{' '}
                {state.concepts.length} semantic elements.
              </p>
            </div>
          )}

          <FilterConsole
            onFindAnswer={(id) => setAnswerConceptId(id)}
            activeFindConceptId={answerConceptId}
          />

          <ConceptTable
            onFindAnswer={(id) => setAnswerConceptId(id)}
            onOpenPrediction={(id) => setPredictionConceptId(id)}
          />
        </div>
      </div>

      {predictionConcept && (
        <PredictionModal
          concept={predictionConcept}
          taxonomyId={state.selectedTaxonomy?.taxonomy_id ?? null}
          onClose={() => setPredictionConceptId(null)}
          onChanged={refreshConcepts}
          onToast={showToast}
        />
      )}

      {answerConcept && (
        <AnswerModal
          concept={answerConcept}
          customerSiteId={customerSiteIdRef.current}
          siteId={siteIdRef.current}
          period={periodRef.current}
          onClose={() => setAnswerConceptId(null)}
          onToast={showToast}
        />
      )}

      <ToastCenter toasts={toasts} onRemove={removeToast} />
    </div>
  )
}

export default App
