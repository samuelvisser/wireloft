import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import DownloadProgressStatus from './DownloadProgressStatus'
import type {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {presentDownloadProgress} from '../../lib/downloadProgress'
import {frontendOperationDefinitions} from '../../lib/operationDefinitions'
import ProgressButton from '../common/ProgressButton'
import './DownloadProgress.css'
import {faIcon} from '../../icons/faIcon'

export default function DownloadProgressButton({download, starting = false, label = 'Download', downloadedLabel = 'Downloaded', ariaLabel,
    onStart, onRetry, onCancel, disabled = false, controlBusy = false, primary = true, showCompletedStatus = true}: {
    download?: MediaDownloadViewRead; starting?: boolean; label?: string; downloadedLabel?: string; ariaLabel?: string;
    onStart: () => void; onRetry?: () => void; onCancel?: () => void;
    disabled?: boolean; controlBusy?: boolean; primary?: boolean; showCompletedStatus?: boolean
}) {
    const state = starting ? presentDownloadProgress(download, download?.operation, true) : download?.presentation
    const retry = !!download && state?.canRetry && onRetry
    if (download && state?.outcome === 'success') return <span className="wl-progress-with-details">
        {showCompletedStatus && <DownloadProgressStatus download={download} compact details={false} labelOverride={downloadedLabel}/>} 
        <button type="button" className="icon-btn" onClick={onRetry || onStart}
                disabled={disabled || controlBusy} title="Re-download" aria-label={`Re-download ${ariaLabel || ''}`}>
            <FontAwesomeIcon icon={faIcon('fas', 'rotate-right')}/>
        </button>
    </span>
    return <ProgressButton definition={frontendOperationDefinitions['media.download']} resourceId={download?.id ?? null}
        presentation={state} starting={starting} label={state?.outcome === 'success' ? 'Re-download' : label}
        icon={faIcon('fas', state?.outcome === 'success' ? 'rotate-right' : 'download')}
        onClick={retry || onStart} disabled={disabled || controlBusy} primary={primary} ariaLabel={ariaLabel}
        onCancel={state?.canCancel ? onCancel : undefined} cancelDisabled={controlBusy}
        retry={state?.active && retry ? {onClick: retry, disabled: controlBusy, label: 'Restart download'} : undefined}/>
}
