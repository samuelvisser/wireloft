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
import './SettingsSaveState.css'


type SettingsTab = 'general' | 'downloads' | 'automation' | 'dailywire' | 'advanced'

type SettingsTabDefinition = {
    id: SettingsTab
    label: string
    description: string
}

type NumberFieldConstraint = {
    label: string
    min?: number
    max?: number
}

const SETTINGS_TABS: SettingsTabDefinition[] = [
    {id: 'general', label: 'General', description: 'Application behaviour and sessions'},
    {id: 'downloads', label: 'Downloads', description: 'Storage, naming, processing and verification'},
    {id: 'automation', label: 'Automation', description: 'Scheduler and episode monitoring'},
    {id: 'dailywire', label: 'DailyWire', description: 'Account and integration details'},
    {id: 'advanced', label: 'Advanced', description: 'Encryption files and configuration details'},
]

const NUMBER_FIELD_CONSTRAINTS: Partial<Record<SettingsFieldPath, NumberFieldConstraint>> = {
    'loginSession.ttlSeconds': {label: 'Session lifetime', min: 60},
    'movieMetadata.requestTimeoutSeconds': {label: 'TMDB request timeout', min: 1},
    'movieMetadata.maxRetries': {label: 'TMDB retry attempts', min: 0, max: 5},
    'dwTimeout.minFastRequestMs': {label: 'Minimum fast-request delay', min: 0},
    'dwTimeout.maxFastRequests': {label: 'Fast requests before slowdown', min: 1},
    'dwTimeout.minSlowRequestMs': {label: 'Minimum slow-request delay', min: 0},
    'scheduler.maxWorkers': {label: 'Maximum workers', min: 1},
    'scheduler.defaultMaxRetries': {label: 'Default retries', min: 0},
    'scheduler.retryBackoffSeconds': {label: 'Retry backoff', min: 0},
    'episodeStatusTiming.publishedCountdownAfterMinutes': {label: 'Countdown publication threshold', min: 0},
    'episodeStatusTiming.publishedFinalAfterMinutes': {label: 'Final publication threshold', min: 0},
    'downloadSettings.maxConcurrentDownloads': {label: 'Concurrent downloads', min: 1},
    'downloadSettings.maxDownloadAttempts': {label: 'Maximum download attempts', min: 1},
    'downloadSettings.downloadTimeoutSeconds': {label: 'Download timeout', min: 1},
}

const CRON_FIELD_PATHS = new Set<SettingsFieldPath>([
    'newEpisodeSchedule.findEpisodesCron',
    'newEpisodeSchedule.monitorEpisodeCron',
    'newEpisodeSchedule.checkNoShowTodayCron',
    'downloadSettings.verifyDownloadsCron',
    'fileWatcher.scanCron',
])

function cloneSettings(values: SettingsValues): SettingsValues {
    return structuredClone(values)
}

function valueAtPath(values: SettingsValues, path: SettingsFieldPath): unknown {
    let current: unknown = values
    for (const segment of path.split('.')) {
        if (current === null || typeof current !== 'object') return undefined
        current = (current as Record<string, unknown>)[segment]
    }
    return current
}

function setValueAtPath(values: SettingsValues, path: SettingsFieldPath, value: number): void {
    const segments = path.split('.')
    let current = values as unknown as Record<string, unknown>

    for (const segment of segments.slice(0, -1)) {
        current = current[segment] as Record<string, unknown>
    }
    current[segments[segments.length - 1]] = value
}

function hasFiveCronFields(value: string): boolean {
    return value.trim().split(/\s+/).filter(Boolean).length === 5
}

export default function SettingsPage() {
    const settingsQuery = useSettings()
    const saveSettings = useSaveSettings()
    const [activeTab, setActiveTab] = useState<SettingsTab>('general')
    const [draft, setDraft] = useState<SettingsValues | null>(null)
    const [baseline, setBaseline] = useState<SettingsValues | null>(null)
    const [hasSavedChanges, setHasSavedChanges] = useState(false)

    useEffect(() => {
        if (!settingsQuery.data) return
        setDraft(cloneSettings(settingsQuery.data.values))
        setBaseline(cloneSettings(settingsQuery.data.values))
    }, [settingsQuery.data])

    const updateDraft = useCallback((mutator: (next: SettingsValues) => void) => {
        setHasSavedChanges(false)
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

        const valuesToSave = cloneSettings(draft)
        for (const path of dirtyFields) {
            const numberConstraint = NUMBER_FIELD_CONSTRAINTS[path]
            if (numberConstraint) {
                const value = valueAtPath(valuesToSave, path)
                if (typeof value !== 'number' || !Number.isFinite(value)) {
                    toast.error(`Enter a number for ${numberConstraint.label} before saving.`)
                    return
                }

                let normalizedValue = value
                if (numberConstraint.min !== undefined) {
                    normalizedValue = Math.max(numberConstraint.min, normalizedValue)
                }
                if (numberConstraint.max !== undefined) {
                    normalizedValue = Math.min(numberConstraint.max, normalizedValue)
                }
                if (normalizedValue !== value) {
                    setValueAtPath(valuesToSave, path, normalizedValue)
                }
            }

            if (CRON_FIELD_PATHS.has(path)) {
                const cronValue = valueAtPath(valuesToSave, path)
                if (typeof cronValue !== 'string' || !hasFiveCronFields(cronValue)) {
                    toast.error('Cron schedules must contain five fields before saving.')
                    return
                }
            }
        }

        try {
            await saveSettings.mutateAsync({values: valuesToSave, changedFields: dirtyFields})
            setHasSavedChanges(true)
            toast.success('Settings saved to config.yml')
        } catch (error: any) {
            toast.error(error?.message || 'Failed to save settings')
        }
    }

    const discardChanges = () => {
        setHasSavedChanges(false)
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

                {isDirty || hasSavedChanges ? (
                    <div className={`settings-actions${isDirty ? ' is-dirty' : ' is-saved'}`}>
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
                ) : null}
            </div>
        </section>
    )
}
