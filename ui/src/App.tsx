import { useCallback } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import HomePage from './pages/HomePage'
import MediaProfilesPage from './pages/MediaProfilesPage'
import SettingsPage from './pages/SettingsPage'
import AddShowPage from './pages/show/AddShowPage'
import AddMediaProfilePage from './pages/media-profile/AddMediaProfilePage'
import EditMediaProfilePage from './pages/media-profile/EditMediaProfilePage'
import ShowPage from './pages/show/ShowPage'
import EditShow from './pages/show/EditShowPage'

export default function App() {
  const navigate = useNavigate()

  const goToAddShow = useCallback(() => navigate('/add-show'), [navigate])
  const cancelAddShow = useCallback(() => navigate('/'), [navigate])

  return (
    <div className="app">
      <Sidebar />
      <main className="content" role="main">
        <Routes>
          <Route path="/" element={<HomePage onAddShow={goToAddShow} />} />
          <Route path="/profiles" element={<MediaProfilesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/add-show" element={<AddShowPage onCancel={cancelAddShow} />} />
          <Route path="/add-media-profile" element={<AddMediaProfilePage />} />
          <Route path="/edit-media-profile/:id" element={<EditMediaProfilePage />} />
          <Route path="/show/:id" element={<ShowPage />} />
          <Route path="/edit-show/:id" element={<EditShow />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
