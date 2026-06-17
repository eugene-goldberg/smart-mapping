import {
  createContext,
  useContext,
  useReducer,
  type ReactNode,
  type Dispatch,
} from 'react'
import type { Taxonomy, Concept, CustomerGroup, SubSite, FilterType } from '@/types'

export interface AppState {
  taxonomies: Taxonomy[]
  concepts: Concept[]
  filteredConcepts: Concept[]
  selectedTaxonomy: Taxonomy | null
  activeFilter: FilterType
  searchQuery: string
  activeConcept: Concept | null
  customerGroups: CustomerGroup[]
  sites: SubSite[]
  periods: number[]
}

export type Action =
  | { type: 'SET_TAXONOMIES'; payload: Taxonomy[] }
  | { type: 'SET_CONCEPTS'; payload: Concept[] }
  | { type: 'SET_SELECTED_TAXONOMY'; payload: Taxonomy }
  | { type: 'SET_FILTER'; payload: FilterType }
  | { type: 'SET_SEARCH'; payload: string }
  | { type: 'SET_ACTIVE_CONCEPT'; payload: Concept | null }
  | { type: 'SET_CUSTOMER_GROUPS'; payload: CustomerGroup[] }
  | { type: 'SET_SITES'; payload: SubSite[] }
  | { type: 'SET_PERIODS'; payload: number[] }

function applyFilter(state: AppState): Concept[] {
  let result = state.concepts

  if (state.activeFilter === 'Quantitative') {
    result = result.filter((c) => c.classification === 'Quantitative')
  } else if (state.activeFilter === 'Narrative') {
    result = result.filter((c) => c.classification === 'Narrative')
  } else if (state.activeFilter === 'Choice') {
    result = result.filter((c) => c.classification === 'Choice')
  } else if (state.activeFilter === 'Unmapped') {
    result = result.filter((c) => c.mappedStatus === 'Unmapped' && !c.isAbstract)
  } else if (state.activeFilter === 'Mapped') {
    result = result.filter((c) => c.mappedStatus === 'Mapped' && !c.isAbstract)
  }

  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase()
    result = result.filter(
      (c) =>
        c.identifier.toLowerCase().includes(q) ||
        (c.name && c.name.toLowerCase().includes(q)) ||
        (c.subGroup && c.subGroup.toLowerCase().includes(q)),
    )
  }

  return result
}

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'SET_TAXONOMIES':
      return { ...state, taxonomies: action.payload }
    case 'SET_CONCEPTS': {
      const next = { ...state, concepts: action.payload }
      return { ...next, filteredConcepts: applyFilter(next) }
    }
    case 'SET_SELECTED_TAXONOMY':
      return { ...state, selectedTaxonomy: action.payload }
    case 'SET_FILTER': {
      const next = { ...state, activeFilter: action.payload }
      return { ...next, filteredConcepts: applyFilter(next) }
    }
    case 'SET_SEARCH': {
      const next = { ...state, searchQuery: action.payload }
      return { ...next, filteredConcepts: applyFilter(next) }
    }
    case 'SET_ACTIVE_CONCEPT':
      return { ...state, activeConcept: action.payload }
    case 'SET_CUSTOMER_GROUPS':
      return { ...state, customerGroups: action.payload }
    case 'SET_SITES':
      return { ...state, sites: action.payload }
    case 'SET_PERIODS':
      return { ...state, periods: action.payload }
    default:
      return state
  }
}

const initialState: AppState = {
  taxonomies: [],
  concepts: [],
  filteredConcepts: [],
  selectedTaxonomy: null,
  activeFilter: 'all',
  searchQuery: '',
  activeConcept: null,
  customerGroups: [],
  sites: [],
  periods: [],
}

const StoreContext = createContext<{ state: AppState; dispatch: Dispatch<Action> } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used within StoreProvider')
  return ctx
}
