import {useEffect, useMemo, useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import {faIcon} from '../../icons/faIcon'
import {
    notificationQueryKeys,
    saveRouting,
    useNotificationChannels,
    useNotificationEvents,
} from '../../lib/notifications'
import ServiceTile from './ServiceTile'
import type {BrowserPush} from './useBrowserPush'

type Column = {key: string; name: string; serviceName: string | null; enabled: boolean; health: string | null}
type Draft = Record<string, string[]>

const BROWSER = 'browser'
const PRESETS = ['custom', 'failures', 'everything', 'nothing'] as const
type Preset = typeof PRESETS[number]
const PRESET_LABEL: Record<Preset, string> = {
    custom: 'Custom',
    failures: 'Failures only',
    everything: 'Everything',
    nothing: 'Nothing',
}

const sameSet = (left: string[], right: string[]) =>
    left.length === right.length && left.every((value) => right.includes(value))

export default function RoutingPanel({push}: {push: BrowserPush}) {
    const queryClient = useQueryClient()
    const channelsQuery = useNotificationChannels()
    const eventsQuery = useNotificationEvents()
    const events = useMemo(() => eventsQuery.data ?? [], [eventsQuery.data])

    const columns = useMemo<Column[]>(() => [
        ...(push.supported ? [{
            key: BROWSER, name: 'This browser', serviceName: null, enabled: push.enabled, health: null,
        }] : []),
        ...(channelsQuery.data ?? []).map((channel) => ({
            key: String(channel.id),
            name: channel.name,
            serviceName: channel.serviceName,
            enabled: channel.enabled,
            health: channel.health,
        })),
    ], [channelsQuery.data, push.supported, push.enabled])

    const saved = useMemo<Draft>(() => ({
        [BROWSER]: push.events,
        ...Object.fromEntries((channelsQuery.data ?? []).map((channel) => [String(channel.id), channel.events])),
    }), [channelsQuery.data, push.events])

    const [draft, setDraft] = useState<Draft>(saved)
    const [saving, setSaving] = useState(false)
    const dirty = columns.some(({key}) => !sameSet(draft[key] ?? [], saved[key] ?? []))

    // Follow the server until the user starts editing.
    useEffect(() => {
        if (!dirty) setDraft(saved)
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [saved])

    const failureEvents = events.filter(({tone}) => tone === 'failure').map(({event}) => event)
    const allEvents = events.map(({event}) => event)

    const toggle = (column: string, event: string) => setDraft((current) => {
        const selected = current[column] ?? []
        return {
            ...current,
            [column]: selected.includes(event) ? selected.filter((value) => value !== event) : [...selected, event],
        }
    })

    const apply = (events: string[]) => setDraft(Object.fromEntries(columns.map(({key}) => [key, events])))

    const preset: Preset = (() => {
        const same = (target: string[]) => columns.length > 0 && columns.every(({key}) => sameSet(draft[key] ?? [], target))
        if (same(failureEvents)) return 'failures'
        if (same(allEvents)) return 'everything'
        if (same([])) return 'nothing'
        return 'custom'
    })()

    const choosePreset = (next: Preset) => {
        if (next === 'failures') apply(failureEvents)
        else if (next === 'everything') apply(allEvents)
        else if (next === 'nothing') apply([])
    }

    const save = async () => {
        setSaving(true)
        try {
            const changedChannels = (channelsQuery.data ?? [])
                .filter(({id}) => !sameSet(draft[String(id)] ?? [], saved[String(id)] ?? []))
            if (changedChannels.length > 0) {
                await saveRouting(changedChannels.map(({id}) => ({channelId: id, events: draft[String(id)] ?? []})))
            }
            if (push.supported && push.enabled && !sameSet(draft[BROWSER] ?? [], saved[BROWSER] ?? [])) {
                await push.saveEvents(draft[BROWSER] ?? [])
            }
            await queryClient.invalidateQueries({queryKey: notificationQueryKeys.channels})
            toast.success('Routing saved')
        } catch (cause) {
            toast.error(cause instanceof Error ? cause.message : 'Could not save routing')
        } finally {
            setSaving(false)
        }
    }

    return (
        <section className="notif-panel" aria-label="Routing">
            <div className="notif-panel__header">
                <p className="help">
                    Choose which events go to which channel. Only events that happen after a channel is added
                    are sent; older ones are never replayed.
                </p>
                <div className="notif-routing-tools">
                    <label className="notif-routing-preset">
                        <span>Preset</span>
                        <select
                            className="input"
                            value={preset}
                            onChange={(event) => choosePreset(event.target.value as Preset)}
                        >
                            {PRESETS.map((option) => (
                                <option key={option} value={option} disabled={option === 'custom' && preset !== 'custom'}>
                                    {PRESET_LABEL[option]}
                                </option>
                            ))}
                        </select>
                    </label>
                    <button type="button" className="btn btn-secondary" onClick={() => apply(failureEvents)}>
                        <FontAwesomeIcon icon={faIcon('fas', 'circle-exclamation')} aria-hidden="true"/>
                        Select all failures
                    </button>
                </div>
            </div>

            {columns.length === 0 ? <p className="help">Add a channel first, then route events to it.</p> : (
                <div className="notif-matrix-wrap">
                    <table className="notif-matrix">
                        <thead>
                        <tr>
                            <th scope="col">Event</th>
                            {columns.map((column) => (
                                <th
                                    key={column.key}
                                    scope="col"
                                    className={
                                        !column.enabled || column.health === 'failing' ? 'is-dimmed' : undefined
                                    }
                                >
                                    <span className="notif-matrix__channel">
                                        {column.serviceName ? <ServiceTile name={column.serviceName} size="sm"/> : (
                                            <span className="notif-tile notif-tile--sm notif-tile--builtin" aria-hidden="true">
                                                <FontAwesomeIcon icon={faIcon('fas', 'globe')}/>
                                            </span>
                                        )}
                                        <span>{column.name}</span>
                                    </span>
                                    {!column.enabled ? <small>{column.key === BROWSER ? 'Off' : 'Paused'}</small> : null}
                                    {column.enabled && column.health === 'failing' ? <small>Failing</small> : null}
                                </th>
                            ))}
                        </tr>
                        </thead>
                        <tbody>
                        {events.map(({event, label, description, tone}) => (
                            <tr key={event}>
                                <th scope="row">
                                    <strong className={`notif-tone notif-tone--${tone}`}>{label}</strong>
                                    <small>{description}</small>
                                </th>
                                {columns.map((column) => (
                                    <td
                                        key={column.key}
                                        className={
                                            !column.enabled || column.health === 'failing' ? 'is-dimmed' : undefined
                                        }
                                    >
                                        <input
                                            type="checkbox"
                                            aria-label={`${label} to ${column.name}`}
                                            checked={(draft[column.key] ?? []).includes(event)}
                                            onChange={() => toggle(column.key, event)}
                                        />
                                    </td>
                                ))}
                            </tr>
                        ))}
                        </tbody>
                    </table>
                </div>
            )}

            <div className="actions notif-routing-actions">
                <button type="button" className="btn" disabled={!dirty || saving} onClick={() => setDraft(saved)}>
                    Discard
                </button>
                <button type="button" className="btn btn-primary" disabled={!dirty || saving} onClick={() => void save()}>
                    <FontAwesomeIcon icon={faIcon('fas', saving ? 'spinner' : 'check')} spin={saving} aria-hidden="true"/>
                    Save routing
                </button>
            </div>
        </section>
    )
}
