import {zodResolver} from '@hookform/resolvers/zod'
import {useQueryClient} from '@tanstack/react-query'
import {useCallback, useEffect, useMemo, useState} from 'react'
import {type FieldErrors, type FieldPath, useForm} from 'react-hook-form'
import toast from 'react-hot-toast'

import AdvancedSettingsTab from '../components/Settings/AdvancedSettingsTab'
import AutomationSettingsTab from '../components/Settings/AutomationSettingsTab'
import DailyWireSettingsTab from '../components/Settings/DailyWireSettingsTab'
import DownloadsSettingsTab from '../components/Settings/DownloadsSettingsTab'
import GeneralSettingsTab from '../components/Settings/GeneralSettingsTab'
import {SettingsLoading} from '../components/Settings/SettingsControls'
import {saveSettingsRequest, useSettings} from '../lib/settings'
import {
    SETTINGS_FIELD_PATHS,
    SettingsFormSchema,
    type SettingsFieldPath,
    type SettingsRead,
    SettingsReadSchema,
    SettingsServerErrors,
    type SettingsValues,
} from '../types/schemas/settings'
import {buildServerAwareSubmit} from '../utils/buildServerAwareSubmit'
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

const SETTINGS_SERVER_FIELD_ALIASES: Record<string, string> = Object.fromEntries(
    SETTINGS_FIELD_PATHS.map((path) => [`values.${path}`, path]),
)

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

function errorAtPath(errors: FieldErrors<SettingsValues>, path: SettingsFieldPath): string | undefined {
    let current: unknown = errors
    for (const segment of path.split('.')) {
        if (current === null || typeof current !== 'object') return undefined
        current = (current as Record<string, unknown>)[segment]
    }

    if (current === null || typeof current !== 'object') return undefined
    const message = (current as {message?: unknown}).message
    return typeof message === 'string' ? message : undefined
}

export default function SettingsPage() {
    const settingsQuery = useSettings()
    const queryClient = useQueryClient()
    const [activeTab, setActiveTab] = useState<SettingsTab>('general')
    const [baseline, setBaseline] = useState<SettingsValues | null>(null)

    const form = useForm<SettingsValues>({
        resolver: zodResolver(SettingsFormSchema),
        mode: 'onSubmit',
        reValidateMode: 'onChange',
        shouldFocusError: true,
    })
    const {
        formState: {errors, isSubmitted, isSubmitting},
        getValues,
        reset,
        setValue,
        watch,
    } = form
    const draft = watch()

    useEffect(() => {
        if (!settingsQuery.data) return
        const values = cloneSettings(settingsQuery.data.values)
        reset(values)
        setBaseline(cloneSettings(values))
    }, [reset, settingsQuery.data])

    const updateDraft = useCallback((mutator: (next: SettingsValues) => void) => {
        const current = cloneSettings(getValues())
        const next = cloneSettings(current)
        mutator(next)

        for (const path of SETTINGS_FIELD_PATHS) {
            const currentValue = valueAtPath(current, path)
            const nextValue = valueAtPath(next, path)
            if (Object.is(currentValue, nextValue)) continue

            setValue(path as FieldPath<SettingsValues>, nextValue as never, {
                shouldDirty: true,
                shouldValidate: isSubmitted,
            })
        }
    }, [getValues, isSubmitted, setValue])

    const dirtyFields = useMemo<SettingsFieldPath[]>(() => {
        if (!baseline) return []
        return SETTINGS_FIELD_PATHS.filter(
            (path) => !Object.is(valueAtPath(draft, path), valueAtPath(baseline, path)),
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

    const errorFor = useCallback((path: SettingsFieldPath): string | undefined => {
        return errorAtPath(errors, path)
    }, [errors])

    const submit = buildServerAwareSubmit<SettingsValues, SettingsValues, SettingsRead>(
        form,
        (values) => saveSettingsRequest({values, changedFields: dirtyFields}),
        {
            successStatuses: [200],
            parseSuccess: async (response) => SettingsReadSchema.parse(await response.json()),
            fieldAlias: {...SETTINGS_SERVER_FIELD_ALIASES},
            mapMessage: SettingsServerErrors,
            rootOnFieldErrors: true,
            onSuccess: (settings) => {
                queryClient.setQueryData(['settings'], settings)
                toast.success('Settings saved to config.yml')
            },
        },
    )

    const discardChanges = () => {
        if (baseline) reset(cloneSettings(baseline))
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

    if (settingsQuery.isLoading || !baseline || !settingsQuery.data) {
        return (
            <section className="view settings-page" aria-labelledby="settings-title">
                <SettingsLoading />
            </section>
        )
    }

    const updatedAt = settingsQuery.data.updatedAt
    const tabProps = {draft, updateDraft, environmentVariableFor, errorFor}

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
                {errors.root?.message ? (
                    <div className="form-error-card" role="alert" aria-live="polite">
                        {String(errors.root.message)}
                    </div>
                ) : null}

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

                {isDirty ? (
                    <div className="settings-actions is-dirty">
                        <div>
                            <strong>Unsaved changes</strong>
                            <span>
                                {dirtyFields.length} {dirtyFields.length === 1 ? 'setting' : 'settings'} will be written to config.yml.
                            </span>
                        </div>
                        <div className="settings-actions__buttons">
                            <button
                                className="btn"
                                type="button"
                                disabled={isSubmitting}
                                onClick={discardChanges}
                            >
                                Discard
                            </button>
                            <button
                                className="btn btn-primary"
                                type="button"
                                disabled={isSubmitting}
                                onClick={() => void submit()}
                            >
                                {isSubmitting ? 'Saving…' : 'Save settings'}
                            </button>
                        </div>
                    </div>
                ) : null}
            </div>
        </section>
    )
}
