import {useCallback} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import {faIcon} from '../../icons/faIcon'
import {notificationKeys, removeDevice, usePushDevices} from '../../lib/notifications'
import {useBrowserPush} from './useBrowserPush'

/** Push on this browser, and every device that gets push messages from WireLoft. */
export default function ThisDevice() {
    const queryClient = useQueryClient()
    const devices = usePushDevices()
    const refresh = useCallback(() => {
        void queryClient.invalidateQueries({queryKey: notificationKeys.devices})
    }, [queryClient])
    const push = useBrowserPush(refresh)

    const forget = async (deviceId: number) => {
        try {
            await removeDevice(deviceId)
            refresh()
        } catch (error) {
            toast.error((error as Error).message)
        }
    }

    return (
        <div className="notif-device">
            {!push.supported ? (
                <p className="help">
                    This browser cannot get push messages from WireLoft here. Push needs WireLoft over HTTPS; on an
                    iPhone or iPad, first add WireLoft to the home screen from the share menu.
                </p>
            ) : push.loading ? <p className="help">Checking…</p> : (
                <div className="notif-toolbar">
                    {push.enabled ? (
                        <>
                            <span className="notif-health notif-health--healthy">On for this device</span>
                            <button type="button" className="btn btn-secondary" disabled={push.busy} onClick={() => void push.test()}>
                                <FontAwesomeIcon icon={faIcon('fass', 'paper-plane')} aria-hidden="true"/> Send a test
                            </button>
                            <button type="button" className="btn btn-secondary" disabled={push.busy} onClick={() => void push.disable()}>
                                Turn off
                            </button>
                        </>
                    ) : (
                        <button type="button" className="btn btn-primary" disabled={push.busy} onClick={() => void push.enable()}>
                            <FontAwesomeIcon icon={faIcon('fass', 'bell')} aria-hidden="true"/> Turn on notifications here
                        </button>
                    )}
                </div>
            )}
            {push.error ? <p className="error" role="alert">{push.error}</p> : null}
            {devices.isError ? <p role="alert">Could not load the devices: {devices.error.message}</p> : null}
            {devices.data && devices.data.length > 0 ? (
                <>
                    <h3>Devices that get push messages</h3>
                    <ul className="notif-list">
                        {devices.data.map((device) => (
                            <li key={device.id} className="notif-row notif-row--compact">
                                <div className="notif-row__main">
                                    <strong>{device.deviceName}</strong>
                                    <p className="notif-row__meta">Since {device.createdAt.toLocaleDateString()}</p>
                                </div>
                                <div className="notif-row__actions">
                                    <button type="button" className="btn btn-secondary" onClick={() => void forget(device.id)}>Remove</button>
                                </div>
                            </li>
                        ))}
                    </ul>
                </>
            ) : null}
        </div>
    )
}
