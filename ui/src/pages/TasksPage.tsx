import {useQuery} from '@tanstack/react-query'
import {useEffect, useMemo, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import Select from 'react-select'
import {faIcon} from '../icons/faIcon'

import {Column, DataTable} from '../components/DataTable/DataTable'
import ProgressBar from '../components/common/ProgressBar'
import PageSubtitle from '../components/common/PageSubtitle'
import {useTaskLedgerInfinite} from '../lib/taskLedger'
import {useFilterChipPress} from '../lib/useFilterChipPress'
import {waitingPresentation} from '../lib/progressPresentation'
import {TaskDefinitionReadSchema, type TaskLedgerEntryRead} from '../types/schemas/task'
import {createSelectRegistry} from '../utils/selectRegistry'
import './TasksPage.css'

type TaskStatusFilter = {
    value: string
    label: string
}

type TaskDefinitionOption = {
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
    if (status === 'SUCCEEDED') return faIcon('fas', 'circle-check')
    if (status === 'FAILED') return faIcon('fas', 'triangle-exclamation')
    if (status === 'CANCELED') return faIcon('fas', 'circle-xmark')
    if (status === 'RETRY_SCHEDULED') return faIcon('fas', 'clock-rotate-left')
    if (status === 'SCHEDULED' || status === 'QUEUED') return faIcon('fas', 'clock')
    return faIcon('fas', 'spinner')
}

function statusLabel(row: TaskLedgerEntryRead): string {
    if (row.status === 'RETRY_SCHEDULED') return 'Retry scheduled'
    return row.status.toLowerCase().replace(/^./, (character) => character.toUpperCase())
}

function taskMessage(row: TaskLedgerEntryRead): string | null {
    if (row.lastError) return row.lastError
    if (row.waitState) {
        return waitingPresentation(
            row.waitState.reason,
            row.waitState.message,
            row.progress ?? null,
            row.waitState.until,
        ).detail
    }
    return row.message || null
}

function TaskStatus({row}: {row: TaskLedgerEntryRead}) {
    const active = ACTIVE_STATUSES.has(row.status)
    const wait = active && row.waitState
        ? waitingPresentation(row.waitState.reason, row.waitState.message, row.progress ?? null, row.waitState.until)
        : null
    const hasProgress = active && !wait && row.progress != null
    const text = row.status === 'RUNNING' && !hasProgress
        ? (row.message || 'Working')
        : statusLabel(row)

    return (
        <span className={`task-progress-status is-${row.status.toLowerCase().replace(/_/g, '-')}`}>
            <span className="task-progress-heading">
                <span className="task-progress-label">
                    <FontAwesomeIcon
                        icon={wait?.icon ?? statusIcon(row.status)}
                        className={active && !hasProgress && !wait ? 'wl-progress-icon' : undefined}
                        aria-hidden="true"
                    />
                    {wait?.label ?? (hasProgress ? `${row.progress}%` : text)}
                </span>
            </span>
            {active && (
                <ProgressBar
                    value={wait?.percent ?? (hasProgress ? row.progress : null)}
                    mode={wait?.mode ?? (hasProgress ? 'determinate' : row.status === 'RUNNING' ? 'indeterminate' : 'waiting')}
                    ariaLabel={`${row.definitionTitle} progress`}
                    detail={wait?.detail ?? row.message ?? statusLabel(row)}
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
    const [definitionKey, setDefinitionKey] = useState('')
    const [statuses, setStatuses] = useState<Set<string>>(() => new Set(DEFAULT_STATUSES))
    const filterPress = useFilterChipPress()
    const sentinelRef = useRef<HTMLDivElement | null>(null)
    const selectedStatuses = useMemo(
        () => setsEqual(statuses, DEFAULT_STATUSES) ? undefined : [...statuses].sort(),
        [statuses],
    )
    const definitions = useQuery({
        queryKey: ['taskDefinitions'],
        queryFn: async ({signal}) => {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/tasks/definitions`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            return TaskDefinitionReadSchema.array().parse(await response.json())
        },
        staleTime: Infinity,
    })
    const definitionReg = useMemo(() => {
        const spec: Record<string, {label: string}> = {'': {label: 'All'}}
        const values = ['']
        const sortedDefinitions = [...(definitions.data ?? [])]
            .sort((left, right) => left.title.localeCompare(right.title))
        for (const definition of sortedDefinitions) {
            spec[definition.key] = {label: definition.title}
            values.push(definition.key)
        }
        return createSelectRegistry('TaskDefinitionFilter', spec, values)
    }, [definitions.data])
    const query = useTaskLedgerInfinite({
        definitionKey: definitionKey || undefined,
        status: selectedStatuses,
        limit: 100,
        enabled: statuses.size > 0,
    })
    const rows = query.items
    const total = query.total

    useEffect(() => {
        const element = sentinelRef.current
        if (!element || !query.hasNextPage) return

        const observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting) && !query.isFetching) {
                    void query.fetchNextPage()
                }
            },
            {rootMargin: '400px 0px'},
        )
        observer.observe(element)
        return () => observer.disconnect()
    }, [query.fetchNextPage, query.hasNextPage, query.isFetching])

    const toggleStatus = (value: string) => {
        setStatuses((current) => {
            const next = new Set(current)
            if (next.has(value)) next.delete(value)
            else next.add(value)
            return next
        })
    }

    const pressStatus = (value: string) => {
        filterPress.press(
            value,
            () => toggleStatus(value),
            () => setStatuses(new Set([value])),
        )
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
                    {taskMessage(row) || '—'}
                </span>
            ),
            dataLabel: 'Message',
            sortAccessor: taskMessage,
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
                        This ledger contains every task execution. Active tasks report progress when available.
                    </p>
                    <p>
                        Use this view to diagnose certain problems or track task progress.
                    </p>
                </PageSubtitle>
            </div>

            <div className="task-definition-filter">
                <label htmlFor="tasks-definition-select">Task</label>
                <Select<TaskDefinitionOption, false>
                    inputId="tasks-definition-select"
                    className="task-definition-select"
                    classNamePrefix="select"
                    options={definitionReg.options}
                    value={definitionReg.options.find((option) => option.value === definitionKey) ?? definitionReg.options[0]}
                    onChange={(option) => setDefinitionKey(option?.value ?? '')}
                    isSearchable
                    isClearable={false}
                    isLoading={definitions.isPending}
                />
            </div>

            <div className="task-filter-row">
                <div className="filter-chip-group" role="group" aria-label="Filter tasks by status">
                    {STATUS_FILTERS.map((option) => (
                        <button
                            key={option.value}
                            type="button"
                            className="filter-chip"
                            aria-pressed={statuses.has(option.value)}
                            onClick={() => pressStatus(option.value)}
                        >
                            {option.label}
                        </button>
                    ))}
                    {!setsEqual(statuses, DEFAULT_STATUSES) && (
                        <button
                            type="button"
                            className="filter-chip-reset"
                            onClick={() => {
                                filterPress.reset()
                                setStatuses(new Set(DEFAULT_STATUSES))
                            }}
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
                        <FontAwesomeIcon className="wl-progress-icon" icon={faIcon('fas', 'spinner')}/>
                        Loading more tasks...
                    </div>
                )}
            </div>
        </section>
    )
}
