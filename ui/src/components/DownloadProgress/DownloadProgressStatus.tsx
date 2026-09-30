import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {MediaDownloadViewRead} from '../../types/schemas/media_download'
import ProgressBar from '../common/ProgressBar'
import ProgressExplanation from '../common/ProgressExplanation'
import './DownloadProgress.css'

export default function DownloadProgressStatus({download, compact = false, details = true, labelOverride}: {
    download: MediaDownloadViewRead; compact?: boolean; details?: boolean; labelOverride?: string
}) {
    const state = download.presentation
    const label = labelOverride ?? (compact ? state.compactLabel || state.label : state.label)
    return <span className={`download-progress download-progress-status${compact ? ' is-compact' : ''}`}>
        <span className="download-progress-heading">
            <span className="download-progress-label" role="status" aria-live={state.mode === 'determinate' ? 'off' : 'polite'}><FontAwesomeIcon icon={state.icon} aria-hidden="true"/> {label}</span>
            {details && <ProgressExplanation detail={state.detail + (state.secondary ? ` ${state.secondary}.` : '')}/>}
        </span>
        {state.active && <ProgressBar value={state.percent} mode={state.mode} ariaLabel="Download progress" detail={state.detail}/>}
        {!compact && state.secondary && <small>{state.secondary}</small>}
    </span>
}
