import {useState} from 'react'

import ChannelsPanel from './ChannelsPanel'
import DeliveryHistoryPanel from './DeliveryHistoryPanel'
import RoutingPanel from './RoutingPanel'
import {useBrowserPush} from './useBrowserPush'
import './notifications.css'

type Section = 'channels' | 'routing' | 'history'

const SECTIONS: {id: Section; label: string}[] = [
    {id: 'channels', label: 'Channels'},
    {id: 'routing', label: 'Routing'},
    {id: 'history', label: 'Delivery history'},
]

export default function NotificationsSettingsTab() {
    const [section, setSection] = useState<Section>('channels')
    const push = useBrowserPush()

    return (
        <div className="notif">
            <div className="notif-seg" role="tablist" aria-label="Notification settings">
                {SECTIONS.map(({id, label}) => (
                    <button
                        key={id}
                        type="button"
                        role="tab"
                        aria-selected={section === id}
                        className={`notif-seg__item${section === id ? ' is-active' : ''}`}
                        onClick={() => setSection(id)}
                    >
                        {label}
                    </button>
                ))}
            </div>
            {section === 'channels' ? <ChannelsPanel push={push}/> : null}
            {section === 'routing' ? <RoutingPanel push={push}/> : null}
            {section === 'history' ? <DeliveryHistoryPanel active/> : null}
        </div>
    )
}
