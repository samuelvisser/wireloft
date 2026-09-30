import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {MediaDownloadViewRead} from '../../types/schemas/media_download'
import './DownloadProgress.css'

export default function DownloadStatusBadge({download}: {download: MediaDownloadViewRead}) {
    const state = download.presentation
    const label = `${download.localMediaProfileName || 'Download'}: ${state.label}. ${state.detail}`
    return <span role="listitem" className={`status download-progress status-${state.status}`} title={label} aria-label={label}>
        <FontAwesomeIcon icon={state.icon} spin={state.mode === 'indeterminate'} aria-hidden="true"/>
    </span>
}
