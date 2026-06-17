export interface Taxonomy {
  taxonomy_id: number
  name: string
  uuid: string
  created: string
}

export interface Concept {
  taxonomyConceptId: number
  identifier: string
  name: string | null
  type: string | null
  presentationType: string | null
  periodType: string | null
  subGroup: string | null
  isAbstract: boolean
  mappedStatus: 'Mapped' | 'Unmapped'
  mappedPositionId: number | null
  mappedPositionName: string | null
  classification: string
}

export interface Breakdown {
  lexical: number
  unit: number
  temporal: number
  structural: number
}

export interface Candidate {
  positionId: number
  positionName: string
  positionTypeName: string
  unitClassName: string
  score: number
  breakdown: Breakdown
}

export interface CustomerGroup {
  customerSiteId: number
  customerName: string
}

export interface SubSite {
  siteId: number
  siteName: string
}

export interface HistoricPreference {
  distinctYears: number
  totalTransactions: number
  isPreferred: boolean
}

export interface AnswerResult {
  found: boolean
  positionId?: number
  positionName?: string
  positionTypeName?: string
  score?: number
  breakdown?: Breakdown
  value?: string | number
  isNumeric?: boolean
  unitName?: string
  period?: number
  occurrenceDate?: string | null
  siteName?: string
  positionPath?: string
  confidence?: string
  historicPreference?: HistoricPreference
  candidates?: Array<Candidate & { historicPreference?: HistoricPreference }>
}

export interface LlmRanking {
  positionId: number
  positionName: string
  rank: number
  reasoning: string
  suggestedRename: string | null
}

export interface LlmResults {
  targetConcept: string
  rankings: LlmRanking[]
  simulated?: boolean
  debugMessage?: string
}

export type FilterType = 'all' | 'Quantitative' | 'Narrative' | 'Choice' | 'Unmapped' | 'Mapped'
