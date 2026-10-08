import {useNotificationDeliveries, useNotificationEvents} from '../../lib/notifications'
import type {NotificationDeliveryRead} from '../../types/schemas/notifications'

const STATUS_LABEL: Record<NotificationDeliveryRead['status'], string> = {
    SENT: 'Sent',
    PENDING: 'Retrying',
    FAILED: 'Failed',
    CANCELED: 'Canceled',
}

const timeFormat = new Intl.DateTimeFormat(undefined, {dateStyle: 'medium', timeStyle: 'short'})

export default function DeliveryHistoryPanel({active}: {active: boolean}) {
    const deliveriesQuery = useNotificationDeliveries(active)
    const eventsQuery = useNotificationEvents()
    const labels = new Map((eventsQuery.data ?? []).map(({event, label}) => [event, label]))
    const deliveries = deliveriesQuery.data ?? []

    return (
        <section className="notif-panel" aria-label="Delivery history">
            <p className="help">
                The latest notifications sent to your channels and this browser. Failed attempts are retried
                automatically a few times.
            </p>
            {deliveriesQuery.isError ? <p role="alert" className="error">Could not load delivery history.</p> : null}
            {!deliveriesQuery.isLoading && deliveries.length === 0 ? (
                <p className="help">Nothing has been sent yet.</p>
            ) : (
                <ul className="notif-list">
                    {deliveries.map((delivery) => (
                        <li key={delivery.id} className="notif-row notif-row--compact">
                            <div className="notif-row__main">
                                <div className="notif-row__title">
                                    <strong>{delivery.title}</strong>
                                    <span className={`notif-delivery notif-delivery--${delivery.status.toLowerCase()}`}>
                                        {STATUS_LABEL[delivery.status]}
                                    </span>
                                </div>
                                <p className="notif-row__meta">
                                    {labels.get(delivery.event) ?? delivery.event} to {delivery.destination}
                                    {' · '}
                                    <time dateTime={delivery.at.toISOString()}>{timeFormat.format(delivery.at)}</time>
                                </p>
                                {delivery.error ? <p className="error">{delivery.error}</p> : null}
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    )
}
