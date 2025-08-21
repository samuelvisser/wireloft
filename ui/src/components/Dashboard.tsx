// Types for the dashboard demo
export type Episode = {
  id: string
  title: string
  index: number
  cover?: string
}

export type Show = {
  id: string
  author: string
  title: string
  years?: string
  count: number
  episodes: Episode[]
}

// Demo data (mock) — replace with real data when backend is ready
const shows: Show[] = [
  {
    id: 'the-ben-shapiro-show',
    author: 'Ben Shapiro',
    title: 'The Ben Shapiro Show',
    years: '2015-2025',
    count: 30,
    episodes: Array.from({ length: 30 }, (_, i) => ({
      id: `tbs-${i + 1}`,
      title: `Ben Shapiro #${i + 1}`,
      index: i + 1,
    })),
  },
  {
    id: 'the-matt-walsh-show',
    author: 'Matt Walsh',
    title: 'The Matt Walsh Show',
    years: '2018 – 2025',
    count: 20,
    episodes: Array.from({ length: 20 }, (_, i) => ({
      id: `tmws-${i + 1}`,
      title: `Matt Walsh #${i + 1}`,
      index: i + 1,
    })),
  },
  {
    id: 'ben-after-dark',
    author: 'Ben Shapiro',
    title: 'Ben After Dark',
    years: '2025 - 2025',
    count: 7,
    episodes: Array.from({ length: 7 }, (_, i) => ({
      id: `bad-${i + 1}`,
      title: `Ben After Dark #${i + 1}`,
      index: i + 1,
    })),
  },
]

function EpisodeCard({ ep }: { ep: Episode }) {
  const initials = ep.title.split(' ').map((w) => w[0]).join('').slice(0, 3).toUpperCase()
  const style = ep.cover ? { backgroundImage: `url(${ep.cover})` } : undefined
  return (
    <div className="episode-card" role="listitem" aria-label={ep.title} tabIndex={0}>
      <div className="cover" style={style}>
        {!ep.cover && <span className="cover-text" aria-hidden>{initials}</span>}
        <span className="badge">#{ep.index}</span>
      </div>
    </div>
  )
}

export default function Dashboard({ onAddShow }: { onAddShow: () => void }) {
  return (
    <section className="view shows-view" aria-labelledby="dashboard-title">
      <div className="view-header">
        <h1 id="dashboard-title">Shows</h1>
        <button className="btn btn-primary" onClick={onAddShow}>Add show</button>
      </div>
      {shows.map((show) => (
        <article className="show-section" key={show.id} aria-labelledby={`${show.id}-title`}>
          <header className="show-header">
            <div className="show-author">{show.author}</div>
            <h2 id={`${show.id}-title`} className="show-title">{show.title}</h2>
            <div className="show-meta">
              {show.count} episodes{show.years ? ` • ${show.years}` : ''}
            </div>
          </header>
          <div className="episodes-row" role="list" aria-label={`${show.title} episodes`}>
            {show.episodes.map((ep) => (
              <EpisodeCard key={ep.id} ep={ep} />
            ))}
          </div>
        </article>
      ))}
    </section>
  )
}
