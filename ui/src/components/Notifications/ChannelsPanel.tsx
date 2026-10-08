import {useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import Switch from 'react-switch'

import {faIcon} from '../../icons/faIcon'
import {
    deleteChannel,
    notificationQueryKeys,
    setChannelEnabled,
    testChannel,
    useNotificationChannels,
    useNotificationEvents,
} from '../../lib/notifications'
import type {NotificationChannelRead} from '../../types/schemas/notifications'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import ChannelDialog from './ChannelDialog'
import ServiceTile from './ServiceTile'
import type {BrowserPush} from './useBrowserPush'

const HEALTH_LABEL: Record<NotificationChannelRead['health'], string> = {
    healthy: 'Healthy',
    failing: 'Failing',
    untested: 'Not tested yet',
    disabled: 'Paused',
}

function EventChips({events, labels}: {events: string[]; labels: Map<string, string>}) {
    if (events.length === 0) return <span className="notif-chip notif-chip--empty">No events routed</span>
    return (
        <>
            {events.map((event) => (
                <span key={event} className="notif-chip">{labels.get(event) ?? event}</span>
            ))}
        </>
    )
}

function BrowserRow({push, labels}: {push: BrowserPush; labels: Map<string, string>}) {
    const toggle = async () => {
        try {
            await (push.enabled ? push.disable() : push.enable())
        } catch {
            // The hook already exposes the message.
        }
    }
    return (
        <li className="notif-row">
            <span className="notif-tile notif-tile--md notif-tile--builtin" aria-hidden="true">
                <FontAwesomeIcon icon={faIcon('fas', 'globe')}/>
            </span>
            <div className="notif-row__main">
                <div className="notif-row__title">
                    <strong>This browser (Web Push)</strong>
                    <span className="notif-badge">Built in</span>
                </div>
                {!push.supported ? (
                    <p className="notif-row__meta">
                        Needs a supported browser and HTTPS. On iOS, install WireLoft on your Home Screen first.
                        Not available in Vite development mode.
                    </p>
                ) : (
                    <>
                        <div className="notif-row__chips">
                            {push.enabled
                                ? <EventChips events={push.events} labels={labels}/>
                                : <span className="notif-chip notif-chip--empty">Off for this browser</span>}
                        </div>
                        {push.error ? <p role="alert" className="error">{push.error}</p> : null}
                        {typeof Notification !== 'undefined' && Notification.permission === 'denied' ? (
                            <p className="notif-row__meta" role="status">
                                Browser notifications are blocked. Allow them in the browser or system settings.
                            </p>
                        ) : null}
                    </>
                )}
            </div>
            {push.supported ? (
                <div className="notif-row__actions">
                    <Switch
                        checked={push.enabled}
                        disabled={push.loading || push.busy}
                        onChange={() => void toggle()}
                        onColor="#0ea5e9"
                        offColor="#94a3b8"
                        checkedIcon={false}
                        uncheckedIcon={false}
                        height={22}
                        width={42}
                        handleDiameter={18}
                        aria-label="Enable Web Push on this browser"
                    />
                </div>
            ) : null}
        </li>
    )
}

function ChannelRow({
    channel,
    labels,
    onEdit,
    onDelete,
}: {
    channel: NotificationChannelRead
    labels: Map<string, string>
    onEdit: () => void
    onDelete: () => void
}) {
    const queryClient = useQueryClient()
    const [testing, setTesting] = useState(false)
    const refresh = () => queryClient.invalidateQueries({queryKey: notificationQueryKeys.channels})

    const test = async () => {
        setTesting(true)
        try {
            const result = await testChannel(channel.id)
            if (result.delivered) toast.success(`Test sent to ${channel.name}`)
            else toast.error(result.error ?? `Could not send to ${channel.name}`)
        } catch (cause) {
            toast.error(cause instanceof Error ? cause.message : 'Could not send the test notification')
        } finally {
            setTesting(false)
            await refresh()
        }
    }

    const toggle = async (enabled: boolean) => {
        try {
            await setChannelEnabled(channel.id, enabled)
        } catch (cause) {
            toast.error(cause instanceof Error ? cause.message : 'Could not update the channel')
        }
        await refresh()
    }

    return (
        <li className="notif-row">
            <ServiceTile name={channel.serviceName}/>
            <div className="notif-row__main">
                <div className="notif-row__title">
                    <strong>{channel.name}</strong>
                    <span className={`notif-health notif-health--${channel.health}`}>
                        {HEALTH_LABEL[channel.health]}
                    </span>
                </div>
                <p className="notif-row__meta"><code>{channel.maskedUrl}</code></p>
                <div className="notif-row__chips">
                    <EventChips events={channel.events} labels={labels}/>
                </div>
                {channel.lastError ? <p className="error">{channel.lastError}</p> : null}
            </div>
            <div className="notif-row__actions">
                <button type="button" className="btn btn-secondary" disabled={testing} onClick={() => void test()}>
                    <FontAwesomeIcon
                        icon={faIcon('fas', testing ? 'spinner' : 'paper-plane')}
                        spin={testing}
                        aria-hidden="true"
                    />
                    Test
                </button>
                <button type="button" className="btn btn-secondary" aria-label={`Edit ${channel.name}`} onClick={onEdit}>
                    <FontAwesomeIcon icon={faIcon('fas', 'pen')} aria-hidden="true"/>
                </button>
                <button type="button" className="btn btn-secondary" aria-label={`Delete ${channel.name}`} onClick={onDelete}>
                    <FontAwesomeIcon icon={faIcon('fas', 'trash')} aria-hidden="true"/>
                </button>
                <Switch
                    checked={channel.enabled}
                    onChange={(checked) => void toggle(checked)}
                    onColor="#0ea5e9"
                    offColor="#94a3b8"
                    checkedIcon={false}
                    uncheckedIcon={false}
                    height={22}
                    width={42}
                    handleDiameter={18}
                    aria-label={`Send notifications to ${channel.name}`}
                />
            </div>
        </li>
    )
}

export default function ChannelsPanel({push}: {push: BrowserPush}) {
    const queryClient = useQueryClient()
    const channelsQuery = useNotificationChannels()
    const eventsQuery = useNotificationEvents()
    const [dialog, setDialog] = useState<{channel: NotificationChannelRead | null} | null>(null)
    const [pendingDelete, setPendingDelete] = useState<NotificationChannelRead | null>(null)

    const labels = new Map((eventsQuery.data ?? []).map(({event, label}) => [event, label]))
    const channels = channelsQuery.data ?? []

    const confirmDelete = async () => {
        if (!pendingDelete) return
        try {
            await deleteChannel(pendingDelete.id)
            toast.success(`Deleted ${pendingDelete.name}`)
        } catch (cause) {
            toast.error(cause instanceof Error ? cause.message : 'Could not delete the channel')
        }
        setPendingDelete(null)
        await queryClient.invalidateQueries({queryKey: notificationQueryKeys.channels})
    }

    return (
        <section className="notif-panel" aria-label="Channels">
            <div className="notif-panel__header">
                <p className="help">
                    Send WireLoft alerts to any service Apprise supports. Secrets are stored encrypted and only
                    shown masked.
                </p>
                <button type="button" className="btn btn-primary" onClick={() => setDialog({channel: null})}>
                    <FontAwesomeIcon icon={faIcon('fas', 'plus')} aria-hidden="true"/>
                    Add channel
                </button>
            </div>

            {channelsQuery.isError ? <p role="alert" className="error">Could not load channels.</p> : null}

            <ul className="notif-list">
                <BrowserRow push={push} labels={labels}/>
                {channels.map((channel) => (
                    <ChannelRow
                        key={channel.id}
                        channel={channel}
                        labels={labels}
                        onEdit={() => setDialog({channel})}
                        onDelete={() => setPendingDelete(channel)}
                    />
                ))}
            </ul>
            {!channelsQuery.isLoading && channels.length === 0 ? (
                <p className="help">No Apprise channels yet. Add one to get alerts in Discord, Telegram, ntfy, email and more.</p>
            ) : null}

            {dialog ? (
                <ChannelDialog channel={dialog.channel} onDismiss={() => setDialog(null)}/>
            ) : null}

            <ConfirmDialog
                open={pendingDelete !== null}
                title="Delete channel?"
                icon={faIcon('fas', 'trash')}
                iconTone="danger"
                onDismiss={() => setPendingDelete(null)}
                confirmButton={{
                    label: 'Delete',
                    className: 'btn btn-danger',
                    onClick: confirmDelete,
                }}
            >
                <p>
                    {pendingDelete?.name} and its routing will be removed. Notifications already sent are not affected.
                </p>
            </ConfirmDialog>
        </section>
    )
}
