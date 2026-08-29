import {useEffect, useRef} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DailywireShowCard from './DailywireShowCard'
import LocalMediaProfileForm from '../LocalMediaProfile/LocalMediaProfileForm'
import {useLocalMediaProfiles} from '../../lib/queries'
import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {
    LocalMediaProfileCreateUnionIn, LocalMediaProfileUpsertIn, LocalMediaProfileUpsertOut, LocalMediaProfileUpsertSchema
} from "../../types/schemas/show_as_bundle";
import LocalMediaProfileCard from '../LocalMediaProfile/LocalMediaProfileCard'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'

// Local upsert type and schema for the form
type Props = {
    value: Partial<LocalMediaProfileUpsertIn>
    onChange: (v: Partial<LocalMediaProfileUpsertIn>) => void
    onSubmit: (v: LocalMediaProfileUpsertOut) => void;
    onBack: () => void
    onContinue: () => void
    onCancel: () => void
    showSlug?: string
}

export default function LocalMediaProfileStep({value, onChange, onSubmit: onSubmitParent, onBack, onContinue, onCancel, showSlug}: Props) {
    const profilesQuery = useLocalMediaProfiles()
    const profiles: LocalMediaProfileRead[] | undefined = profilesQuery.data?.filter((profile) => profile.type === 'show')
    const profilesError = profilesQuery.isError ? ((profilesQuery.error)?.message ?? 'Failed to load media profiles') : null

    // React Hook Form setup
    const form = useForm<LocalMediaProfileUpsertIn>({
        resolver: zodResolver(LocalMediaProfileUpsertSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: { op: 'create_new', type: 'show', ...(value) },
    })
    const {watch, setValue, formState: {isSubmitting}} = form

    // Subscribe to ALL changes
    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values); // push up on every change
        });
        return () => subscription.unsubscribe();
    }, [watch, onChange]);

    // Snapshot previous values when switching to an existing profile, so we can restore on deselect
    const snapshotRef = useRef<Pick<LocalMediaProfileCreateUnionIn, 'name' | 'outputTemplate' | 'preferredFormat'> | null>(null)

    const watchedOp = watch('op')
    const watchedSlug = watch('slug')

    // Selection handler for profile cards
    const handleSelect = (p: LocalMediaProfileRead) => {
        const selected = watchedOp === 'update_by_slug' && watchedSlug === p.slug
        if (selected) {
            // Deselect: switch back to create_new and restore snapshot if any
            setValue('op', 'create_new', {shouldValidate: true, shouldDirty: true})
            setValue('type', 'show', {shouldValidate: true, shouldDirty: true})
            setValue('id', undefined as any, {shouldValidate: true, shouldDirty: true})
            const snap = snapshotRef.current
            setValue('name', snap?.name ?? '', {shouldValidate: true})
            setValue('outputTemplate', snap?.outputTemplate ?? '', {shouldValidate: true})
            setValue('preferredFormat', (snap?.preferredFormat ?? 'format_1080p') as any, {shouldValidate: true})
            snapshotRef.current = null
        } else {
            // Selecting a profile
            if (!(watchedOp === 'update_by_slug')) {
                // Save current values before replacing
                snapshotRef.current = {
                    name: watch('name'),
                    outputTemplate: watch('outputTemplate'),
                    preferredFormat: watch('preferredFormat'),
                }
            }
            setValue('op', 'update_by_slug', {shouldValidate: true, shouldDirty: true})
            setValue('type', 'show', {shouldValidate: true, shouldDirty: true})
            setValue('slug', p.slug, {shouldValidate: true, shouldDirty: true})
            setValue('id', p.id as any, {shouldValidate: true, shouldDirty: true})
            setValue('name', p.name, {shouldValidate: true})
            setValue('outputTemplate', p.outputTemplate, {shouldValidate: true})
            setValue('preferredFormat', p.preferredFormat as any, {shouldValidate: true})
        }
    }

    const onSubmit = buildServerAwareSubmit(form, async (dataIn: LocalMediaProfileUpsertIn) => {
        const dataOut = LocalMediaProfileUpsertSchema.parse(dataIn)
        onSubmitParent(dataOut)
        onContinue()
    }, {
        fallbackField: 'name',
        rootClientValidationMessage: 'Please fix the highlighted fields.',
    })

    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                <form className="form form-fluid" onSubmit={onSubmit} noValidate>
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
                                        <LocalMediaProfileCard
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
                    <LocalMediaProfileForm form={form} mode="show"/>

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
