import {useQuery} from '@tanstack/react-query'
import {useEffect, useMemo, useRef, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import Select from 'react-select'
import Switch from 'react-switch'

import PageSubtitle from '../components/common/PageSubtitle'
import {ApplicationLogPageReadSchema, type ApplicationLogEntryRead} from '../types/schemas/log'
import './LogsPage.css'

type LogLevelOption = {
    value: string
    label: string
}

const LEVEL_OPTIONS: readonly LogLevelOption[] = [
    {value: '', label: 'All'},
    {value: 'DEBUG', label: 'Debug'},
    {value: 'INFO', label: 'Info'},
    {value: 'WARNING', label: 'Warning'},
    {value: 'ERROR', label: 'Error'},
    {value: 'CRITICAL', label: 'Critical'},
]

function isPullRequestLog(entry: ApplicationLogEntryRead): boolean {
    return entry.logger === 'uvicorn.access'
        && /"\w+ \/api\/pull(?:\?|\s)/.test(entry.message)
}

function formatTimestamp(value: string): string {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function LogsPage() {
    const [level, setLevel] = useState('')
    const [search, setSearch] = useState('')
    const [hidePullRequests, setHidePullRequests] = useState(true)
    const panelRef = useRef<HTMLDivElement | null>(null)
    const stickToBottomRef = useRef(true)

    const params = useMemo(() => {
        const query = new URLSearchParams({limit: '20000'})
        if (level) query.set('level', level)
        if (search.trim()) query.set('search', search.trim())
        return query.toString()
    }, [level, search])

    const logs = useQuery({
        queryKey: ['applicationLogs', level, search.trim()],
        queryFn: async ({signal}) => {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/logs?${params}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`HTTP ${response.status}`)
            return ApplicationLogPageReadSchema.parse(await response.json())
        },
        refetchInterval: 2000,
        refetchOnMount: 'always',
    })

    const canShowPullRequests = level === '' || level === 'INFO'
    const items = useMemo(() => {
        const entries = logs.data?.items ?? []
        if (!canShowPullRequests || !hidePullRequests) return entries
        return entries.filter((entry) => !isPullRequestLog(entry))
    }, [canShowPullRequests, hidePullRequests, logs.data?.items])
    const total = items.length

    useEffect(() => {
        const panel = panelRef.current
        if (!panel || !stickToBottomRef.current) return
        panel.scrollTop = panel.scrollHeight
    }, [items])

    return (
        <section className="view logs-view" aria-labelledby="logs-title">
            <div className="view-header">
                <h1 id="logs-title">Log</h1>
                <PageSubtitle summary={<>Application-wide WireLoft log output.</>}>
                    <p>
                        Logs from the backend, scheduler, task workers, downloads and web server are collected here.
                        The latest 20,000 records from the current server process are retained.
                    </p>
                </PageSubtitle>
            </div>

            <div className="logs-toolbar">
                <label className="logs-search">
                    <span className="sr-only">Search logs</span>
                    <FontAwesomeIcon icon={['fas', 'magnifying-glass']} aria-hidden="true"/>
                    <input
                        type="search"
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search logs..."
                    />
                </label>
                <div className="logs-level">
                    <label htmlFor="logs-level-select">Level</label>
                    <Select<LogLevelOption, false>
                        inputId="logs-level-select"
                        className="logs-level-select"
                        classNamePrefix="select"
                        options={LEVEL_OPTIONS}
                        value={LEVEL_OPTIONS.find((option) => option.value === level) ?? LEVEL_OPTIONS[0]}
                        onChange={(option) => setLevel(option?.value ?? '')}
                        isSearchable={false}
                        isClearable={false}
                    />
                </div>
                {canShowPullRequests && (
                    <div className="logs-pull-toggle">
                        <label id="logs-hide-pull-requests-label" htmlFor="logs-hide-pull-requests">Hide Pull requests</label>
                        <Switch
                            id="logs-hide-pull-requests"
                            checked={hidePullRequests}
                            onChange={setHidePullRequests}
                            onColor="#0ea5e9"
                            offColor="#94a3b8"
                            uncheckedIcon={false}
                            checkedIcon={false}
                            aria-labelledby="logs-hide-pull-requests-label"
                        />
                    </div>
                )}
                <strong className="logs-count">{total.toLocaleString()} {total === 1 ? 'entry' : 'entries'}</strong>
            </div>

            <div
                ref={panelRef}
                className="logs-panel"
                role="log"
                aria-live="off"
                aria-label="Application logs"
                onScroll={(event) => {
                    const panel = event.currentTarget
                    stickToBottomRef.current = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80
                }}
            >
                {logs.isPending ? (
                    <div className="logs-message">
                        <FontAwesomeIcon className="wl-progress-icon" icon={['fas', 'spinner']}/>
                        Loading logs...
                    </div>
                ) : logs.error ? (
                    <div className="logs-message is-error">
                        {logs.error instanceof Error ? logs.error.message : 'Could not load logs.'}
                    </div>
                ) : items.length === 0 ? (
                    <div className="logs-message">No log entries match the current filters.</div>
                ) : (
                    items.map((entry) => (
                        <div className="log-entry" key={entry.id}>
                            <time>{formatTimestamp(entry.timestamp)}</time>
                            <strong className={`log-level is-${entry.level.toLowerCase()}`}>{entry.level}</strong>
                            <span className="log-logger">[{entry.logger}]</span>
                            <span className="log-message">
                                {entry.message}
                                {entry.exception && <pre>{entry.exception}</pre>}
                            </span>
                        </div>
                    ))
                )}
            </div>
        </section>
    )
}
