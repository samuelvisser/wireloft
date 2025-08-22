import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

// Types for the home (formerly dashboard) demo
export type EpisodeStatus = 'downloaded' | 'downloading' | 'processing' | 'error'

export type Episode = {
  id: string
  title: string
  index: number
  cover?: string
  status: EpisodeStatus
}

export type Show = {
  id: string
  author: string
  title: string
  years?: string
  count: number
  episodes: Episode[]
}

const STATUS_LIST: EpisodeStatus[] = ['downloaded', 'downloading', 'processing', 'error']
const seenStatuses = new Set<EpisodeStatus>()
const rand = (max: number) => Math.floor(Math.random() * max)
const randomStatus = (): EpisodeStatus => {
  const s = STATUS_LIST[rand(STATUS_LIST.length)]
  seenStatuses.add(s)
  return s
}

function makeEpisodes(n: number, prefix: string, titlePrefix: string): Episode[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `${prefix}-${i + 1}`,
    title: `${titlePrefix} #${i + 1}`,
    index: i + 1,
    status: randomStatus(),
  }))
}

// Demo data (mock) — replace with real data when backend is ready
const shows: Show[] = [
  {
    id: 'the-ben-shapiro-show',
    author: 'Ben Shapiro',
    title: 'The Ben Shapiro Show',
    years: '2015-2025',
    count: 30,
    episodes: makeEpisodes(30, 'tbs', 'Ben Shapiro'),
  },
  {
    id: 'the-matt-walsh-show',
    author: 'Matt Walsh',
    title: 'The Matt Walsh Show',
    years: '2018 – 2025',
    count: 20,
    episodes: makeEpisodes(20, 'tmws', 'Matt Walsh'),
  },
  {
    id: 'ben-after-dark',
    author: 'Ben Shapiro',
    title: 'Ben After Dark',
    years: '2025 - 2025',
    count: 7,
    episodes: makeEpisodes(7, 'bad', 'Ben After Dark'),
  },
]

// Ensure all four statuses are represented in the demo set
const missing = STATUS_LIST.filter((s) => !seenStatuses.has(s))
if (missing.length > 0) {
  let i = 0
  for (const m of missing) {
    // Place missing statuses on the first show's first episodes
    const target = shows[0]?.episodes[i]
    if (target) target.status = m
    i++
  }
}

function statusIcon(status: EpisodeStatus) {
  switch (status) {
    case 'downloaded':
      return ['fas', 'circle-check'] as const
    case 'downloading':
      return ['fas', 'arrow-down'] as const
    case 'processing':
      return ['fas', 'spinner'] as const
    case 'error':
      return ['fas', 'circle-exclamation'] as const
  }
}

function statusLabel(status: EpisodeStatus) {
  switch (status) {
    case 'downloaded':
      return 'Downloaded'
    case 'downloading':
      return 'Downloading'
    case 'processing':
      return 'Waiting for processing'
    case 'error':
      return 'Error'
  }
}

function EpisodeCard({ ep }: { ep: Episode }) {
  const initials = ep.title
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 3)
    .toUpperCase()
  const style = ep.cover ? { backgroundImage: `url(${ep.cover})` } : undefined
  const icon = statusIcon(ep.status)
  const label = statusLabel(ep.status)
  const isProcessing = ep.status === 'processing'

  return (
    <div className="episode-card" role="listitem" aria-label={ep.title} tabIndex={0}>
      <div className="cover" style={style}>
        {/* status icon in bottom-left */}
        <span className={`status status-${ep.status}`} aria-label={label} title={label}>
          <FontAwesomeIcon icon={icon as any} spin={isProcessing} />
        </span>
        {!ep.cover && (
          <span className="cover-text" aria-hidden>
            {initials}
          </span>
        )}
        <span className="badge">#{ep.index}</span>
      </div>
    </div>
  )
}

export default function Home({ onAddShow }: { onAddShow: () => void }) {
  return (
    <section className="view shows-view" aria-labelledby="home-title">
      <div className="view-header">
        <h1 id="home-title">Shows</h1>
        <button className="btn btn-primary" onClick={onAddShow}>
          Add show
        </button>
      </div>
      {shows.map((show) => (
        <article className="show-section" key={show.id} aria-labelledby={`${show.id}-title`}>
          <header className="show-header">
            <div className="show-author">{show.author}</div>
            <h2 id={`${show.id}-title`} className="show-title">
              {show.title}
            </h2>
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
