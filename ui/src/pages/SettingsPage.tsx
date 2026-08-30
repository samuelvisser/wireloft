import {useCallback, useEffect, useMemo, useState} from 'react'
import toast from 'react-hot-toast'

import AdvancedSettingsTab from '../components/Settings/AdvancedSettingsTab'
import AutomationSettingsTab from '../components/Settings/AutomationSettingsTab'
import DailyWireSettingsTab from '../components/Settings/DailyWireSettingsTab'
import DownloadsSettingsTab from '../components/Settings/DownloadsSettingsTab'
import GeneralSettingsTab from '../components/Settings/GeneralSettingsTab'
import {SettingsLoading} from '../components/Settings/SettingsControls'
import {useSaveSettings, useSettings} from '../lib/settings'
import {
    SETTINGS_FIELD_PATHS,
    type SettingsFieldPath,
    type SettingsValues,
} from '../types/schemas/settings'
import './SettingsPage.css'
import './SettingsEnvironmentOverrides.css'


type SettingsTab = 'general' | 'downloads' | 'automation' | 'dailywire' | 'advanced'

type SettingsTabDefinition = {
    id: SettingsTab
    label: string
    description: string
}

const SETTINGS_TABS: SettingsTabDefinition[] = [
    {id: 'general', label: 'General', description: 'Application behaviour and sessions'},
    {id: 'downloads', label: 'Downloads', description: 'Storage, naming, processing and verification'},
    {id: 'automation', label: 'Automation', description: 'Scheduler and episode monitoring'},
    {id: 'dailywire', label: 'DailyWire', description: 'Account and integration details'},
    {id: 'advanced', label: 'Advanced', description: 'Encryption files and configuration details'},
]

function cloneSettings(values: SettingsValues): SettingsValues {
    return JSON.parse(JSON.stringify(values)) as SettingsValues
}

function valueAtPath(values: SettingsValues, path: SettingsFieldPath): unknown {
    let current: unknown = values
    for (const segment of path.split('.')) {
        if (current === null || typeof current !== 'object') return undefined
        current = (current as Record<string, unknown>)[segment]
    }
    return current
}

export default function SettingsPage() {
    const settingsQuery = useSettings()
    const saveSettings = useSaveSettings()
    const [activeTab, setActiveTab] = useState<SettingsTab>('general')
    const [draft, setDraft] = useState<SettingsValues | null>(null)
    const [baseline, setBaseline] = useState<SettingsValues | null>(null)

    useEffect(() => {
        if (!settingsQuery.data) return
        setDraft(cloneSettings(settingsQuery.data.values))
        setBaseline(cloneSettings(settingsQuery.data.values))
    }, [settingsQuery.data])

    const updateDraft = useCallback((mutator: (next: SettingsValues) => void) => {
        setDraft((current) => {
            if (!current) return current
            const next = cloneSettings(current)
            mutator(next)
            return next
        })
    }, [])

    const dirtyFields = useMemo<SettingsFieldPath[]>(() => {
        if (!draft || !baseline) return []
        return SETTINGS_FIELD_PATHS.filter(
            (path) => valueAtPath(draft, path) !== valueAtPath(baseline, path),
        )
    }, [draft, baseline])
    const isDirty = dirtyFields.length > 0

    useEffect(() => {
        if (!isDirty) return

        const warnBeforeUnload = (event: BeforeUnloadEvent) => {
            event.preventDefault()
            event.returnValue = ''
        }
        window.addEventListener('beforeunload', warnBeforeUnload)
        return () => window.removeEventListener('beforeunload', warnBeforeUnload)
    }, [isDirty])

    const environmentVariableFor = useCallback((path: SettingsFieldPath): string | undefined => {
        return settingsQuery.data?.environmentOverrides[path]
    }, [settingsQuery.data?.environmentOverrides])

    const submit = async () => {
        if (!draft || !isDirty) return
        try {
            await saveSettings.mutateAsync({values: draft, changedFields: dirtyFields})
            toast.success('Settings saved to config.yml')
        } catch (error: any) {
            toast.error(error?.message || 'Failed to save settings')
        }
    }

    const discardChanges = () => {
        if (baseline) setDraft(cloneSettings(baseline))
    }

    if (settingsQuery.isError) {
        return (
            <section className="view settings-page" aria-labelledby="settings-title">
                <h1 id="settings-title">Settings</h1>
                <div className="settings-error" role="alert">
                    <h2>Settings could not be loaded</h2>
                    <p>{settingsQuery.error.message}</p>
                    <button className="btn btn-primary" type="button" onClick={() => void settingsQuery.refetch()}>
                        Try again
                    </button>
                </div>
            </section>
        )
    }

    if (settingsQuery.isLoading || !draft || !baseline) {
        return (
            <section className="view settings-page" aria-labelledby="settings-title">
                <SettingsLoading />
            </section>
        )
    }

    const updatedAt = settingsQuery.data?.updatedAt
    const tabProps = {draft, updateDraft, environmentVariableFor}

    return (
        <section className="view settings-page" aria-labelledby="settings-title">
            <div className="settings-page__heading">
                <div>
                    <h1 id="settings-title">Settings</h1>
                    <p>Configure how WireLoft downloads, monitors and serves your media.</p>
                </div>
                <div className="settings-source-status" aria-live="polite">
                    <span className="settings-source-badge is-active">config.yml</span>
                    {updatedAt ? <small>Modified {updatedAt.toLocaleString()}</small> : null}
                </div>
            </div>

            <div>
                <div className="settings-tabs" role="tablist" aria-label="Settings categories">
                    {SETTINGS_TABS.map((tab) => (
                        <button
                            key={tab.id}
                            id={`settings-tab-${tab.id}`}
                            className={`settings-tab${activeTab === tab.id ? ' is-active' : ''}`}
                            type="button"
                            role="tab"
                            aria-selected={activeTab === tab.id}
                            aria-controls={`settings-panel-${tab.id}`}
                            onClick={() => setActiveTab(tab.id)}
                        >
                            <span>{tab.label}</span>
                            <small>{tab.description}</small>
                        </button>
                    ))}
                </div>

                <div
                    id={`settings-panel-${activeTab}`}
                    className="settings-panel"
                    role="tabpanel"
                    aria-labelledby={`settings-tab-${activeTab}`}
                >
                    {activeTab === 'general' ? <GeneralSettingsTab {...tabProps} /> : null}
                    {activeTab === 'downloads' ? <DownloadsSettingsTab {...tabProps} /> : null}
                    {activeTab === 'automation' ? <AutomationSettingsTab {...tabProps} /> : null}
                    {activeTab === 'dailywire' ? <DailyWireSettingsTab {...tabProps} /> : null}
                    {activeTab === 'advanced' ? <AdvancedSettingsTab {...tabProps} /> : null}
                </div>

                <div className={`settings-actions${isDirty ? ' is-dirty' : ''}`}>
                    <div>
                        <strong>{isDirty ? 'Unsaved changes' : 'All changes saved'}</strong>
                        <span>
                            {isDirty
                                ? `${dirtyFields.length} ${dirtyFields.length === 1 ? 'setting' : 'settings'} will be written to config.yml.`
                                : 'The values shown match the active configuration.'}
                        </span>
                    </div>
                    <div className="settings-actions__buttons">
                        <button
                            className="btn"
                            type="button"
                            disabled={!isDirty || saveSettings.isPending}
                            onClick={discardChanges}
                        >
                            Discard
                        </button>
                        <button
                            className="btn btn-primary"
                            type="button"
                            disabled={!isDirty || saveSettings.isPending}
                            onClick={() => void submit()}
                        >
                            {saveSettings.isPending ? 'Saving…' : 'Save settings'}
                        </button>
                    </div>
                </div>
            </div>
        </section>
    )
}
