import {useEffect, useMemo, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import toast from 'react-hot-toast'

import {faIcon} from '../../icons/faIcon'
import {
    destinationPayload,
    notificationQueryKeys,
    previewDestination,
    sendJson,
    testChannel,
    testDestination,
    useNotificationServices,
} from '../../lib/notifications'
import {
    ChannelFormSchema,
    type ChannelFormValues,
    type ChannelTestRead,
    type NotificationChannelRead,
    type NotificationServiceRead,
    type ServiceFieldRead,
} from '../../types/schemas/notifications'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {getZodDefaults} from '../../utils/defaultZod'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import ServiceTile from './ServiceTile'

type Props = {
    /** The channel being edited, or null to add a new one. */
    channel: NotificationChannelRead | null
    onDismiss: () => void
}

type Preview = {maskedUrl: string | null; hint: string | null}

type FieldValue = string | number | boolean | string[]

/** Form values hold what the user typed; list fields are split into arrays only when talking to the API. */
function toApiValues(service: NotificationServiceRead | undefined, values: Record<string, FieldValue>) {
    const kinds = new Map((service?.fields ?? []).map((field) => [field.key, field.kind]))
    return Object.fromEntries(Object.entries(values).map(([key, value]) => [
        key,
        kinds.get(key) === 'list' && typeof value === 'string'
            ? value.split(',').map((item) => item.trim()).filter(Boolean)
            : value,
    ]))
}

function ServiceField({
    field,
    value,
    onChange,
}: {
    field: ServiceFieldRead
    value: FieldValue | undefined
    onChange: (value: FieldValue | undefined) => void
}) {
    const id = `notif-field-${field.key}`
    const text = value === undefined ? '' : String(value)
    const label = (
        <label htmlFor={id}>
            {field.label}
            {field.required ? <span aria-hidden="true"> *</span> : null}
        </label>
    )

    if (field.kind === 'select') {
        return (
            <div className="form-row">
                {label}
                <select id={id} className="input" value={text} onChange={(event) => onChange(event.target.value || undefined)}>
                    {!field.required || !field.default ? <option value="">{field.default ? `Default (${field.default})` : 'Not set'}</option> : null}
                    {field.choices.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
                </select>
            </div>
        )
    }
    if (field.kind === 'boolean') {
        const current = value === undefined ? '' : value ? 'yes' : 'no'
        return (
            <div className="form-row">
                {label}
                <select
                    id={id}
                    className="input"
                    value={current}
                    onChange={(event) => onChange(event.target.value === '' ? undefined : event.target.value === 'yes')}
                >
                    <option value="">Default{field.default ? ` (${field.default})` : ''}</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                </select>
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
                value={text}
                onChange={(event) => onChange(event.target.value === '' ? undefined : event.target.value)}
            />
        </div>
    )
}

export default function ChannelDialog({channel, onDismiss}: Props) {
    const queryClient = useQueryClient()
    const editing = channel !== null
    const servicesQuery = useNotificationServices(true)
    const services = servicesQuery.data ?? []

    const form = useForm<ChannelFormValues>({
        resolver: zodResolver(ChannelFormSchema),
        defaultValues: {
            ...getZodDefaults(ChannelFormSchema),
            name: channel?.name ?? '',
            service: channel?.service ?? '',
            changeDestination: !editing,
        },
        mode: 'onBlur',
        shouldFocusError: true,
    })
    const {register, setValue, watch, formState: {errors, isSubmitting}} = form
    const mode = watch('mode') ?? 'fields'
    const serviceKey = watch('service') ?? ''
    const values = (watch('values') ?? {}) as Record<string, FieldValue>
    const url = watch('url') ?? ''
    const changeDestination = watch('changeDestination') ?? true

    const [search, setSearch] = useState('')
    const [preview, setPreview] = useState<Preview>({maskedUrl: null, hint: null})
    const [testing, setTesting] = useState(false)
    const [testResult, setTestResult] = useState<ChannelTestRead | null>(null)

    const service = services.find(({key}) => key === serviceKey)
    const visibleServices = useMemo(() => {
        const needle = search.trim().toLowerCase()
        return needle ? services.filter(({name}) => name.toLowerCase().includes(needle)) : services
    }, [search, services])

    const apiForm = (): ChannelFormValues => ({
        ...form.getValues(),
        values: toApiValues(service, form.getValues('values') as Record<string, FieldValue> ?? {}),
    })

    // Show the masked URL (or why there is none yet) while the user fills in the fields.
    const previewKey = JSON.stringify([mode, serviceKey, values, url, changeDestination])
    useEffect(() => {
        setTestResult(null)
        const ready = mode === 'url' ? url.includes('://') : serviceKey !== ''
        if (!changeDestination || !ready) {
            setPreview({maskedUrl: null, hint: null})
            return
        }
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            try {
                const result = await previewDestination(apiForm(), controller.signal)
                setPreview({maskedUrl: result.maskedUrl, hint: null})
            } catch (cause) {
                if (controller.signal.aborted) return
                setPreview({maskedUrl: null, hint: cause instanceof Error ? cause.message : null})
            }
        }, 400)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [previewKey, service])

    const chooseService = (next: NotificationServiceRead) => {
        const schema = next.fields.find(({key}) => key === 'schema')
        setValue('service', next.key, {shouldDirty: true, shouldValidate: true})
        setValue('values', schema?.default ? {schema: schema.default} : {}, {shouldDirty: true})
        setSearch('')
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
            setTestResult(editing && !changeDestination
                ? await testChannel(channel.id)
                : await testDestination(apiForm()))
        } catch (cause) {
            setTestResult({
                delivered: false,
                error: cause instanceof Error ? cause.message : 'Could not send the test notification',
                elapsedMs: 0,
            })
        } finally {
            setTesting(false)
        }
    }

    const submit = buildServerAwareSubmit<ChannelFormValues>(
        form,
        async (data) => {
            const destination = destinationPayload({
                ...data,
                values: toApiValues(service, (data.values ?? {}) as Record<string, FieldValue>),
            })
            return editing
                ? sendJson(`/channels/${channel.id}`, 'PATCH', {name: data.name, destination})
                : sendJson('/channels', 'POST', {name: data.name, destination})
        },
        {
            successStatuses: [200, 201],
            fallbackField: 'destination',
            genericMessage: 'Could not save the channel',
            onSuccess: async () => {
                await queryClient.invalidateQueries({queryKey: notificationQueryKeys.channels})
                toast.success(editing ? 'Channel saved' : 'Channel added')
                onDismiss()
            },
        },
    )

    const rootError = errors.root?.message
    const basicFields = service?.fields.filter(({advanced}) => !advanced) ?? []
    const advancedFields = service?.fields.filter(({advanced}) => advanced) ?? []

    return (
        <ConfirmDialog
            open
            className="notif-dialog"
            title={editing ? `Edit ${channel.name}` : 'Add channel'}
            icon={faIcon('fas', 'bell')}
            onDismiss={onDismiss}
            dismissOnOverlayClick={false}
            confirmButton={{
                label: editing ? 'Save channel' : 'Add channel',
                icon: faIcon('fas', isSubmitting ? 'spinner' : 'check'),
                iconSpin: isSubmitting,
                disabled: isSubmitting,
                onClick: () => submit(),
            }}
        >
            <form className="notif-form" onSubmit={submit} noValidate>
                {rootError ? <div className="form-error-card" role="alert">{rootError}</div> : null}

                <div className="form-row">
                    <label htmlFor="notif-channel-name">Name</label>
                    <input
                        id="notif-channel-name"
                        className="input"
                        placeholder="e.g. Phone alerts"
                        aria-invalid={errors.name ? 'true' : undefined}
                        {...register('name')}
                    />
                    {errors.name ? <span className="error">{errors.name.message}</span> : null}
                </div>

                {editing ? (
                    <div className="form-row">
                        <span>Destination</span>
                        <div className="notif-masked">
                            <ServiceTile name={channel.serviceName} size="sm"/>
                            <code>{channel.maskedUrl}</code>
                        </div>
                        <label className="notif-check">
                            <input type="checkbox" {...register('changeDestination')}/>
                            <span>Replace the destination (credentials are never shown again, so enter them fresh)</span>
                        </label>
                    </div>
                ) : null}

                {changeDestination ? (
                    <>
                        <div className="notif-seg" role="tablist" aria-label="How to describe the destination">
                            {(['fields', 'url'] as const).map((option) => (
                                <button
                                    key={option}
                                    type="button"
                                    role="tab"
                                    aria-selected={mode === option}
                                    className={`notif-seg__item${mode === option ? ' is-active' : ''}`}
                                    onClick={() => setValue('mode', option, {shouldDirty: true})}
                                >
                                    {option === 'fields' ? 'Pick a service' : 'Custom Apprise URL'}
                                </button>
                            ))}
                        </div>

                        {mode === 'fields' ? (
                            <>
                                {service ? (
                                    <div className="notif-masked">
                                        <ServiceTile name={service.name} size="sm"/>
                                        <strong>{service.name}</strong>
                                        {service.setupUrl ? (
                                            <a href={service.setupUrl} target="_blank" rel="noreferrer">Setup guide</a>
                                        ) : null}
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={() => setValue('service', '', {shouldDirty: true})}
                                        >
                                            Change
                                        </button>
                                    </div>
                                ) : (
                                    <div className="form-row">
                                        <label htmlFor="notif-service-search">Service</label>
                                        <div className="notif-search">
                                            <FontAwesomeIcon icon={faIcon('fas', 'magnifying-glass')} aria-hidden="true"/>
                                            <input
                                                id="notif-service-search"
                                                className="input"
                                                type="search"
                                                placeholder={`Search ${services.length || ''} services`}
                                                value={search}
                                                onChange={(event) => setSearch(event.target.value)}
                                            />
                                        </div>
                                        {servicesQuery.isError ? <span className="error">Could not load services.</span> : null}
                                        <div className="notif-grid" role="listbox" aria-label="Notification services">
                                            {visibleServices.map((option) => (
                                                <button
                                                    key={option.key}
                                                    type="button"
                                                    role="option"
                                                    aria-selected={false}
                                                    className="notif-grid__item"
                                                    onClick={() => chooseService(option)}
                                                >
                                                    <ServiceTile name={option.name} size="sm"/>
                                                    <span>{option.name}</span>
                                                </button>
                                            ))}
                                            {servicesQuery.isSuccess && visibleServices.length === 0 ? (
                                                <span className="help">No matching service. Try a custom Apprise URL.</span>
                                            ) : null}
                                        </div>
                                        {errors.service ? <span className="error">{errors.service.message}</span> : null}
                                    </div>
                                )}

                                {service ? (
                                    <>
                                        {basicFields.map((field) => (
                                            <ServiceField
                                                key={field.key}
                                                field={field}
                                                value={values[field.key]}
                                                onChange={(value) => setFieldValue(field.key, value)}
                                            />
                                        ))}
                                        {advancedFields.length > 0 ? (
                                            <details className="notif-advanced">
                                                <summary>Advanced options</summary>
                                                <div className="notif-advanced__body">
                                                    {advancedFields.map((field) => (
                                                        <ServiceField
                                                            key={field.key}
                                                            field={field}
                                                            value={values[field.key]}
                                                            onChange={(value) => setFieldValue(field.key, value)}
                                                        />
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
                                <input
                                    id="notif-url"
                                    className="input"
                                    type="password"
                                    autoComplete="off"
                                    placeholder="e.g. ntfys://my-topic"
                                    aria-invalid={errors.url ? 'true' : undefined}
                                    {...register('url')}
                                />
                                {errors.url ? <span className="error">{errors.url.message}</span> : null}
                                <span className="help">
                                    Any <a href="https://appriseit.com/services/" target="_blank" rel="noreferrer">Apprise URL</a> works.
                                </span>
                            </div>
                        )}

                        <div className="notif-preview" aria-live="polite">
                            <span>Destination</span>
                            {preview.maskedUrl ? <code>{preview.maskedUrl}</code> : (
                                <span className="help">{preview.hint ?? 'Fill in the details to see the destination.'}</span>
                            )}
                        </div>
                        {errors.destination ? <span className="error">{errors.destination.message}</span> : null}
                    </>
                ) : null}

                <div className="notif-test">
                    <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={testing || (changeDestination && !preview.maskedUrl)}
                        onClick={() => void runTest()}
                    >
                        <FontAwesomeIcon
                            icon={faIcon('fas', testing ? 'spinner' : 'paper-plane')}
                            spin={testing}
                            aria-hidden="true"
                        />
                        Send test notification
                    </button>
                    {testResult ? (
                        <span
                            role="status"
                            className={testResult.delivered ? 'notif-test__ok' : 'error'}
                        >
                            {testResult.delivered
                                ? `Delivered in ${testResult.elapsedMs} ms`
                                : testResult.error ?? 'Delivery failed'}
                        </span>
                    ) : null}
                </div>
                {!editing ? (
                    <p className="help">New channels receive failure alerts. Adjust this under Routing.</p>
                ) : null}
                <button type="submit" hidden/>
            </form>
        </ConfirmDialog>
    )
}
