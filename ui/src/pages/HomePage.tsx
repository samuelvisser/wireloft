import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@awesome.me/kit-83fa1ac5a9/icons'
import { Link, useNavigate } from 'react-router-dom'
import type React from 'react'

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

// Each episode is a full mock data record, including its parent show metadata
export type EpisodeRecord = Episode & {
  showId: string
  showAuthor: string
  showTitle: string
  showYears?: string
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

function randomEpisodeTitle(showTitle: string, i: number): string {
  const topics = [
    'free speech',
    'AI and the future',
    'parenting',
    'college campuses',
    'elections',
    'the economy',
    'culture wars',
    'movies and media',
    'sports',
    'education',
    'technology',
    'faith and culture',
  ]
  const t = topics[rand(topics.length)]
  const n = i + 1
  const patterns = [
    `${showTitle} — Quick Take on ${t}`,
    `${showTitle}: Full Episode #${n} — ${t} Explained in Depth With Examples and Context` ,
    `${showTitle} Clip: ${t} in 60 Seconds` ,
    `${showTitle} — ${t} | Highlights and Reactions` ,
    `${showTitle} (Ep ${n}): ${t}, Mailbag, and More` ,
    `${showTitle}: ${t} — What You Need To Know Right Now` ,
    `${showTitle} — ${t} and Why It Matters More Than You Think in 2025` ,
  ]
  return patterns[rand(patterns.length)]
}

function makeEpisodeRecords(
  n: number,
  prefix: string,
  showId: string,
  showAuthor: string,
  showTitle: string,
  showYears?: string,
): EpisodeRecord[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `${prefix}-${i + 1}`,
    title: randomEpisodeTitle(showTitle, i),
    index: i + 1,
    status: randomStatus(),
    showId,
    showAuthor,
    showTitle,
    showYears,
  }))
}

// Flat list of episode records (mock) — each entry is an episode with its show metadata
const EPISODES: EpisodeRecord[] = [
  ...makeEpisodeRecords(30, 'the-ben-shapiro-show', 'the-ben-shapiro-show', 'Ben Shapiro', 'The Ben Shapiro Show', '2015-2025'),
  ...makeEpisodeRecords(20, 'the-matt-walsh-show', 'the-matt-walsh-show', 'Matt Walsh', 'The Matt Walsh Show', '2018 – 2025'),
  ...makeEpisodeRecords(7, 'ben-after-dark', 'ben-after-dark', 'Ben Shapiro', 'Ben After Dark', '2025 - 2025'),
]

// Ensure all four statuses are represented in the demo set
const missing = STATUS_LIST.filter((s) => !seenStatuses.has(s))
if (missing.length > 0) {
  let i = 0
  for (const m of missing) {
    // Place missing statuses on the first show's first episodes
    const target = EPISODES[i]
    if (target) target.status = m
    i++
  }
}

// Group the flat episodes into shows for display
const shows: Show[] = Object.values(
  EPISODES.reduce<Record<string, Show>>((acc, ep) => {
    if (!acc[ep.showId]) {
      acc[ep.showId] = {
        id: ep.showId,
        author: ep.showAuthor,
        title: ep.showTitle,
        years: ep.showYears,
        count: 0,
        episodes: [],
      }
    }
    acc[ep.showId].episodes.push({ id: ep.id, title: ep.title, index: ep.index, cover: ep.cover, status: ep.status })
    acc[ep.showId].count += 1
    return acc
  }, {}),
)

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

function EpisodeCard({ ep, showId }: { ep: Episode; showId: string }) {
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

  const navigate = useNavigate()
  const goToEpisode = () => navigate(`/show/${showId}/episode/${ep.id}`)
  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      goToEpisode()
    }
  }

  return (
    <div className="episode-card" role="listitem" aria-label={ep.title} tabIndex={0} onKeyDown={onKeyDown}>
      <div className="cover" style={style} onClick={goToEpisode}>
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
      <div className="episode-title" title={ep.title}>{ep.title}</div>
    </div>
  )
}

export default function HomePage({ onAddShow }: { onAddShow: () => void }) {
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
          <Link to={`/show/${show.id}`} className="show-header" aria-labelledby={`${show.id}-title`}>
            <div className="show-author">{show.author}</div>
            <h2 id={`${show.id}-title`} className="show-title">
              {show.title}
            </h2>
            <div className="show-meta">
              {show.count} episodes{show.years ? ` • ${show.years}` : ''}
            </div>
          </Link>
          <div className="episodes-row" role="list" aria-label={`${show.title} episodes`}>
            {show.episodes.map((ep) => (
              <EpisodeCard key={ep.id} ep={ep} showId={show.id} />
            ))}
          </div>
        </article>
      ))}
    </section>
  )
}
