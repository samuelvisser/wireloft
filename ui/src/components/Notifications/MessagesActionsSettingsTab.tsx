import './notifications.css'
import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'

import {
    notificationKeys,
    restoreDefaultRules,
    useDestinations,
    useNotificationEvents,
    useNotificationHistory,
    useRules,
} from '../../lib/notifications'
import {SettingsLoading, SettingsSection} from '../Settings/SettingsControls'
import Destinations from './Destinations'
import History from './History'
import Rules from './Rules'
import ThisDevice from './ThisDevice'

/** Settings › Messages and actions: push on this device, destinations and services, the rules, and what was sent. */
export default function MessagesActionsSettingsTab() {
    const queryClient = useQueryClient()
    const events = useNotificationEvents()
    const destinations = useDestinations()
    const rules = useRules()
    const history = useNotificationHistory()
    const [restoring, setRestoring] = useState(false)

    const failed = events.error ?? destinations.error ?? rules.error
    if (failed) return <p role="alert">Could not load messages and actions: {failed.message}</p>
    if (!events.data || !destinations.data || !rules.data) return <SettingsLoading/>

    const restore = async () => {
        setRestoring(true)
        try {
            await restoreDefaultRules()
            await queryClient.invalidateQueries({queryKey: notificationKeys.rules})
            toast.success('Default rules restored')
        } catch (error) {
            toast.error((error as Error).message)
        } finally {
            setRestoring(false)
        }
    }

    return (
        <div className="notif">
            <SettingsSection
                title="This device"
                description="Push messages to this phone or computer. Rules choose what is pushed to your devices."
                bodyClassName="notif-panel-body"
            >
                <ThisDevice/>
            </SettingsSection>
            <SettingsSection
                title="Destinations and services"
                description="Where messages go, and the media servers, webhooks and scripts that rules can call."
                bodyClassName="notif-panel-body"
            >
                <Destinations destinations={destinations.data}/>
            </SettingsSection>
            <SettingsSection
                title="Rules"
                description="Each rule says what happens, in which Shows, and where it goes. The same problem is sent again only after a day."
                bodyClassName="notif-panel-body"
            >
                <Rules rules={rules.data} events={events.data} destinations={destinations.data}/>
                <div className="notif-toolbar">
                    <button type="button" className="btn btn-secondary" disabled={restoring} onClick={() => void restore()}>
                        Restore default rules
                    </button>
                    <span className="help">Brings back any default rule that was deleted, without touching your own rules.</span>
                </div>
            </SettingsSection>
            <SettingsSection
                title="History"
                description="What was sent lately, and what failed."
                bodyClassName="notif-panel-body"
                defaultOpen={false}
            >
                <History deliveries={history.data ?? []} empty="Nothing was sent yet."/>
            </SettingsSection>
        </div>
    )
}
