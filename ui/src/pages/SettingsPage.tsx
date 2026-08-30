import DailywireAuthCard from '../components/DailywireAuth/DailywireAuthCard'

export default function SettingsPage() {
  return (
    <section className="view" aria-labelledby="settings-title">
      <h1 id="settings-title">Settings</h1>
      <p>Adjust application settings.</p>
      <div style={{marginTop: 16}}>
        <DailywireAuthCard />
      </div>

      <section style={{marginTop: 24}} aria-labelledby="movie-metadata-title">
        <h2 id="movie-metadata-title">Movie metadata</h2>
        <p>
          WireLoft can query TMDB once when a movie is first added, then permanently stores the
          canonical release date in its local database. Configure an API Read Access Token with
          <code> WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN</code> or the
          <code> movieMetadata.tmdbReadAccessToken</code> config value.
        </p>
        <p className="help">
          This product uses the TMDB API but is not endorsed or certified by{' '}
          <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer">TMDB</a>.
        </p>
      </section>
    </section>
  )
}
