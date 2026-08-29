import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'

export type MediaType = 'shows' | 'movies'

type MediaTypeTabsProps = {
    activeType: MediaType
    onChange: (type: MediaType) => void
    ariaLabel: string
    showCount?: number
    movieCount?: number
}

export default function MediaTypeTabs({
    activeType,
    onChange,
    ariaLabel,
    showCount,
    movieCount,
}: MediaTypeTabsProps) {
    return (
        <div className="media-type-tabs browse-type-tabs" role="tablist" aria-label={ariaLabel}>
            <button type="button" role="tab" aria-selected={activeType === 'shows'} onClick={() => onChange('shows')}>
                <FontAwesomeIcon icon={['fas', 'tv']}/> Shows
                {showCount !== undefined && <span>{showCount}</span>}
            </button>
            <button type="button" role="tab" aria-selected={activeType === 'movies'} onClick={() => onChange('movies')}>
                <FontAwesomeIcon icon={['fas', 'clapperboard']}/> Movies
                {movieCount !== undefined && <span>{movieCount}</span>}
            </button>
        </div>
    )
}
