import {useEffect, useMemo, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import {Controller, useForm} from 'react-hook-form'
import toast from 'react-hot-toast'

import {faIcon} from '../../icons/faIcon'
import {
    destinationPayload,
    notificationKeys,
    notificationsRequest,
    previewDestination,
    testDestination,
    testUnsavedDestination,
    useAppriseServices,
    useScripts,
    useWebhookExample,
} from '../../lib/notifications'
import {
    DestinationFormSchema,
    type AppriseServiceRead,
    type DestinationFormValues,
    type DestinationKind,
    type DestinationRead,
    type ServiceFieldRead,
    type TestRead,
} from '../../types/schemas/notifications'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {getZodDefaults} from '../../utils/defaultZod'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import SimpleSelect from '../common/SimpleSelect'
import ServiceTile from './ServiceTile'
import {DEFAULT_CHOICE, KIND_LABELS, MethodReg, RefreshScopeReg, fieldRegistry, scriptRegistry} from './registries'

type Props = {
    /** The destination being edited, or null to add a new one. */
    destination: DestinationRead | null
    onDismiss: () => void
}

type FieldValue = string | number | boolean | string[]

const KINDS: {kind: DestinationKind; help: string}[] = [
    {kind: 'apprise', help: 'Discord, Telegram, email, ntfy and 100 more, through Apprise'},
    {kind: 'jellyfin', help: 'Refresh the library when files change'},
    {kind: 'emby', help: 'Refresh the library when files change'},
    {kind: 'plex', help: 'Refresh the library when files change'},
    {kind: 'webhook', help: 'Send the details as JSON to an address'},
    {kind: 'script', help: 'Run your own script from the scripts folder'},
]

/** Form values hold what was typed; list fields become arrays only when talking to the API. */
function toApiValues(service: AppriseServiceRead | undefined, values: Record<string, FieldValue>) {
    const kinds = new Map((service?.fields ?? []).map((field) => [field.key, field.kind]))
    return Object.fromEntries(Object.entries(values).map(([key, value]) => [
        key,
        kinds.get(key) === 'list' && typeof value === 'string'
            ? value.split(',').map((item) => item.trim()).filter(Boolean)
            : value,
    ]))
}

function AppriseField({field, value, onChange}: {
    field: ServiceFieldRead
    value: FieldValue | undefined
    onChange: (value: FieldValue | undefined) => void
}) {
    const id = `notif-field-${field.key}`
    const registry = useMemo(() => (field.kind === 'select' || field.kind === 'boolean') ? fieldRegistry(field) : null, [field])
    const label = (
        <label htmlFor={id}>
            {field.label}
            {field.required ? <span aria-hidden="true"> *</span> : null}
        </label>
    )
    if (registry) {
        const current = value === undefined ? DEFAULT_CHOICE : field.kind === 'boolean' ? (value ? 'yes' : 'no') : String(value)
        return (
            <div className="form-row">
                {label}
                <SimpleSelect
                    inputId={id}
                    registry={registry}
                    value={current}
                    onChange={(next) => onChange(
                        next === DEFAULT_CHOICE ? undefined : field.kind === 'boolean' ? next === 'yes' : next,
                    )}
                />
            </div>
        )
    }
    return (
        <div className="form-row">
            {label}
            <input
                id={id}
                className="input"
                type={field.kind === 'secret' ? 'password' : field.kind === 'number' ? 'number' : 'text'}
                autoComplete="off"
                placeholder={field.kind === 'list' ? 'Separate several with commas' : field.default ?? undefined}
                value={value === undefined ? '' : String(value)}
                onChange={(event) => onChange(event.target.value === '' ? undefined : event.target.value)}
            />
        </div>
    )
}

export default function DestinationDialog({destination, onDismiss}: Props) {
    const queryClient = useQueryClient()
    const editing = destination !== null
    const form = useForm<DestinationFormValues>({
        resolver: zodResolver(DestinationFormSchema),
        defaultValues: {
            ...getZodDefaults(DestinationFormSchema),
            ...(destination ? {
                name: destination.name,
                kind: destination.kind,
                service: destination.service,
                changeSettings: false,
                ...settingsOf(destination),
            } : {}),
        },
        mode: 'onBlur',
    })
    const {register, setValue, watch, control, formState: {errors, isSubmitting}} = form
    const kind = watch('kind') ?? 'apprise'
    const mode = watch('mode') ?? 'fields'
    const serviceKey = watch('service') ?? ''
    const values = (watch('values') ?? {}) as Record<string, FieldValue>
    const changeSettings = watch('changeSettings') ?? true

    const servicesQuery = useAppriseServices(kind === 'apprise')
    const scripts = useScripts(kind === 'script')
    const example = useWebhookExample(kind === 'webhook')
    const services = servicesQuery.data ?? []
    const service = services.find(({key}) => key === serviceKey)

    const [search, setSearch] = useState('')
    const [preview, setPreview] = useState<{masked: string | null; hint: string | null}>({masked: null, hint: null})
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<TestRead | null>(null)

    const visibleServices = useMemo(() => {
        const needle = search.trim().toLowerCase()
        return needle ? services.filter(({name}) => name.toLowerCase().includes(needle)) : services
    }, [search, services])

    const apiForm = (): DestinationFormValues => ({
        ...form.getValues(),
        values: toApiValues(service, (form.getValues('values') ?? {}) as Record<string, FieldValue>),
    })

    // Show the destination as it will be listed (or why it cannot be yet) while it is filled in.
    const watched = watch()
    const previewKey = JSON.stringify([watched.kind, watched.mode, watched.service, watched.values, watched.url,
        watched.address, watched.apiKey, watched.webhookUrl, watched.method, watched.script, changeSettings])
    useEffect(() => {
        setTestResult(null)
        if (!changeSettings || !readyToCheck(apiForm())) {
            setPreview({masked: null, hint: null})
            return
        }
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            try {
                const result = await previewDestination(apiForm(), controller.signal)
                setPreview({masked: result.masked, hint: null})
            } catch (cause) {
                if (controller.signal.aborted) return
                setPreview({masked: null, hint: cause instanceof Error ? cause.message : null})
            }
        }, 400)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [previewKey, service])

    const chooseService = (next: AppriseServiceRead) => {
        const schema = next.fields.find(({key}) => key === 'schema')
        setValue('service', next.key, {shouldDirty: true, shouldValidate: true})
        setValue('values', schema?.default ? {schema: schema.default} : {}, {shouldDirty: true})
        if (!form.getValues('name')) setValue('name', next.name)
        setSearch('')
    }

    const chooseKind = (next: DestinationKind) => {
        const name = form.getValues('name') ?? ''
        // Replace a name WireLoft filled in itself, never one that was typed.
        const filledIn = !name || Object.values(KIND_LABELS).includes(name) || services.some((option) => option.name === name)
        setValue('kind', next, {shouldDirty: true})
        if (filledIn) setValue('name', next === 'apprise' ? '' : KIND_LABELS[next])
    }

    const setFieldValue = (key: string, value: FieldValue | undefined) => {
        const next = {...values}
        if (value === undefined) delete next[key]
        else next[key] = value
        setValue('values', next, {shouldDirty: true})
    }

    const runTest = async () => {
        setTesting(true)
        setTestResult(null)
        try {
            setTestResult(editing && !changeSettings ? await testDestination(destination.id) : await testUnsavedDestination(apiForm()))
            if (editing) void queryClient.invalidateQueries({queryKey: notificationKeys.destinations})
        } catch (cause) {
            setTestResult({delivered: false, error: cause instanceof Error ? cause.message : 'The test failed', elapsedMs: 0})
        } finally {
            setTesting(false)
        }
    }

    const submit = buildServerAwareSubmit<DestinationFormValues>(
        form,
        async (data) => {
            const settings = data.changeSettings === false ? undefined : destinationPayload({
                ...data,
                values: toApiValues(service, (data.values ?? {}) as Record<string, FieldValue>),
            })
            return editing
                ? notificationsRequest(`/notifications/destinations/${destination.id}`, 'PATCH', {name: data.name, destination: settings})
                : notificationsRequest('/notifications/destinations', 'POST', {name: data.name, destination: settings})
        },
        {
            successStatuses: [200, 201],
            fallbackField: 'destination',
            genericMessage: 'Could not save it',
            onSuccess: async () => {
                await queryClient.invalidateQueries({queryKey: notificationKeys.destinations})
                toast.success(editing ? 'Saved' : `${KIND_LABELS[kind]} added`)
                onDismiss()
            },
        },
    )

    const rootError = errors.root?.message
    const basicFields = service?.fields.filter(({advanced}) => !advanced) ?? []
    const advancedFields = service?.fields.filter(({advanced}) => advanced) ?? []
    const mediaServer = kind === 'jellyfin' || kind === 'emby' || kind === 'plex'
    const testLabel = kind === 'apprise' ? 'Send a test message'
        : mediaServer ? 'Test the connection'
            : kind === 'webhook' ? 'Send a test call' : 'Run on the newest download'

    return (
        <ConfirmDialog
            open
            className="notif-dialog"
            title={editing ? `Edit ${destination.name}` : 'Add a destination or service'}
            icon={faIcon('fass', 'paper-plane')}
            onDismiss={onDismiss}
            dismissOnOverlayClick={false}
            confirmButton={{
                label: editing ? 'Save' : 'Add',
                icon: faIcon('fass', isSubmitting ? 'spinner' : 'check'),
                iconSpin: isSubmitting,
                disabled: isSubmitting,
                onClick: () => submit(),
            }}
        >
            <form className="notif-form" onSubmit={submit} noValidate>
                {rootError ? <div className="form-error-card" role="alert">{rootError}</div> : null}

                {!editing ? (
                    <div className="form-row">
                        <span>What should WireLoft do?</span>
                        <div className="notif-kinds" role="radiogroup" aria-label="Kind">
                            {KINDS.map((option) => (
                                <button
                                    key={option.kind}
                                    type="button"
                                    role="radio"
                                    aria-checked={kind === option.kind}
                                    className={`notif-kind${kind === option.kind ? ' is-active' : ''}`}
                                    onClick={() => chooseKind(option.kind)}
                                >
                                    <strong><ServiceTile name={KIND_LABELS[option.kind]} size="sm"/>{option.kind === 'apprise' ? 'Send a message' : KIND_LABELS[option.kind]}</strong>
                                    <small>{option.help}</small>
                                </button>
                            ))}
                        </div>
                    </div>
                ) : null}

                <div className="form-row">
                    <label htmlFor="notif-destination-name">Name</label>
                    <input id="notif-destination-name" className="input" placeholder="e.g. Phone alerts"
                           aria-invalid={errors.name ? 'true' : undefined} {...register('name')}/>
                    {errors.name ? <span className="error">{errors.name.message}</span> : null}
                </div>

                {editing ? (
                    <div className="form-row">
                        <span>Settings</span>
                        <div className="notif-masked">
                            <ServiceTile name={destination.serviceName} size="sm"/>
                            <code>{destination.masked}</code>
                        </div>
                        <label className="notif-check">
                            <input type="checkbox" {...register('changeSettings')}/>
                            <span>Enter the settings again (passwords, keys and tokens are never shown again)</span>
                        </label>
                    </div>
                ) : null}

                {changeSettings && kind === 'apprise' ? (
                    <>
                        <div className="notif-seg" role="tablist" aria-label="How to describe the destination">
                            {(['fields', 'url'] as const).map((option) => (
                                <button key={option} type="button" role="tab" aria-selected={mode === option}
                                        className={`notif-seg__item${mode === option ? ' is-active' : ''}`}
                                        onClick={() => setValue('mode', option, {shouldDirty: true})}>
                                    {option === 'fields' ? 'Pick a service' : 'Apprise URL'}
                                </button>
                            ))}
                        </div>
                        {mode === 'fields' ? (
                            <>
                                {service ? (
                                    <div className="notif-masked">
                                        <ServiceTile name={service.name} size="sm"/>
                                        <strong>{service.name}</strong>
                                        {service.setupUrl ? <a href={service.setupUrl} target="_blank" rel="noreferrer">Setup guide</a> : null}
                                        <button type="button" className="btn btn-secondary" onClick={() => setValue('service', '', {shouldDirty: true})}>
                                            Change
                                        </button>
                                    </div>
                                ) : (
                                    <div className="form-row">
                                        <label htmlFor="notif-service-search">Service</label>
                                        <div className="notif-search">
                                            <FontAwesomeIcon icon={faIcon('fass', 'magnifying-glass')} aria-hidden="true"/>
                                            <input id="notif-service-search" className="input" type="search"
                                                   placeholder={`Search ${services.length || ''} services`}
                                                   value={search} onChange={(event) => setSearch(event.target.value)}/>
                                        </div>
                                        {servicesQuery.isError ? <span className="error">Could not load the services.</span> : null}
                                        <div className="notif-grid" role="listbox" aria-label="Services">
                                            {visibleServices.map((option) => (
                                                <button key={option.key} type="button" role="option" aria-selected={false}
                                                        className="notif-grid__item" onClick={() => chooseService(option)}>
                                                    <ServiceTile name={option.name} size="sm"/>
                                                    <span>{option.name}</span>
                                                </button>
                                            ))}
                                            {servicesQuery.isSuccess && visibleServices.length === 0 ? (
                                                <span className="help">No matching service. Try an Apprise URL.</span>
                                            ) : null}
                                        </div>
                                        {errors.service ? <span className="error">{errors.service.message}</span> : null}
                                    </div>
                                )}
                                {service ? (
                                    <>
                                        {basicFields.map((field) => (
                                            <AppriseField key={field.key} field={field} value={values[field.key]}
                                                          onChange={(value) => setFieldValue(field.key, value)}/>
                                        ))}
                                        {advancedFields.length > 0 ? (
                                            <details className="notif-advanced">
                                                <summary>Advanced options</summary>
                                                <div className="notif-advanced__body">
                                                    {advancedFields.map((field) => (
                                                        <AppriseField key={field.key} field={field} value={values[field.key]}
                                                                      onChange={(value) => setFieldValue(field.key, value)}/>
                                                    ))}
                                                </div>
                                            </details>
                                        ) : null}
                                    </>
                                ) : null}
                            </>
                        ) : (
                            <div className="form-row">
                                <label htmlFor="notif-url">Apprise URL</label>
                                <input id="notif-url" className="input" type="password" autoComplete="off"
                                       placeholder="e.g. ntfys://my-topic" aria-invalid={errors.url ? 'true' : undefined}
                                       {...register('url')}/>
                                {errors.url ? <span className="error">{errors.url.message}</span> : null}
                                <span className="help">
                                    Any <a href="https://appriseit.com/services/" target="_blank" rel="noreferrer">Apprise URL</a> works.
                                </span>
                            </div>
                        )}
                    </>
                ) : null}

                {changeSettings && mediaServer ? (
                    <>
                        <div className="form-row">
                            <label htmlFor="notif-address">Address</label>
                            <input id="notif-address" className="input"
                                   placeholder={kind === 'plex' ? 'http://plex:32400' : kind === 'emby' ? 'http://emby:8096' : 'http://jellyfin:8096'}
                                   aria-invalid={errors.address ? 'true' : undefined} {...register('address')}/>
                            {errors.address ? <span className="error">{errors.address.message}</span> : null}
                        </div>
                        <div className="form-row">
                            <label htmlFor="notif-api-key">{kind === 'plex' ? 'Plex token' : 'API key'}</label>
                            <input id="notif-api-key" className="input" type="password" autoComplete="off"
                                   aria-invalid={errors.apiKey ? 'true' : undefined} {...register('apiKey')}/>
                            {errors.apiKey ? <span className="error">{errors.apiKey.message}</span> : null}
                            <span className="help">
                                {kind === 'plex' ? (
                                    <a href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/" target="_blank" rel="noreferrer">
                                        How to find your Plex token
                                    </a>
                                ) : `Create one in ${KIND_LABELS[kind]} under Dashboard › API Keys.`}
                            </span>
                        </div>
                        <div className="form-row">
                            <label htmlFor="notif-scope">What to refresh</label>
                            <Controller control={control} name="scope" render={({field}) => (
                                <SimpleSelect inputId="notif-scope" registry={RefreshScopeReg} value={field.value} onChange={field.onChange}/>
                            )}/>
                        </div>
                        <details className="notif-advanced">
                            <summary>Path mapping</summary>
                            <div className="notif-advanced__body">
                                <span className="help">
                                    Only needed when {KIND_LABELS[kind]} sees the files under another path, for example
                                    /downloads in WireLoft and /media in {KIND_LABELS[kind]}.
                                </span>
                                <div className="form-row">
                                    <label htmlFor="notif-path-from">Path in WireLoft</label>
                                    <input id="notif-path-from" className="input" placeholder="/downloads" {...register('pathFrom')}/>
                                </div>
                                <div className="form-row">
                                    <label htmlFor="notif-path-to">Path in {KIND_LABELS[kind]}</label>
                                    <input id="notif-path-to" className="input" placeholder="/media" {...register('pathTo')}/>
                                </div>
                            </div>
                        </details>
                    </>
                ) : null}

                {changeSettings && kind === 'webhook' ? (
                    <>
                        <div className="notif-inline">
                            <div className="form-row notif-grow">
                                <label htmlFor="notif-webhook-url">Address</label>
                                <input id="notif-webhook-url" className="input" placeholder="https://example.com/hooks/wireloft"
                                       aria-invalid={errors.webhookUrl ? 'true' : undefined} {...register('webhookUrl')}/>
                                {errors.webhookUrl ? <span className="error">{errors.webhookUrl.message}</span> : null}
                            </div>
                            <div className="form-row">
                                <label htmlFor="notif-method">Method</label>
                                <Controller control={control} name="method" render={({field}) => (
                                    <SimpleSelect inputId="notif-method" registry={MethodReg} value={field.value} onChange={field.onChange}/>
                                )}/>
                            </div>
                        </div>
                        <div className="notif-inline">
                            <div className="form-row notif-grow">
                                <label htmlFor="notif-secret-header">Secret header (optional)</label>
                                <input id="notif-secret-header" className="input" placeholder="X-Webhook-Secret" {...register('secretHeader')}/>
                            </div>
                            <div className="form-row notif-grow">
                                <label htmlFor="notif-secret-value">Its value</label>
                                <input id="notif-secret-value" className="input" type="password" autoComplete="off" {...register('secretValue')}/>
                            </div>
                        </div>
                        <div className="form-row">
                            <span>What it sends</span>
                            <pre className="notif-pre">{example.data ? JSON.stringify(example.data.payload, null, 2) : 'Loading…'}</pre>
                            <span className="help">A failed call is tried again three times over a few minutes.</span>
                        </div>
                    </>
                ) : null}

                {changeSettings && kind === 'script' ? (
                    <>
                        <div className="form-row">
                            <label htmlFor="notif-script">Script</label>
                            {scripts.data && scripts.data.scripts.length > 0 ? (
                                <Controller control={control} name="script" render={({field}) => (
                                    <SimpleSelect inputId="notif-script" registry={scriptRegistry(scripts.data.scripts)}
                                                  value={field.value} onChange={field.onChange} placeholder="Choose a script"/>
                                )}/>
                            ) : (
                                <span className="help">
                                    {scripts.data
                                        ? <>No scripts yet. Put an executable script in <code>{scripts.data.folder}</code> and open this again.</>
                                        : 'Loading…'}
                                </span>
                            )}
                            {errors.script ? <span className="error">{errors.script.message}</span> : null}
                        </div>
                        <div className="form-row">
                            <label htmlFor="notif-timeout">Time limit in seconds</label>
                            <input id="notif-timeout" className="input" type="number" min={1} max={3600}
                                   aria-invalid={errors.timeoutSeconds ? 'true' : undefined} {...register('timeoutSeconds')}/>
                            {errors.timeoutSeconds ? <span className="error">{errors.timeoutSeconds.message}</span> : null}
                        </div>
                        {scripts.data ? (
                            <div className="form-row">
                                <span>What it receives</span>
                                <div className="notif-vars">
                                    {scripts.data.variables.map((name) => <code key={name} className="notif-chip">{name}</code>)}
                                </div>
                                <span className="help">WireLoft only runs scripts from {scripts.data.folder} and never stores them. Its output goes to the log.</span>
                            </div>
                        ) : null}
                    </>
                ) : null}

                {changeSettings ? (
                    <div className="notif-preview" aria-live="polite">
                        <span>Shown as</span>
                        {preview.masked ? <code>{preview.masked}</code> : (
                            <span className="help">{preview.hint ?? 'Fill in the details to see it.'}</span>
                        )}
                    </div>
                ) : null}
                {errors.destination ? <span className="error">{errors.destination.message}</span> : null}

                <div className="notif-test">
                    <button type="button" className="btn btn-secondary" disabled={testing || (changeSettings && !preview.masked)}
                            onClick={() => void runTest()}>
                        <FontAwesomeIcon icon={faIcon('fass', testing ? 'spinner' : 'paper-plane')} spin={testing} aria-hidden="true"/>
                        {testLabel}
                    </button>
                    {testResult ? (
                        <span role="status" className={testResult.delivered ? 'notif-test__ok' : 'error'}>
                            {testResult.delivered ? `It worked (${testResult.elapsedMs} ms)` : testResult.error ?? 'It failed'}
                        </span>
                    ) : null}
                </div>
                {!editing ? <p className="help">Adding it changes no rules. Choose it in the rules you want.</p> : null}
                <button type="submit" hidden/>
            </form>
        </ConfirmDialog>
    )
}

/** Whether enough is filled in to ask the server what it makes of it. */
function readyToCheck(form: DestinationFormValues): boolean {
    switch (form.kind ?? 'apprise') {
        case 'apprise':
            return form.mode === 'url' ? (form.url ?? '').includes('://') : Boolean(form.service)
        case 'webhook':
            return /^https?:\/\/./.test(form.webhookUrl ?? '')
        case 'script':
            return Boolean(form.script)
        default:
            return /^https?:\/\/./.test(form.address ?? '') && Boolean(form.apiKey)
    }
}

/** The settings that are not secret, so editing starts from what is stored. */
function settingsOf(destination: DestinationRead): Partial<DestinationFormValues> {
    const settings = destination.settings
    const text = (key: string) => (typeof settings[key] === 'string' ? settings[key] as string : '')
    return {
        address: text('address'),
        scope: settings.scope === 'library' ? 'library' : 'folder',
        pathFrom: text('path_from'),
        pathTo: text('path_to'),
        webhookUrl: text('url'),
        method: settings.method === 'PUT' ? 'PUT' : 'POST',
        secretHeader: text('secret_header'),
        script: text('script'),
        timeoutSeconds: typeof settings.timeout_seconds === 'number' ? settings.timeout_seconds : 60,
    }
}
