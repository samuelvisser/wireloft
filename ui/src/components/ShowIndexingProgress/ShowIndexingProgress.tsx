import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'

import {useActiveOperation} from '../OperationNotifier/OperationNotifier'
import ProgressBar from '../common/ProgressBar'
import './ShowIndexingProgress.css'

type Props = {
    showId: number
    showSlug: string
    className?: string
    pollForStart?: boolean
}

export default function ShowIndexingProgress({showId, className}: Props) {
    const indexingOperation = useActiveOperation('show.index', 'show', showId)

    if (!indexingOperation) return null

    const progress = typeof indexingOperation.progress === 'number'
        ? indexingOperation.progress
        : null
    const detail = indexingOperation.message
        && !['Queued', 'Running', 'OK'].includes(indexingOperation.message)
        ? indexingOperation.message
        : null
    const classes = ['show-indexing-progress', className].filter(Boolean).join(' ')

    return (
        <div className={classes} aria-live="polite">
            <div className="show-indexing-label">
                <span>
                    {progress == null ? 'Indexing…' : `Indexing… ${progress}%`}
                    {detail ? ` · ${detail}` : ''}
                </span>
                {progress == null && <FontAwesomeIcon icon={['fas', 'spinner']} spin aria-hidden="true"/>}
            </div>
            {progress != null && <ProgressBar value={progress} ariaLabel="Indexing progress"/>}
        </div>
    )
}
