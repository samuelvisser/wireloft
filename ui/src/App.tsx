import { useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import MediaProfiles from './components/MediaProfiles'
import Settings from './components/Settings'

export type View = 'dashboard' | 'profiles' | 'settings'

export default function App() {
  const [view, setView] = useState<View>('dashboard')

  const content = useMemo(() => {
    switch (view) {
      case 'dashboard':
        return <Dashboard />
      case 'profiles':
        return <MediaProfiles />
      case 'settings':
        return <Settings />
      default:
        return <Dashboard />
    }
  }, [view])

  return (
    <div className="app">
      <Sidebar currentView={view} onSelect={setView} />
      <main className="content" role="main">
        {content}
      </main>
    </div>
  )
}
