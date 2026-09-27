import {useEffect, useState} from 'react'
import {Controller, type UseFormReturn, useWatch} from 'react-hook-form'
import Select from 'react-select'
import {z} from 'zod'

const RootPreviewSchema = z.object({
    path: z.string().nullable(),
    reason: z.string().nullable(),
    showTitle: z.string().nullable(),
    systemEnabled: z.boolean(),
})
type RootPreview = z.infer<typeof RootPreviewSchema>

export default function ShowAssetsField({form, sourceId}: {
    form: UseFormReturn<any>
    sourceId: string | null
}) {
    const {control, formState: {errors}} = form
    const outputTemplate = useWatch({control, name: 'outputTemplate'}) as string | undefined
    const localMediaProfileId = useWatch({control, name: 'id'}) as number | undefined
    const [preview, setPreview] = useState<RootPreview | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState('')

    useEffect(() => {
        setPreview(null)
        setError('')
        if (!outputTemplate) {
            setLoading(false)
            return
        }
        const controller = new AbortController()
        setLoading(true)
        const timer = window.setTimeout(async () => {
            try {
                const response = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/template/show-root`, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    signal: controller.signal,
                    body: JSON.stringify({outputTemplate, sourceId, localMediaProfileId: localMediaProfileId ?? null}),
                })
                const payload = await response.json()
                if (controller.signal.aborted) return
                if (!response.ok) {
                    const detail = payload?.detail
                    setError(typeof detail === 'string' ? detail : detail?.[0]?.msg ?? 'The show root could not be resolved.')
                    return
                }
                setPreview(RootPreviewSchema.parse(payload))
            } catch {
                if (!controller.signal.aborted) setError('The show-root preview is temporarily unavailable.')
            } finally {
                if (!controller.signal.aborted) setLoading(false)
            }
        }, 300)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [localMediaProfileId, outputTemplate, sourceId])

    const options = [
        {value: 'system', label: preview ? `System (${preview.systemEnabled ? 'enabled' : 'disabled'})` : 'System'},
        {value: 'enabled', label: 'Enabled'},
        {value: 'disabled', label: 'Disabled'},
    ]
    const fieldError = errors.downloadShowAssets

    return (
        <div className="form-row">
            <label htmlFor="mp-show-assets">Download show assets</label>
            <Controller
                control={control}
                name="downloadShowAssets"
                render={({field}) => (
                    <Select
                        inputId="mp-show-assets"
                        ref={field.ref}
                        name={field.name}
                        classNamePrefix="select"
                        options={options}
                        value={options.find(({value}) => value === (field.value == null ? 'system' : field.value ? 'enabled' : 'disabled'))}
                        onChange={(option) => field.onChange(option?.value === 'enabled' ? true : option?.value === 'disabled' ? false : null)}
                        onBlur={field.onBlur}
                        isClearable={false}
                        aria-invalid={!!fieldError}
                        aria-describedby={`mp-show-assets-help${fieldError ? ' mp-show-assets-error' : ''}`}
                    />
                )}
            />
            {fieldError && <div id="mp-show-assets-error" className="error" role="alert">{String(fieldError.message)}</div>}
            <div id="mp-show-assets-help" className="help">
                <p>
                    Save available poster, background and square artwork in the shared show folder.
                    System inherits Settings / Downloads. Episode thumbnails are controlled separately.
                    Existing custom artwork is preserved.
                </p>
                <div role="status" aria-live="polite">
                    {loading ? 'Resolving show root...' : error || (preview?.path ? (
                        <>
                            Resolved show root{preview.showTitle ? ` for ${preview.showTitle}` : ''}:<br/>
                            <code style={{overflowWrap: 'anywhere'}}>{preview.path}</code>
                        </>
                    ) : preview?.reason ?? 'Select an episode and enter an output template to preview the shared show root.')}
                </div>
                <p>
                    Uses the selected example episode's actual show metadata and the current template,
                    including unsaved changes. Ambiguous or shared library folders are skipped.
                </p>
            </div>
        </div>
    )
}
