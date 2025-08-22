import { useCallback } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Home from './components/Home'
import MediaProfiles from './components/MediaProfiles'
import Settings from './components/Settings'
import AddShow from './components/AddShow'
import AddMediaProfile from './components/AddMediaProfile'

export default function App() {
  const navigate = useNavigate()

  const goToAddShow = useCallback(() => navigate('/add-show'), [navigate])
  const cancelAddShow = useCallback(() => navigate('/'), [navigate])

  return (
    <div className="app">
      <Sidebar />
      <main className="content" role="main">
        <Routes>
          <Route path="/" element={<Home onAddShow={goToAddShow} />} />
          <Route path="/profiles" element={<MediaProfiles />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/add-show" element={<AddShow onCancel={cancelAddShow} />} />
          <Route path="/add-media-profile" element={<AddMediaProfile />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
