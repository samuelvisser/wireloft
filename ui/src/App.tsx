import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Footer from './components/Footer'
import HomePage from './pages/HomePage'
import LocalMediaProfilesPage from './pages/LocalMediaProfilesPage'
import SettingsPage from './pages/SettingsPage'
import AddShowPage from './pages/show/AddShowPage'
import AddLocalMediaProfilePage from './pages/local-media-profile/AddLocalMediaProfilePage'
import EditLocalMediaProfilePage from './pages/local-media-profile/EditLocalMediaProfilePage'
import ShowPage from './pages/show/ShowPage'
import EditShow from './pages/show/EditShowPage'
import EpisodePage from './pages/episode/EpisodePage'
import LoginPage from './pages/LoginPage'
import DownloadProfilesPage from './pages/DownloadProfilesPage'
import AddPodcastDownloadProfilePage from './pages/download-profile-podcast/AddPodcastDownloadProfilePage'
import EditPodcastDownloadProfilePage from './pages/download-profile-podcast/EditPodcastDownloadProfilePage'
import AddSeriesDownloadProfilePage from './pages/download-profile-series/AddSeriesDownloadProfilePage'
import EditSeriesDownloadProfilePage from './pages/download-profile-series/EditSeriesDownloadProfilePage'

export default function App() {
  const navigate = useNavigate()

  const [authState, setAuthState] = useState<'checking' | 'ok' | 'no'>('checking')

  useEffect(() => {
    let cancelled = false
    const base = (window as any).appConfig?.API_URL || '/api'
    fetch(`${base}/auth/status`, { credentials: 'include' })
      .then((r) => {
        if (cancelled) return
        setAuthState(r.ok ? 'ok' : 'no')
      })
      .catch(() => {
        if (cancelled) return
        setAuthState('no')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const goToAddShow = useCallback(() => navigate('/add-show'), [navigate])
  const cancelAddShow = useCallback(() => navigate('/'), [navigate])

  if (authState === 'checking') {
    return (
      <div style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <div>Loading…</div>
      </div>
    )
  }

  if (authState === 'no') {
    return <LoginPage />
  }

  return (
    <div className="app">
      <Sidebar />
      <main className="content" role="main">
        <Routes>
          <Route path="/" element={<HomePage onAddShow={goToAddShow} />} />
          <Route path="/local-media-profiles" element={<LocalMediaProfilesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/add-show" element={<AddShowPage onCancel={cancelAddShow} />} />
          <Route path="/add-local-media-profile" element={<AddLocalMediaProfilePage />} />
          <Route path="/edit-local-media-profile/:slug" element={<EditLocalMediaProfilePage />} />
          <Route path="/download-profiles" element={<DownloadProfilesPage />} />
          <Route path="/download-profile/podcast/add" element={<AddPodcastDownloadProfilePage />} />
          <Route path="/download-profile/podcast/:id/edit" element={<EditPodcastDownloadProfilePage />} />
          <Route path="/download-profile/series/add" element={<AddSeriesDownloadProfilePage />} />
          <Route path="/download-profile/series/:id/edit" element={<EditSeriesDownloadProfilePage />} />
          <Route path="/show/:id" element={<ShowPage />} />
          <Route path="/show/:id/episode/:episodeId" element={<EpisodePage />} />
          <Route path="/edit-show/:id" element={<EditShow />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer wrapperClass="page-footer" />
    </div>
  )
}
