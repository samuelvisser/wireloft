import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {ProgressPresentation} from '../../types/progress'
import ProgressFill from '../common/ProgressFill'
import './DownloadProgress.css'

/** Content for a real action-menu button; the menu retains keyboard/role ownership. */
export default function DownloadProgressActionItem({presentation}: {presentation: ProgressPresentation}) {
    return <span className="download-progress-action" role="status" aria-label={presentation.detail}>
        <ProgressFill presentation={presentation} className="action-menu-item-progress"/>
        <span className="download-progress-action-label"><FontAwesomeIcon icon={presentation.icon} aria-hidden="true"/> {presentation.compactLabel || presentation.label}</span>
    </span>
}
