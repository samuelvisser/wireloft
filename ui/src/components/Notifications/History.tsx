import type {DeliveryRead} from '../../types/schemas/notifications'

const STATUS_LABELS: Record<DeliveryRead['status'], string> = {
    PENDING: 'Waiting',
    SENT: 'Sent',
    FAILED: 'Failed',
    CANCELED: 'Not sent',
}

/** A failed attempt that WireLoft tries again, rather than one still waiting for its first try. */
function retrying(delivery: DeliveryRead): boolean {
    return delivery.status === 'PENDING' && !!delivery.retryAt
}

/** What was sent lately, newest first, with the reason when something failed. */
export default function History({deliveries, empty}: {deliveries: DeliveryRead[]; empty: string}) {
    if (deliveries.length === 0) return <p className="notif-empty">{empty}</p>
    return (
        <div className="notif-history-wrap">
            <table className="notif-history">
                <thead>
                    <tr><th>When</th><th>What</th><th>Where</th><th>Result</th></tr>
                </thead>
                <tbody>
                    {deliveries.map((delivery) => (
                        <tr key={delivery.id}>
                            <td>{delivery.at.toLocaleString()}</td>
                            <td>{delivery.title}</td>
                            <td>{delivery.destination}</td>
                            <td>
                                <span className={`notif-delivery notif-delivery--${retrying(delivery) ? 'failed' : delivery.status.toLowerCase()}`}>
                                    {retrying(delivery) ? 'Failed, trying again' : STATUS_LABELS[delivery.status]}
                                </span>
                                {delivery.error ? <small>{delivery.error}</small> : null}
                                {retrying(delivery) ? (
                                    <small>Next try at {delivery.retryAt!.toLocaleTimeString(undefined, {hour: '2-digit', minute: '2-digit'})}</small>
                                ) : null}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
