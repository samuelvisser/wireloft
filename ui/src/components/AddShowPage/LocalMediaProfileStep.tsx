import {useEffect, useRef} from 'react'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import DailywireShowCard from './DailywireShowCard'
import LocalMediaProfileForm from '../LocalMediaProfile/LocalMediaProfileForm'
import {useLocalMediaProfiles} from '../../lib/queries'
import {ShowLocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {
    LocalMediaProfileCreateUnionIn,
    LocalMediaProfileCreateUnionSchema,
    LocalMediaProfileUpdateUnionSchema,
    LocalMediaProfileUpsertIn,
    LocalMediaProfileUpsertOut,
    LocalMediaProfileUpsertSchema,
} from '../../types/schemas/show_as_bundle'
import LocalMediaProfileCard from '../LocalMediaProfile/LocalMediaProfileCard'
import {buildServerAwareSubmit} from '../../utils/buildServerAwareSubmit'
import {getZodDefaults} from '../../utils/defaultZod'


type Props = {
    value: Partial<LocalMediaProfileUpsertIn>
    onChange: (v: Partial<LocalMediaProfileUpsertIn>) => void
    onSubmit: (v: LocalMediaProfileUpsertOut) => void
    onBack: () => void
    onContinue: () => void
    onCancel: () => void
    showSlug?: string
}

export default function LocalMediaProfileStep({value, onChange, onSubmit: onSubmitParent, onBack, onContinue, onCancel, showSlug}: Props) {
    const profilesQuery = useLocalMediaProfiles()
    const profiles: ShowLocalMediaProfileRead[] | undefined = profilesQuery.data?.filter(
        (profile): profile is ShowLocalMediaProfileRead => profile.type === 'show',
    )
    const profilesError = profilesQuery.isError ? ((profilesQuery.error)?.message ?? 'Failed to load media profiles') : null
    const createDefaults = getZodDefaults(LocalMediaProfileCreateUnionSchema)
    const updateDefaults = getZodDefaults(LocalMediaProfileUpdateUnionSchema)

    const form = useForm<LocalMediaProfileUpsertIn>({
        resolver: zodResolver(LocalMediaProfileUpsertSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: {...createDefaults, ...value},
    })
    const {watch, formState: {isSubmitting}} = form

    useEffect(() => {
        const subscription = watch((values) => {
            onChange(values)
        })
        return () => subscription.unsubscribe()
    }, [watch, onChange])

    const snapshotRef = useRef<Pick<
        LocalMediaProfileCreateUnionIn,
        'name' | 'showScope' | 'outputTemplate' | 'preferredFormat'
    > | null>(null)

    const watchedOp = watch('op')
    const watchedSlug = watch('slug')

    const handleSelect = (profile: ShowLocalMediaProfileRead) => {
        const selected = watchedOp === 'update_by_slug' && watchedSlug === profile.slug
        if (selected) {
            form.reset({
                ...createDefaults,
                ...(snapshotRef.current ?? {}),
            } as LocalMediaProfileUpsertIn)
            snapshotRef.current = null
            return
        }

        if (watchedOp !== 'update_by_slug') {
            snapshotRef.current = {
                name: watch('name'),
                showScope: watch('showScope'),
                outputTemplate: watch('outputTemplate'),
                preferredFormat: watch('preferredFormat'),
            }
        }

        form.reset({
            ...updateDefaults,
            id: profile.id,
            slug: profile.slug,
            name: profile.name,
            showScope: profile.showScope,
            outputTemplate: profile.outputTemplate,
            preferredFormat: profile.preferredFormat,
        } as LocalMediaProfileUpsertIn)
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
                    <div className="form-row">
                        <label>Choose a media profile</label>
                        <div className="card-grid" role="list">
                            {profilesQuery.isPending ? (
                                <div role="listitem" className="card">Loading profiles...</div>
                            ) : !profiles || profiles.length === 0 ? (
                                <div role="listitem" className="card">{profilesError ?? 'No profiles found'}</div>
                            ) : (
                                profiles.map((profile) => {
                                    const selected = watchedOp === 'update_by_slug' && watchedSlug === profile.slug
                                    return (
                                        <LocalMediaProfileCard
                                            key={profile.slug}
                                            profile={profile}
                                            selected={selected}
                                            onClick={() => handleSelect(profile)}
                                        />
                                    )
                                })
                            )}
                        </div>
                    </div>

                    <hr className="divider" aria-hidden="true"/>
                    <div className="divider-label" aria-hidden="true">
                        {watchedOp === 'update_by_slug' ? 'Update current profile' : 'Or create a new profile'}
                    </div>

                    <LocalMediaProfileForm form={form} mode="show"/>

                    <div className="actions">
                        <button type="button" className="btn" onClick={onBack}>Back</button>
                        <input type="submit" className="btn btn-primary" value="Continue" disabled={isSubmitting}/>
                        <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    </div>
                </form>
            </div>

            {showSlug ? (
                <aside className="wizard-aside" aria-label="Selected show details">
                    <DailywireShowCard showSlug={showSlug}/>
                </aside>
            ) : null}
        </div>
    )
}
