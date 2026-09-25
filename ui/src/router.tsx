import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  ScrollRestoration,
  useNavigate,
} from 'react-router-dom'
import App from './App'
import HomePage from './pages/HomePage'
import LocalMediaProfilesPage from './pages/LocalMediaProfilesPage'
import SettingsPage from './pages/SettingsPage'
import AddShowPage from './pages/show/AddShowPage'
import AddLocalMediaProfilePage from './pages/local-media-profile/AddLocalMediaProfilePage'
import EditLocalMediaProfilePage from './pages/local-media-profile/EditLocalMediaProfilePage'
import LocalMediaProfilePage from './pages/local-media-profile/LocalMediaProfilePage'
import ShowPage from './pages/show/ShowPage'
import EditShow from './pages/show/EditShowPage'
import EpisodePage from './pages/episode/EpisodePage'
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
import EditMoviePage from './pages/movie/EditMoviePage'

function RootRoute() {
  return (
    <>
      <App />
      <ScrollRestoration />
    </>
  )
}

function AddShowRoute() {
  const navigate = useNavigate()
  return <AddShowPage onCancel={() => navigate('/library')} />
}

export const router = createBrowserRouter(
  createRoutesFromElements(
    <Route path="/" element={<RootRoute />}>
      <Route index element={<HomePage />} />
      <Route path="library" element={<LibraryPage />} />
      <Route path="shows" element={<Navigate to="/library?type=shows" replace />} />
      <Route path="browse" element={<BrowsePage />} />
      <Route path="downloads" element={<DownloadsPage />} />
      <Route path="local-media-profiles" element={<LocalMediaProfilesPage />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="add-show" element={<AddShowRoute />} />
      <Route path="add-local-media-profile" element={<AddLocalMediaProfilePage />} />
      <Route path="local-media-profile/:slug" element={<LocalMediaProfilePage />} />
      <Route path="edit-local-media-profile/:slug" element={<EditLocalMediaProfilePage />} />
      <Route path="download-profiles" element={<DownloadProfilesPage />} />
      <Route path="add-download-profile" element={<AddDownloadProfilePage />} />
      <Route path="edit-download-profile/:type/:id" element={<EditDownloadProfilePage />} />
      <Route path="stream-profiles" element={<StreamProfilesPage />} />
      <Route path="add-stream-profile" element={<AddStreamProfilePage />} />
      <Route path="edit-stream-profile/:type/:id" element={<EditStreamProfilePage />} />
      <Route path="show/:id" element={<ShowPage />} />
      <Route path="movie/:slug" element={<MoviePage />} />
      <Route path="edit-movie/:slug" element={<EditMoviePage />} />
      <Route path="show/:id/episode/:episodeId" element={<EpisodePage />} />
      <Route path="edit-show/:id" element={<EditShow />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Route>,
  ),
)
