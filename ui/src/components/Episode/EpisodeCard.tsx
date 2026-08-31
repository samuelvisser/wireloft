import React from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useNavigate} from 'react-router-dom'
import {statusIcon, statusLabel} from '../../utils/showStatus'
import {EpisodeRead} from '../../types/schemas/episode'
import {MediaDownloadViewRead} from '../../types/schemas/media_download'

// Beyond this many downloads for one episode, collapse the rest into a "+N" pill
// instead of letting icons overflow the thumbnail.
const MAX_VISIBLE_DOWNLOAD_ICONS = 4

const LIVE_BADGE_STYLE: React.CSSProperties = {
    position: 'absolute',
    top: 8,
    right: 8,
    zIndex: 2,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: '4px 8px',
    borderRadius: 999,
    background: 'var(--error, #d64545)',
    color: '#fff',
    boxShadow: '0 1px 4px rgb(0 0 0 / 30%)',
    fontSize: '0.68rem',
    fontWeight: 800,
    letterSpacing: '0.04em',
    lineHeight: 1,
    textTransform: 'uppercase',
}

const LIVE_BADGE_DOT_STYLE: React.CSSProperties = {
    width: 6,
    height: 6,
    flex: '0 0 auto',
    borderRadius: '50%',
    background: 'currentColor',
}

export function toImageUrl(path?: string | null): string | undefined {
    if (!path) return undefined
    // If already an absolute URL, return as-is
    if (/^https?:\/\//i.test(path)) return path
    const base = (window as any).appConfig?.API_URL?.replace(/\/+$/, '')
    if (!base) return path
    // If path is already rooted, just prefix API base
    if (path.startsWith('/')) return base + path
    // Default: serve from generic assets path
    return `${base}/assets/${path}`
}

/** Groups a flat list of downloads (e.g. from useMediaDownloadsView) by episode slug. */
export function groupDownloadsByEpisodeSlug(
    downloads?: MediaDownloadViewRead[] | null,
): Map<string, MediaDownloadViewRead[]> {
    const map = new Map<string, MediaDownloadViewRead[]>()
    for (const d of downloads ?? []) {
        if (!d.episodeSlug) continue
        const list = map.get(d.episodeSlug)
        if (list) list.push(d)
        else map.set(d.episodeSlug, [d])
    }
    return map
}

const TYPE_BADGE_LABEL: Record<string, string> = {
    trailer: 'Trailer',
    aux: 'Auxiliary',
}

/** Splits an episode_identifier like "ep.4232" or "ep-extra.101.2" into its type and number. */
function episodeTypeInfo(identifier: string | null | undefined): { type: string | null; number: string | null } {
    if (!identifier) return {type: null, number: null}
    const [type, ...rest] = identifier.split('.')
    return {type: type || null, number: rest.length ? rest.join('.') : null}
}

function DownloadStatusIcons({downloads}: { downloads: MediaDownloadViewRead[] }) {
    if (downloads.length === 0) {
        return (
            <span className="status-group">
                <span className="status status-none" title="No downloads on disk">
                    <FontAwesomeIcon icon={['fas', 'floppy-disk-circle-xmark'] as any}/>
                </span>
            </span>
        )
    }

    const overflow = downloads.length > MAX_VISIBLE_DOWNLOAD_ICONS
    const shown = overflow ? downloads.slice(0, MAX_VISIBLE_DOWNLOAD_ICONS - 1) : downloads
    const remaining = downloads.length - shown.length

    return (
        <span className="status-group" role="list" aria-label="Download status">
            {shown.map((d) => {
                const status = String(d.downloadStatus)
                return (
                    <span
                        key={d.id}
                        role="listitem"
                        className={`status status-${status}`}
                        title={`${d.localMediaProfileName ?? 'Download'}: ${statusLabel(status)}`}
                    >
                        <FontAwesomeIcon icon={statusIcon(status) as any} spin={status === 'local_processing'}/>
                    </span>
                )
            })}
            {remaining > 0 && (
                <span className="status status-more" title={`${remaining} more download(s)`}>+{remaining}</span>
            )}
        </span>
    )
}

type Props = {
    ep: EpisodeRead
    showSlug: string
    downloads?: MediaDownloadViewRead[]
}

/** The episode thumbnail card used on both the Home page and a show's episode list. */
export default function EpisodeCard({ep, showSlug, downloads}: Props) {
    const initials = ep.title
        .split(' ')
        .map((w) => w[0])
        .join('')
        .slice(0, 3)
        .toUpperCase()

    // Prefer episode thumbnailPortraitPath; if missing/empty, use a placeholder with the episode index.
    const portraitPath = (ep.thumbnailPortraitPath && ep.thumbnailPortraitPath.trim() !== '') ? ep.thumbnailPortraitPath : undefined
    const imageUrl = portraitPath ? toImageUrl(portraitPath) : `https://placehold.co/640x360/png?text=Episode+%23${ep.index}`
    const style = imageUrl ? {backgroundImage: `url(${imageUrl})`} : undefined
    const isLive = String(ep.publishStatus).toLowerCase() === 'live'

    const {type, number} = episodeTypeInfo(ep.episodeIdentifier)
    // Bottom-right badge: the episode number for regular/extra episodes (color-coded
    // by type), or the content-type label for trailers/auxiliary content, which have
    // no meaningful episode number.
    const showNumberBadge = (type === 'ep' || type === 'ep-extra') && !!number
    const typeBadgeLabel = type ? TYPE_BADGE_LABEL[type] : undefined
    const cornerBadgeText = showNumberBadge ? `#${number}` : typeBadgeLabel

    const navigate = useNavigate()
    const goToEpisode = () => navigate(`/show/${showSlug}/episode/${ep.slug}`)
    const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            goToEpisode()
        }
    }

    return (
        <div className="episode-card" role="listitem" aria-label={ep.title} tabIndex={0} onKeyDown={onKeyDown}>
            <div className="cover" style={style} onClick={goToEpisode}>
                <DownloadStatusIcons downloads={downloads ?? []}/>
                {isLive && (
                    <span style={LIVE_BADGE_STYLE} aria-label="Episode is live">
                        <span style={LIVE_BADGE_DOT_STYLE} aria-hidden/>
                        Live
                    </span>
                )}
                {/* Show initials only if we are using the placeholder (i.e., no real thumbnail) */}
                {!portraitPath && (
                    <span className="cover-text" aria-hidden>
            {initials}
          </span>
                )}
                {cornerBadgeText && (
                    <span className={`badge badge-${type}`}>{cornerBadgeText}</span>
                )}
            </div>
            <div className="episode-title" title={ep.title}>{ep.title}</div>
        </div>
    )
}
