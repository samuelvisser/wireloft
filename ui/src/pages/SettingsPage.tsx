import DailywireAuthCard from '../components/DailywireAuth/DailywireAuthCard'

const TMDB_LOGO_URL = 'https://www.themoviedb.org/assets/2/v4/logos/v2/blue_square_2-d537fb228cf3ded904ef09b136fe3fec72548ebc1fea3fbbd1ad9e36364db38b.svg'

export default function SettingsPage() {
  return (
    <section className="view" aria-labelledby="settings-title">
      <h1 id="settings-title">Settings</h1>
      <p>Adjust application settings.</p>
      <div style={{marginTop: 16}}>
        <DailywireAuthCard />
      </div>

      <section style={{marginTop: 24}} aria-labelledby="movie-metadata-title">
        <h2 id="movie-metadata-title">Movie metadata &amp; credits</h2>
        <p>
          WireLoft can query TMDB once when a movie is first added, then permanently stores the
          canonical release date in its local database. Configure an API Read Access Token with
          <code> WL_MOVIE_METADATA__TMDB_READ_ACCESS_TOKEN</code> or the
          <code> movieMetadata.tmdbReadAccessToken</code> config value.
        </p>
        <div className="help" style={{display: 'flex', alignItems: 'center', gap: 12}}>
          <a href="https://www.themoviedb.org/" target="_blank" rel="noreferrer" aria-label="Open TMDB">
            <img src={TMDB_LOGO_URL} alt="TMDB" width="52" style={{display: 'block', height: 'auto'}}/>
          </a>
          <p style={{margin: 0}}>
            This product uses the TMDB API but is not endorsed or certified by TMDB.
          </p>
        </div>
      </section>
    </section>
  )
}
