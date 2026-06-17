
import { useStore } from '@/store'

export function Header() {
  const { state, dispatch } = useStore()

  return (
    <header className="main-header">
      <div>
        <input
          type="text"
          className="search-input"
          placeholder="Search concepts by identifier, name, group..."
          value={state.searchQuery}
          onChange={(e) => dispatch({ type: 'SET_SEARCH', payload: e.target.value })}
        />
      </div>
      <div className="header-profile">
        <div className="profile-avatar">SM</div>
        <div>
          <div className="profile-name">Smart-Mapping</div>
          <div className="profile-role">XBRL Administrator</div>
        </div>
      </div>
    </header>
  )
}
