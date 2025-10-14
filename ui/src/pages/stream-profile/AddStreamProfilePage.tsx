import {useCallback, useState} from 'react'
import {Controller, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {useNavigate} from 'react-router-dom'
import {useShows} from '../../lib/queries'
import {buildShowSelectRegistry} from '../../types/show'
import {SelectRegistry} from '../../utils/selectRegistry'
import Select from 'react-select'
import {getZodDefaults} from '../../utils/defaultZod'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import RssStreamProfileForm, {StreamProfileMode} from '../../components/StreamProfile/RssStreamProfileForm'
import SegmentedOptions, {toSegmentedOptions} from '../../components/SegmentedOptions/SegmentedOptions'
import {RssStreamProfileCreateIn, RssStreamProfileCreateOut, RssStreamProfileCreateSchema} from '../../types/schemas/rss_stream_profile'
import {useQueryClient} from '@tanstack/react-query'
import Switch from 'react-switch'

export default function AddStreamProfilePage() {
    const navigate = useNavigate()
    const qc = useQueryClient()

    const [mode, setMode] = useState<StreamProfileMode>('rss')

    const {data: shows} = useShows()
    const showReg: SelectRegistry = buildShowSelectRegistry(shows)

    const form = useForm<RssStreamProfileCreateIn>({
        resolver: zodResolver(RssStreamProfileCreateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: getZodDefaults(RssStreamProfileCreateSchema),
    })
    const {formState: {errors, isSubmitting}} = form

    const onCancel = useCallback(() => navigate('/stream-profiles'), [navigate])

    const submitFn = async (data: RssStreamProfileCreateOut) => {
        return fetch(`${(window as any).appConfig.API_URL}/rss-stream-profiles`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify(data),
        })
    }

    const onSuccess = async () => {
        await qc.invalidateQueries({queryKey: ['rssStreamProfiles']})
        await qc.invalidateQueries({queryKey: ['streamProfilesView']})
        navigate('/stream-profiles')
    }

    const onSubmit = buildServerAwareSubmit(form as any, submitFn, {
        onSuccess,
        successStatuses: [201],
    })

    return (
        <section className="view" aria-labelledby="add-stream-profile-title">
            <div className="view-header">
                <h1 id="add-stream-profile-title">Add stream profile</h1>
            </div>

            <form className="form" onSubmit={onSubmit} noValidate>
                {errors.root && (
                    <div className="form-error-card" role="alert" aria-live="polite">
                        {String(errors.root.message)}
                    </div>
                )}

                {/* Mode selection (only RSS for now) */}
                <div className="form-row">
                    <label>Profile type</label>
                    <SegmentedOptions
                        name="stream-profile-mode"
                        value={mode}
                        onChange={(v) => setMode(v as StreamProfileMode)}
                        options={toSegmentedOptions([['rss', 'RSS']])}
                    />
                </div>

                {/* Show select */}
                <div className="form-row">
                    <label htmlFor="show-id">Show</label>
                    <Controller
                        control={form.control}
                        name={"showId"}
                        render={({field}) => (
                            <Select
                                inputId="show-id"
                                classNamePrefix="select"
                                options={showReg.options}
                                value={showReg.options.find(o => Number(o.value) === field.value) ?? null}
                                onChange={(opt) => field.onChange((opt as any) ? Number((opt as any).value) : undefined)}
                                onBlur={field.onBlur}
                                isDisabled={showReg.options.length === 0}
                                placeholder={showReg.options.length === 0 ? 'No shows found' : undefined}
                                isClearable
                                aria-invalid={!!errors.showId}
                                aria-describedby={errors.showId ? 'show-errors' : undefined}
                            />
                        )}
                    />
                    {errors.showId && (
                        <div id="show-errors" className="error" role="alert" aria-live="polite">
                            {String(errors.showId.message)}
                        </div>
                    )}
                </div>

                {/* Enable profile */}
                <div className="form-row">
                    <label htmlFor="enable-profile">Enable streaming</label>
                    <Controller
                        control={form.control}
                        name="enableProfile"
                        render={({field}) => (
                            <Switch
                                id="enable-profile"
                                checked={!!field.value}
                                onChange={(checked) => field.onChange(checked)}
                                onColor="#0ea5e9"
                                offColor="#d1d5db"
                                uncheckedIcon={false}
                                checkedIcon={false}
                                aria-invalid={!!errors.enableProfile}
                            />
                        )}
                    />
                </div>

                {/* Variant-specific fields (RSS) */}
                <RssStreamProfileForm form={form as any} />

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Create profile" disabled={isSubmitting} />
                </div>
            </form>
        </section>
    )
}
