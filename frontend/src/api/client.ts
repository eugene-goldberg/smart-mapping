import type {
  Taxonomy,
  Concept,
  Candidate,
  CustomerGroup,
  SubSite,
  AnswerResult,
  LlmResults,
} from '@/types'

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  const body = await r.json()
  if (!body.success) throw new Error(body.error || 'Request failed')
  return body as T
}

export const api = {
  taxonomies: async (): Promise<Taxonomy[]> => {
    const data = await getJson<{ success: true; taxonomies: Taxonomy[] }>('/api/taxonomies')
    return data.taxonomies
  },

  concepts: async (taxonomyId: number): Promise<Concept[]> => {
    const data = await getJson<{ success: true; concepts: Concept[] }>(`/api/concepts/${taxonomyId}`)
    return data.concepts
  },

  predictions: async (taxonomyId: number, conceptId: number): Promise<Candidate[]> => {
    const data = await getJson<{ success: true; candidates: Candidate[] }>(
      `/api/predictions/${taxonomyId}/${conceptId}`,
    )
    return data.candidates
  },

  llmPredictions: async (taxonomyId: number, conceptId: number): Promise<LlmResults> => {
    const data = await getJson<{ success: true; results: LlmResults }>(
      `/api/llm-predictions/${taxonomyId}/${conceptId}`,
    )
    return data.results
  },

  llmContext: async (taxonomyId: number, conceptId: number): Promise<string> => {
    const data = await getJson<{ success: true; context: string }>(
      `/api/llm-context/${taxonomyId}/${conceptId}`,
    )
    return data.context
  },

  customerGroups: async (): Promise<CustomerGroup[]> => {
    const data = await getJson<{ success: true; groups: CustomerGroup[] }>('/api/customer-groups')
    return data.groups
  },

  periods: async (): Promise<number[]> => {
    const data = await getJson<{ success: true; periods: number[] }>('/api/periods')
    return data.periods
  },

  sites: async (customerSiteId: number): Promise<SubSite[]> => {
    const data = await getJson<{ success: true; sites: SubSite[] }>(`/api/sites/${customerSiteId}`)
    return data.sites
  },

  findAnswer: async (params: {
    taxonomyId: number
    taxonomyConceptId: number
    customerSiteId?: number | string
    siteId?: number | string
    period?: number | string
  }): Promise<AnswerResult> => {
    const { taxonomyId, taxonomyConceptId, customerSiteId, siteId, period } = params
    let url = `/api/find-answer?taxonomyId=${taxonomyId}&taxonomyConceptId=${taxonomyConceptId}`
    if (customerSiteId) url += `&customerSiteId=${customerSiteId}`
    if (siteId) url += `&siteId=${siteId}`
    if (period) url += `&period=${period}`
    const data = await getJson<{ success: true; result: AnswerResult }>(url)
    return data.result
  },

  createMapping: async (positionId: number, taxonomyConceptId: number): Promise<void> => {
    const r = await fetch('/api/mappings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positionId, taxonomyConceptId }),
    })
    const body = await r.json()
    if (!body.success) throw new Error(body.error || 'Mapping failed')
  },

  deleteMapping: async (positionId: number, taxonomyConceptId: number): Promise<void> => {
    const r = await fetch(`/api/mappings/${positionId}/${taxonomyConceptId}`, {
      method: 'DELETE',
    })
    const body = await r.json()
    if (!body.success) throw new Error(body.error || 'Unmap failed')
  },
}
