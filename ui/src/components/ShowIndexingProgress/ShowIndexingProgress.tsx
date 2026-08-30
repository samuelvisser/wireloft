import {useEffect, useRef} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'

import {useShowIndexingRun} from '../../lib/queries'
import ProgressBar from '../common/ProgressBar'
import './ShowIndexingProgress.css'

type Props = {
    showId: number
    showSlug: string
    className?: string
    pollForStart?: boolean
}

export default function ShowIndexingProgress({showId, showSlug, className, pollForStart = false}: Props) {
    const queryClient = useQueryClient()
    const {data: indexingRun} = useShowIndexingRun(showId, {pollForStart})
    const previouslyIndexing = useRef(false)

    useEffect(() => {
        const isIndexing = indexingRun != null
        if (previouslyIndexing.current && !isIndexing) {
            void Promise.all([
                queryClient.invalidateQueries({queryKey: ['shows']}),
                queryClient.invalidateQueries({queryKey: ['showsView']}),
                queryClient.invalidateQueries({queryKey: ['show', showSlug]}),
                queryClient.invalidateQueries({queryKey: ['episodes', showSlug], exact: false}),
            ])
        }
        previouslyIndexing.current = isIndexing
    }, [indexingRun, queryClient, showSlug])

    if (!indexingRun) return null

    const progress = typeof indexingRun.progress === 'number' ? indexingRun.progress : null
    const classes = ['show-indexing-progress', className].filter(Boolean).join(' ')

    return (
        <div className={classes} aria-live="polite">
            <div className="show-indexing-label">
                <span>{progress == null ? 'Indexing…' : `Indexing… ${progress}%`}</span>
                {progress == null && <FontAwesomeIcon icon={['fas', 'spinner']} spin aria-hidden="true"/>}
            </div>
            {progress != null && <ProgressBar value={progress} ariaLabel="Indexing progress"/>}
        </div>
    )
}
