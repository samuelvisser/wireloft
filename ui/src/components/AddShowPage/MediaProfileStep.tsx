import {useEffect, useRef} from 'react'
import {SubmitHandler, useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DailywireShowCard from './DailywireShowCard'
import MediaProfileForm from '../MediaProfile/MediaProfileForm'
import {useMediaProfiles} from '../../lib/queries'
import {MediaProfileRead} from '../../types/schemas/media_profile'
import {
    MediaProfileCreateUnionIn, MediaProfileUpsertIn, MediaProfileUpsertOut, MediaProfileUpsertSchema
} from "../../types/schemas/show_with_profiles";
import MediaProfileCard from '../MediaProfile/MediaProfileCard'

// Local upsert type and schema for the form
type Props = {
    value: Partial<MediaProfileUpsertIn>
    onChange: (v: Partial<MediaProfileUpsertIn>) => void
    onSubmit: (v: MediaProfileUpsertOut) => void;
    onBack: () => void
    onContinue: () => void
    onCancel: () => void
    showSlug?: string
}

export default function MediaProfileStep({value, onChange, onSubmit: onSubmitParent, onBack, onContinue, onCancel, showSlug}: Props) {
    const profilesQuery = useMediaProfiles()
    const profiles: MediaProfileRead[] | undefined = profilesQuery.data
    const profilesError = profilesQuery.isError ? ((profilesQuery.error)?.message ?? 'Failed to load media profiles') : null

    // React Hook Form setup
    const form = useForm<MediaProfileUpsertIn>({
        resolver: zodResolver(MediaProfileUpsertSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: value,
    })
    const {handleSubmit, watch, setValue, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    // Snapshot previous values when switching to an existing profile, so we can restore on deselect
    const snapshotRef = useRef<Pick<MediaProfileCreateUnionIn, 'name' | 'outputTemplate' | 'preferredFormat' | 'downloadSeriesImages'> | null>(null)

    const watchedOp = watch('op')
    const watchedSlug = watch('slug')

    // Selection handler for profile cards
    const handleSelect = (p: MediaProfileRead) => {
        const selected = watchedOp === 'update_by_slug' && watchedSlug === p.slug
        if (selected) {
            // Deselect: switch back to create_new and restore snapshot if any
            setValue('op', 'create_new', {shouldValidate: true, shouldDirty: true})
            setValue('id', undefined as any, {shouldValidate: true, shouldDirty: true})
            const snap = snapshotRef.current
            setValue('name', snap?.name ?? '', {shouldValidate: true})
            setValue('outputTemplate', snap?.outputTemplate ?? '', {shouldValidate: true})
            setValue('preferredFormat', (snap?.preferredFormat ?? 'format_1080p') as any, {shouldValidate: true})
            setValue('downloadSeriesImages', snap?.downloadSeriesImages ?? true, {shouldValidate: true})
            snapshotRef.current = null
        } else {
            // Selecting a profile
            if (!(watchedOp === 'update_by_slug')) {
                // Save current values before replacing
                snapshotRef.current = {
                    name: watch('name'),
                    outputTemplate: watch('outputTemplate'),
                    preferredFormat: watch('preferredFormat'),
                    downloadSeriesImages: watch('downloadSeriesImages'),
                }
            }
            setValue('op', 'update_by_slug', {shouldValidate: true, shouldDirty: true})
            setValue('slug', p.slug, {shouldValidate: true, shouldDirty: true})
            setValue('id', p.id as any, {shouldValidate: true, shouldDirty: true})
            setValue('name', p.name, {shouldValidate: true})
            setValue('outputTemplate', p.outputTemplate, {shouldValidate: true})
            setValue('preferredFormat', p.preferredFormat as any, {shouldValidate: true})
            setValue('downloadSeriesImages', p.downloadSeriesImages, {shouldValidate: true})
        }
    }

    const onSubmit: SubmitHandler<MediaProfileUpsertIn> = (dataIn: MediaProfileUpsertIn) => {
        const dataOut = MediaProfileUpsertSchema.parse(dataIn)
        onSubmitParent(dataOut)
        onContinue()
    }

    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                <form className="form form-fluid" onSubmit={handleSubmit(onSubmit)} noValidate>
                    {/* Existing profiles list */}
                    <div className="form-row">
                        <label>Choose a media profile</label>
                        <div className="card-grid" role="list">
                            {profilesQuery.isPending ? (
                                <div role="listitem" className="card">Loading profiles...</div>
                            ) : !profiles || profiles.length === 0 ? (
                                <div role="listitem" className="card">{profilesError ?? 'No profiles found'}</div>
                            ) : (
                                profiles.map((p) => {
                                    const selected = watchedOp === 'update_by_slug' && watchedSlug === p.slug
                                    return (
                                        <MediaProfileCard
                                            key={p.slug}
                                            profile={p}
                                            selected={selected}
                                            onClick={() => handleSelect(p)}
                                        />
                                    )
                                })
                            )}
                        </div>
                    </div>

                    {/* Divider and label under it */}
                    <hr className="divider" aria-hidden="true"/>
                    <div className="divider-label"
                         aria-hidden="true">{watchedOp === 'update_by_slug' ? 'Update current profile' : 'Or create a new profile'}</div>

                    {/* New or update profile form (user-editable fields) */}
                    <MediaProfileForm form={form}/>

                    <div className="actions">
                        <button type="button" className="btn" onClick={onBack}>
                            Back
                        </button>
                        <input type="submit" className="btn btn-primary" value="Continue" disabled={isSubmitting}/>
                        <button type="button" className="btn" onClick={onCancel}>
                            Cancel
                        </button>
                    </div>
                </form>
            </div>

            {/* Sidebar with DailyWire show details */}
            {showSlug ? (
                <aside className="wizard-aside" aria-label="Selected show details">
                    <DailywireShowCard showSlug={showSlug}/>
                </aside>
            ) : null}
        </div>
    )
}
