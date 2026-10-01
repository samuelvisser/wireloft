import {useEffect, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'

import ProgressButton from '../common/ProgressButton'
import type {FrontendOperationDefinition} from '../../lib/operationDefinitions'
import {useTaskLedgerPage, type TaskLedgerPageQuery} from '../../lib/taskLedger'
import type {TaskLedgerEntryRead} from '../../types/schemas/task'
import './CronTaskLedgerModal.css'

type Props = {
    open: boolean
    title: string
    definition: FrontendOperationDefinition
    query: Omit<TaskLedgerPageQuery, 'offset' | 'limit' | 'enabled'>
    starting: boolean
    onClose: () => void
    onRunNow: () => void | Promise<void>
}

const PAGE_SIZE = 10

function formatDate(value: string | null | undefined): string {
    if (!value) return '—'
    const normalized = /(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? value : `${value}Z`
    return new Date(normalized).toLocaleString()
}

function formatDuration(value: number | null | undefined): string {
    if (value == null || !Number.isFinite(value)) return '—'
    if (value < 1000) return `${Math.max(0, Math.round(value))} ms`

    const seconds = Math.max(0, Math.round(value / 1000))
    if (seconds < 60) return `${seconds} s`

    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    if (minutes < 60) return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`

    const hours = Math.floor(minutes / 60)
    const remainingMinutes = minutes % 60
    return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

function statusLabel(status: string): string {
    switch (status) {
        case 'SCHEDULED':
            return 'Scheduled'
        case 'QUEUED':
            return 'Queued'
        case 'RUNNING':
            return 'Running'
        case 'SUCCEEDED':
            return 'Succeeded'
        case 'FAILED':
            return 'Failed'
        case 'CANCELED':
            return 'Canceled'
        case 'RETRY_SCHEDULED':
            return 'Retry scheduled'
        default:
            return status.replace(/_/g, ' ').toLowerCase().replace(/^./, (character) => character.toUpperCase())
    }
}

function targetLabel(entry: TaskLedgerEntryRead, query: Props['query']): string | null {
    if (query.resourceId !== undefined || entry.resourceId == null) return null

    const type = entry.resourceType.replace(/_/g, ' ')
    const label = type.replace(/^./, (character) => character.toUpperCase())
    return `${label} ${entry.resourceId}`
}

function statusDetail(entry: TaskLedgerEntryRead): string | null {
    if (entry.status === 'FAILED' && entry.lastError) return entry.lastError
    if (entry.message && entry.message !== statusLabel(entry.status)) return entry.message
    return null
}

export default function CronTaskLedgerModal({
    open,
    title,
    definition,
    query,
    starting,
    onClose,
    onRunNow,
}: Props) {
    const [page, setPage] = useState(1)

    useEffect(() => {
        if (open) setPage(1)
    }, [open, query.definitionKey])

    const ledger = useTaskLedgerPage({
        ...query,
        offset: (page - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
        enabled: open,
    })

    const total = ledger.data?.total ?? 0
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
    const entries = ledger.data?.items ?? []

    useEffect(() => {
        if (page > totalPages) setPage(totalPages)
    }, [page, totalPages])

    if (!open) return null

    return (
        <div className="modal-overlay" role="presentation" onClick={onClose}>
            <div
                className="modal cron-task-ledger-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="cron-task-ledger-title"
                onClick={(event) => event.stopPropagation()}
            >
                <div className="modal-header cron-task-ledger-header">
                    <div className="modal-icon" aria-hidden>
                        <FontAwesomeIcon icon={['fas', 'file-lines']}/>
                    </div>
                    <div>
                        <h2 id="cron-task-ledger-title" className="modal-title">{title} log</h2>
                        <div className="cron-task-ledger-subtitle">Task ledger</div>
                    </div>
                </div>

                <div className="cron-task-ledger-content">
                    {ledger.isLoading ? (
                        <p className="modal-text">Loading task history...</p>
                    ) : ledger.isError ? (
                        <p className="modal-text">Could not load task history.</p>
                    ) : entries.length === 0 ? (
                        <p className="modal-text">No runs have been recorded yet.</p>
                    ) : (
                        <div className="cron-task-ledger-table" role="table" aria-label={`${title} task history`}>
                            <div className="cron-task-ledger-row cron-task-ledger-row-header" role="row">
                                <span role="columnheader">Ran</span>
                                <span role="columnheader">Result</span>
                                <span role="columnheader">Duration</span>
                            </div>
                            {entries.map((entry) => {
                                const target = targetLabel(entry, query)
                                const detail = statusDetail(entry)
                                return (
                                    <div className="cron-task-ledger-row" role="row" key={entry.id}>
                                        <span role="cell">{formatDate(entry.startedAt ?? entry.finishedAt)}</span>
                                        <span
                                            role="cell"
                                            className="cron-task-ledger-result"
                                            title={detail ?? undefined}
                                        >
                                            <span className={`cron-task-ledger-status is-${entry.status.toLowerCase()}`}>
                                                {statusLabel(entry.status)}
                                            </span>
                                            {target ? <small>{target}</small> : null}
                                        </span>
                                        <span role="cell">{formatDuration(entry.runtimeMs)}</span>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>

                <div className="cron-task-ledger-footer">
                    <nav className="cron-task-ledger-pagination" aria-label="Task ledger pages">
                        <button
                            type="button"
                            className="btn"
                            disabled={page <= 1 || ledger.isFetching}
                            onClick={() => setPage((current) => Math.max(1, current - 1))}
                        >
                            Previous
                        </button>
                        <span className="cron-task-ledger-page-label" aria-live="polite">
                            Page {page} of {totalPages}
                        </span>
                        <button
                            type="button"
                            className="btn"
                            disabled={page >= totalPages || ledger.isFetching}
                            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
                        >
                            Next
                        </button>
                    </nav>

                    <div className="modal-actions cron-task-ledger-actions">
                        <button type="button" className="btn" onClick={onClose}>Close</button>
                        <ProgressButton
                            definition={definition}
                            resourceId={0}
                            label="Run now"
                            icon={['fas', 'play']}
                            onClick={() => void onRunNow()}
                            starting={starting}
                        />
                    </div>
                </div>
            </div>
        </div>
    )
}
