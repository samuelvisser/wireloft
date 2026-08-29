import { useCallback, useEffect, useState } from 'react'
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Footer from './components/Sidebar/Footer'
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
import AddDownloadProfilePage from './pages/download-profile/AddDownloadProfilePage'
import EditDownloadProfilePage from './pages/download-profile/EditDownloadProfilePage'
import StreamProfilesPage from './pages/StreamProfilesPage'
import AddStreamProfilePage from './pages/stream-profile/AddStreamProfilePage'
import EditStreamProfilePage from './pages/stream-profile/EditStreamProfilePage'
import DownloadsPage from './pages/DownloadsPage'
import LibraryPage from './pages/LibraryPage'
import BrowsePage from './pages/BrowsePage'
import MoviePage from './pages/movie/MoviePage'

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

  const cancelAddShow = useCallback(() => navigate('/library'), [navigate])

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
          <Route path="/" element={<HomePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/shows" element={<Navigate to="/library?type=shows" replace />} />
          <Route path="/browse" element={<BrowsePage />} />
          <Route path="/downloads" element={<DownloadsPage />} />
          <Route path="/local-media-profiles" element={<LocalMediaProfilesPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/add-show" element={<AddShowPage onCancel={cancelAddShow} />} />
          <Route path="/add-local-media-profile" element={<AddLocalMediaProfilePage />} />
          <Route path="/edit-local-media-profile/:slug" element={<EditLocalMediaProfilePage />} />
          <Route path="/download-profiles" element={<DownloadProfilesPage />} />
          <Route path="/add-download-profile" element={<AddDownloadProfilePage />} />
          <Route path="/edit-download-profile/:type/:id" element={<EditDownloadProfilePage />} />
          <Route path="/stream-profiles" element={<StreamProfilesPage />} />
          <Route path="/add-stream-profile" element={<AddStreamProfilePage />} />
          <Route path="/edit-stream-profile/:type/:id" element={<EditStreamProfilePage />} />
          <Route path="/show/:id" element={<ShowPage />} />
          <Route path="/movie/:slug" element={<MoviePage />} />
          <Route path="/show/:id/episode/:episodeId" element={<EpisodePage />} />
          <Route path="/edit-show/:id" element={<EditShow />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer wrapperClass="page-footer" />
    </div>
  )
}
