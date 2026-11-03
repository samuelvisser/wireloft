import {useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import Switch from 'react-switch'
import toast from 'react-hot-toast'

import {faIcon} from '../../icons/faIcon'
import {changeDestination, deleteDestination, notificationKeys, testDestination} from '../../lib/notifications'
import type {DestinationRead} from '../../types/schemas/notifications'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import DestinationDialog from './DestinationDialog'
import ServiceTile from './ServiceTile'
import {KIND_LABELS} from './registries'

const HEALTH_LABELS: Record<DestinationRead['health'], string> = {
    healthy: 'Working',
    failing: 'Failing',
    untested: 'Not used yet',
    disabled: 'Off',
}

/** Where messages go and what actions call, with the built-in push to the installed app first. */
export default function Destinations({destinations}: {destinations: DestinationRead[]}) {
    const queryClient = useQueryClient()
    const [editing, setEditing] = useState<DestinationRead | 'new' | null>(null)
    const [deleting, setDeleting] = useState<DestinationRead | null>(null)
    const [testing, setTesting] = useState<number | null>(null)
    const refresh = () => queryClient.invalidateQueries({queryKey: notificationKeys.destinations})

    const test = async (destination: DestinationRead) => {
        setTesting(destination.id)
        try {
            const result = await testDestination(destination.id)
            if (result.delivered) toast.success(`${destination.name} works`)
            else toast.error(`${destination.name}: ${result.error ?? 'it failed'}`)
        } catch (error) {
            toast.error((error as Error).message)
        } finally {
            setTesting(null)
            void refresh()
        }
    }

    const toggle = async (destination: DestinationRead, enabled: boolean) => {
        try {
            await changeDestination(destination.id, {enabled})
            await refresh()
        } catch (error) {
            toast.error((error as Error).message)
        }
    }

    const remove = async (destination: DestinationRead) => {
        try {
            await deleteDestination(destination.id)
            await Promise.all([refresh(), queryClient.invalidateQueries({queryKey: notificationKeys.rules})])
            toast.success(`${destination.name} deleted`)
        } catch (error) {
            toast.error((error as Error).message)
        } finally {
            setDeleting(null)
        }
    }

    return (
        <>
            <ul className="notif-list">
                <li className="notif-row notif-row--compact">
                    <span className="notif-tile notif-tile--md notif-tile--builtin" aria-hidden="true">
                        <FontAwesomeIcon icon={faIcon('fass', 'bell')}/>
                    </span>
                    <div className="notif-row__main">
                        <div className="notif-row__title"><strong>Push to the installed app</strong><span className="notif-badge">Built in</span></div>
                        <p className="notif-row__meta">
                            Turn it on per phone or computer under This device, above.
                        </p>
                    </div>
                </li>
                {destinations.map((destination) => (
                    <li key={destination.id} className="notif-row notif-row--compact">
                        <ServiceTile name={destination.serviceName}/>
                        <div className="notif-row__main">
                            <div className="notif-row__title">
                                <strong>{destination.name}</strong>
                                <span className="notif-chip">{destination.kind === 'apprise' ? destination.serviceName : KIND_LABELS[destination.kind]}</span>
                                <span className={`notif-health notif-health--${destination.health}`}>{HEALTH_LABELS[destination.health]}</span>
                            </div>
                            <p className="notif-row__meta"><code>{destination.masked}</code></p>
                            {destination.health === 'failing' && destination.lastError ? (
                                <p className="error">Failed: {destination.lastError} <Link to="/logs">See the log</Link></p>
                            ) : null}
                        </div>
                        <div className="notif-row__actions">
                            <Switch
                                aria-label={destination.enabled ? `Turn ${destination.name} off` : `Turn ${destination.name} on`}
                                checked={destination.enabled}
                                onChange={(checked) => void toggle(destination, checked)}
                                checkedIcon={false}
                                uncheckedIcon={false}
                                height={20}
                                width={36}
                            />
                            <button type="button" className="btn btn-secondary" aria-label={`Test ${destination.name}`}
                                    disabled={testing === destination.id} onClick={() => void test(destination)}>
                                <FontAwesomeIcon icon={faIcon('fass', testing === destination.id ? 'spinner' : 'paper-plane')}
                                                 spin={testing === destination.id} aria-hidden="true"/>
                            </button>
                            <button type="button" className="btn btn-secondary" aria-label={`Edit ${destination.name}`} onClick={() => setEditing(destination)}>
                                <FontAwesomeIcon icon={faIcon('fass', 'pen')} aria-hidden="true"/>
                            </button>
                            <button type="button" className="btn btn-secondary" aria-label={`Delete ${destination.name}`} onClick={() => setDeleting(destination)}>
                                <FontAwesomeIcon icon={faIcon('fass', 'trash')} aria-hidden="true"/>
                            </button>
                        </div>
                    </li>
                ))}
            </ul>
            <div className="notif-toolbar">
                <button type="button" className="btn btn-primary" onClick={() => setEditing('new')}>
                    <FontAwesomeIcon icon={faIcon('fass', 'plus')} aria-hidden="true"/> Add destination or service
                </button>
            </div>
            {editing !== null ? <DestinationDialog destination={editing === 'new' ? null : editing} onDismiss={() => setEditing(null)}/> : null}
            {deleting ? (
                <ConfirmDialog
                    open
                    title={`Delete ${deleting.name}?`}
                    icon={faIcon('fass', 'trash')}
                    iconTone="danger"
                    onDismiss={() => setDeleting(null)}
                    confirmButton={{label: 'Delete', className: 'btn-danger', onClick: () => remove(deleting)}}
                >
                    <p>Rules that use it keep working without it.</p>
                </ConfirmDialog>
            ) : null}
        </>
    )
}
