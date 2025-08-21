import { useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import Home from './components/Home'
import MediaProfiles from './components/MediaProfiles'
import Settings from './components/Settings'
import AddShow from './components/AddShow'

export type View = 'home' | 'profiles' | 'settings' | 'add-show'

export default function App() {
  const [view, setView] = useState<View>('home')

  const content = useMemo(() => {
    switch (view) {
      case 'home':
        return <Home onAddShow={() => setView('add-show')} />
      case 'profiles':
        return <MediaProfiles />
      case 'settings':
        return <Settings />
      case 'add-show':
        return <AddShow onCancel={() => setView('home')} />
      default:
        return <Home onAddShow={() => setView('add-show')} />
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
