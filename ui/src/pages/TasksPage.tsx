import {useEffect, useMemo, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'

import {Column, DataTable} from '../components/DataTable/DataTable'
import ProgressBar from '../components/common/ProgressBar'
import PageSubtitle from '../components/common/PageSubtitle'
import {useTaskLedgerInfinite} from '../lib/taskLedger'
import type {TaskLedgerEntryRead} from '../types/schemas/task'
import './TasksPage.css'

type TaskStatusFilter = {
    value: string
    label: string
}

const STATUS_FILTERS: TaskStatusFilter[] = [
    {value: 'SCHEDULED', label: 'Scheduled'},
    {value: 'QUEUED', label: 'Queued'},
    {value: 'RUNNING', label: 'Running'},
    {value: 'RETRY_SCHEDULED', label: 'Retry scheduled'},
    {value: 'SUCCEEDED', label: 'Succeeded'},
    {value: 'FAILED', label: 'Failed'},
    {value: 'CANCELED', label: 'Canceled'},
]

const ACTIVE_STATUSES = new Set(['SCHEDULED', 'QUEUED', 'RUNNING', 'RETRY_SCHEDULED'])
const DEFAULT_STATUSES = new Set(STATUS_FILTERS.map((item) => item.value))

function formatDate(value: string | null | undefined): string {
    if (!value) return '—'
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatDuration(milliseconds: number | null | undefined): string {
    if (milliseconds == null) return '—'
    if (milliseconds < 1000) return `${Math.max(0, Math.round(milliseconds))} ms`
    const totalSeconds = Math.round(milliseconds / 1000)
    if (totalSeconds < 60) return `${totalSeconds} s`
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60
    if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
    const hours = Math.floor(minutes / 60)
    const remainder = minutes % 60
    return remainder ? `${hours}h ${remainder}m` : `${hours}h`
}

function resourceLabel(row: TaskLedgerEntryRead): string {
    const label = row.resourceType.replace(/_/g, ' ').replace(/^./, (character) => character.toUpperCase())
    return row.resourceId == null ? label : `${label} #${row.resourceId}`
}

function statusIcon(status: string): IconProp {
    if (status === 'SUCCEEDED') return ['fas', 'circle-check']
    if (status === 'FAILED') return ['fas', 'triangle-exclamation']
    if (status === 'CANCELED') return ['fas', 'circle-xmark']
    if (status === 'RETRY_SCHEDULED') return ['fas', 'clock-rotate-left']
    if (status === 'SCHEDULED' || status === 'QUEUED') return ['fas', 'clock']
    return ['fas', 'spinner']
}

function statusLabel(row: TaskLedgerEntryRead): string {
    if (row.status === 'RETRY_SCHEDULED') return 'Retry scheduled'
    return row.status.toLowerCase().replace(/^./, (character) => character.toUpperCase())
}

function waitLabel(waitState: Record<string, unknown> | null | undefined): string | null {
    if (!waitState) return null
    const reason = typeof waitState.reason === 'string' ? waitState.reason : ''
    const labels: Record<string, string> = {
        daily_wire_request_cooldown: 'Cooldown',
        daily_wire_request_queue: 'API queue',
        request_spacing: 'Waiting',
        upstream_retry: 'Retry wait',
        retry_backoff: 'Retry wait',
        download_capacity: 'Queued',
        sidecar_capacity: 'Asset queue',
        processing_capacity: 'Processing queue',
        custom_indexes: 'Preparing',
        previous_attempt: 'Restarting',
    }
    return labels[reason] || 'Waiting'
}

function TaskStatus({row}: {row: TaskLedgerEntryRead}) {
    const active = ACTIVE_STATUSES.has(row.status)
    const wait = active ? waitLabel(row.waitState) : null
    const hasProgress = active && !wait && row.progress != null
    const waitMessage = typeof row.waitState?.message === 'string' ? row.waitState.message : null
    const text = wait
        ? wait
        : row.status === 'RUNNING' && !hasProgress
            ? (row.message || 'Working')
            : statusLabel(row)

    return (
        <span className={`task-progress-status is-${row.status.toLowerCase().replace(/_/g, '-')}`}>
            <span className="task-progress-heading">
                <span className="task-progress-label">
                    <FontAwesomeIcon
                        icon={statusIcon(row.status)}
                        className={active && !hasProgress ? 'wl-progress-icon' : undefined}
                        aria-hidden="true"
                    />
                    {hasProgress ? `${row.progress}%` : text}
                </span>
            </span>
            {active && (
                <ProgressBar
                    value={hasProgress ? row.progress : null}
                    mode={hasProgress ? 'determinate' : wait ? 'waiting' : row.status === 'RUNNING' ? 'indeterminate' : 'waiting'}
                    ariaLabel={`${row.definitionTitle} progress`}
                    detail={waitMessage || row.message || statusLabel(row)}
                />
            )}
        </span>
    )
}

function setsEqual(left: Set<string>, right: Set<string>): boolean {
    if (left.size !== right.size) return false
    for (const value of left) if (!right.has(value)) return false
    return true
}

export default function TasksPage() {
    const [statuses, setStatuses] = useState<Set<string>>(() => new Set(DEFAULT_STATUSES))
    const sentinelRef = useRef<HTMLDivElement | null>(null)
    const selectedStatuses = useMemo(() => [...statuses].sort(), [statuses])
    const query = useTaskLedgerInfinite({
        status: selectedStatuses,
        limit: 100,
        enabled: statuses.size > 0,
    })
    const rows = useMemo(
        () => query.data?.pages.flatMap((page) => page.items) ?? [],
        [query.data],
    )
    const total = query.data?.pages[0]?.total ?? 0

    useEffect(() => {
        const element = sentinelRef.current
        if (!element || !query.hasNextPage) return

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting) && !query.isFetchingNextPage) {
                    void query.fetchNextPage()
                }
            },
            {rootMargin: '400px 0px'},
        )
        observer.observe(element)
        return () => observer.disconnect()
    }, [query.fetchNextPage, query.hasNextPage, query.isFetchingNextPage])

    const toggleStatus = (value: string) => {
        setStatuses((current) => {
            const next = new Set(current)
            if (next.has(value)) next.delete(value)
            else next.add(value)
            return next
        })
    }

    const columns: Column<TaskLedgerEntryRead>[] = [
        {
            header: 'Task',
            cell: (row) => (
                <div className="task-name">
                    <strong>{row.definitionTitle}</strong>
                    <small>{row.definitionKey}</small>
                </div>
            ),
            dataLabel: 'Task',
            sortAccessor: (row) => row.definitionTitle,
            width: '20%',
        },
        {
            header: 'Resource',
            accessor: resourceLabel,
            dataLabel: 'Resource',
            sortAccessor: resourceLabel,
            width: '13%',
        },
        {
            header: 'Status',
            cell: (row) => <TaskStatus row={row}/>,
            dataLabel: 'Status',
            sortAccessor: (row) => row.status,
            width: '17%',
        },
        {
            header: 'Message',
            cell: (row) => (
                <span className={row.lastError ? 'task-message is-error' : 'task-message'}>
                    {row.lastError || row.message || '—'}
                </span>
            ),
            dataLabel: 'Message',
            sortAccessor: (row) => row.lastError || row.message,
        },
        {
            header: 'Attempts',
            cell: (row) => (
                <span>{row.attemptCount}{row.maxRetries > 0 ? ` / ${row.maxRetries + 1}` : ''}</span>
            ),
            align: 'center',
            dataLabel: 'Attempts',
            sortAccessor: (row) => row.attemptCount,
            width: '8%',
        },
        {
            header: 'Started',
            accessor: (row) => formatDate(row.startedAt ?? row.createdAt),
            dataLabel: 'Started',
            sortAccessor: (row) => new Date(row.startedAt ?? row.createdAt),
            width: '14%',
        },
        {
            header: 'Duration',
            accessor: (row) => formatDuration(row.runtimeMs),
            align: 'right',
            dataLabel: 'Duration',
            sortAccessor: (row) => row.runtimeMs,
            width: '9%',
        },
    ]

    return (
        <section className="view" aria-labelledby="tasks-title">
            <div className="view-header">
                <h1 id="tasks-title">Tasks</h1>
                <PageSubtitle summary={<>Background and user-triggered work performed by WireLoft.</>}>
                    <p>
                        This ledger contains every task execution. Active tasks report percentage progress when available;
                        otherwise their current activity is shown with an indeterminate indicator.
                    </p>
                </PageSubtitle>
            </div>

            <div className="task-filter-row">
                <div className="filter-chip-group" role="group" aria-label="Filter tasks by status">
                    {STATUS_FILTERS.map((option) => (
                        <button
                            key={option.value}
                            type="button"
                            className="filter-chip"
                            aria-pressed={statuses.has(option.value)}
                            onClick={() => toggleStatus(option.value)}
                        >
                            {option.label}
                        </button>
                    ))}
                    {!setsEqual(statuses, DEFAULT_STATUSES) && (
                        <button
                            type="button"
                            className="filter-chip-reset"
                            onClick={() => setStatuses(new Set(DEFAULT_STATUSES))}
                        >
                            Reset filters
                        </button>
                    )}
                </div>
                <strong className="task-view-count">{total.toLocaleString()} {total === 1 ? 'task' : 'tasks'}</strong>
            </div>

            <div className="form-row">
                <DataTable<TaskLedgerEntryRead>
                    ariaLabel="Task ledger"
                    columns={columns}
                    data={rows}
                    loading={query.isPending}
                    error={query.error}
                    rowKey={(row) => row.id}
                    className="table tasks-table"
                    wrapperClassName="table-wrapper tasks-table-wrapper"
                    emptyMessage={statuses.size === 0 ? 'Select at least one status to show tasks.' : 'No tasks match these filters.'}
                    mobileSummary={(row) => (
                        <div>
                            <div className="mobile-summary-title">{row.definitionTitle}</div>
                            <div className="mobile-summary-subtitle">{resourceLabel(row)}</div>
                            <div className="mobile-summary-meta"><TaskStatus row={row}/></div>
                        </div>
                    )}
                />
                <div ref={sentinelRef} className="infinite-scroll-sentinel" aria-hidden="true"/>
                {query.isFetchingNextPage && (
                    <div className="task-table-loading">
                        <FontAwesomeIcon className="wl-progress-icon" icon={['fas', 'spinner']}/>
                        Loading more tasks...
                    </div>
                )}
            </div>
        </section>
    )
}
