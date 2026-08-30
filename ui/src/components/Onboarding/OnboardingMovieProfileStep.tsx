import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {zodResolver} from '@hookform/resolvers/zod'
import {useForm} from 'react-hook-form'
import {useQueryClient} from '@tanstack/react-query'

import LocalMediaProfileCard from '../LocalMediaProfile/LocalMediaProfileCard'
import LocalMediaProfileForm from '../LocalMediaProfile/LocalMediaProfileForm'
import {useLocalMediaProfiles} from '../../lib/queries'
import {
    LocalMediaProfileCreateIn,
    LocalMediaProfileRead,
    MovieLocalMediaProfileCreateSchema,
} from '../../types/schemas/local_media_profile'
import {getErrorMessageFromResponse} from '../../utils/helpers'


type Props = {
    movieTitle: string
    onBack: () => void
    onContinue: (profile: LocalMediaProfileRead) => void
}

const NEW_PROFILE_DEFAULTS: LocalMediaProfileCreateIn = {
    type: 'movie',
    name: 'My Movies',
    outputTemplate: '/downloads/movies/{movie_title}/{title}.ext',
    preferredFormat: 'format_1080p',
    appendMediaTypeToFilename: true,
}

export default function OnboardingMovieProfileStep({movieTitle, onBack, onContinue}: Props) {
    const profilesQuery = useLocalMediaProfiles()
    const queryClient = useQueryClient()
    const initialized = useRef(false)
    const [selectedSlug, setSelectedSlug] = useState<string | null>(null)

    const form = useForm<LocalMediaProfileCreateIn>({
        resolver: zodResolver(MovieLocalMediaProfileCreateSchema) as any,
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: NEW_PROFILE_DEFAULTS,
    })

    const movieProfiles = useMemo(
        () => profilesQuery.data?.filter((profile) => profile.type === 'movie') ?? [],
        [profilesQuery.data],
    )

    const selectProfile = useCallback((profile: LocalMediaProfileRead) => {
        setSelectedSlug(profile.slug)
        form.reset({
            type: 'movie',
            name: profile.name,
            outputTemplate: profile.outputTemplate,
            preferredFormat: profile.preferredFormat as LocalMediaProfileCreateIn['preferredFormat'],
            appendMediaTypeToFilename: profile.appendMediaTypeToFilename,
        })
    }, [form])

    useEffect(() => {
        if (initialized.current || profilesQuery.isPending || profilesQuery.isError) return
        initialized.current = true
        const starter = movieProfiles.find((profile) => profile.slug === 'wireloft-movies') ?? movieProfiles[0]
        if (starter) selectProfile(starter)
    }, [movieProfiles, profilesQuery.isError, profilesQuery.isPending, selectProfile])

    const createNew = () => {
        setSelectedSlug(null)
        form.reset(NEW_PROFILE_DEFAULTS)
    }

    const submit = form.handleSubmit(async (input) => {
        form.clearErrors('root')
        try {
            const data = MovieLocalMediaProfileCreateSchema.parse(input)
            const base = (window as any).appConfig?.API_URL || '/api'
            const isUpdating = selectedSlug !== null
            const response = await fetch(
                isUpdating
                    ? `${base}/local-media-profiles/${encodeURIComponent(selectedSlug)}`
                    : `${base}/local-media-profiles`,
                {
                    method: isUpdating ? 'PATCH' : 'POST',
                    credentials: 'include',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                },
            )

            if (!response.ok) {
                const {error} = await getErrorMessageFromResponse(response)
                form.setError('root', {
                    type: 'server',
                    message: error || 'Could not save the Movie Local Media Profile.',
                })
                return
            }

            // The API response is already the canonical Local Media Profile read model.
            // Do not run it back through the stricter client-side schema here: that can
            // reject otherwise valid server timestamps and incorrectly report a network
            // failure after the profile has actually been saved.
            const profile = await response.json() as LocalMediaProfileRead
            await queryClient.invalidateQueries({queryKey: ['localMediaProfiles']})
            onContinue(profile)
        } catch {
            form.setError('root', {
                type: 'server',
                message: 'Could not save the Movie Local Media Profile. Check the connection and try again.',
            })
        }
    })

    return (
        <section className="onboarding-profile-step" aria-labelledby="onboarding-movie-profile-title">
            <div className="onboarding-section-heading">
                <span className="onboarding-eyebrow">Before opening {movieTitle}</span>
                <h1 id="onboarding-movie-profile-title">Choose where movie files will be stored</h1>
                <p>
                    Select a profile to edit its values, or create another one. The profile saved here will already be
                    selected when the movie page opens.
                </p>
            </div>

            <form className="form form-fluid onboarding-profile-form" onSubmit={submit} noValidate>
                <div className="form-row">
                    <div className="onboarding-profile-list-heading">
                        <label>Movie Local Media Profile</label>
                        <button className="btn" type="button" onClick={createNew}>Create a new profile</button>
                    </div>
                    <div className="card-grid" role="list">
                        {profilesQuery.isPending ? (
                            <div role="listitem" className="card">Loading profiles…</div>
                        ) : profilesQuery.isError ? (
                            <div role="listitem" className="card">Could not load profiles: {profilesQuery.error.message}</div>
                        ) : movieProfiles.length === 0 ? (
                            <div role="listitem" className="card selected">Create your first Movie Local Media Profile below.</div>
                        ) : (
                            movieProfiles.map((profile) => (
                                <LocalMediaProfileCard
                                    key={profile.slug}
                                    profile={profile}
                                    selected={selectedSlug === profile.slug}
                                    onClick={() => selectProfile(profile)}
                                />
                            ))
                        )}
                    </div>
                </div>

                <hr className="divider" aria-hidden="true"/>
                <div className="divider-label" aria-hidden="true">
                    {selectedSlug ? 'Edit selected profile' : 'Create a new profile'}
                </div>

                <LocalMediaProfileForm form={form} mode="movie"/>

                <div className="actions">
                    <button className="btn" type="button" onClick={onBack}>Back</button>
                    <button
                        className="btn btn-primary"
                        type="submit"
                        disabled={form.formState.isSubmitting || profilesQuery.isPending}
                    >
                        {form.formState.isSubmitting ? 'Saving…' : 'Save and open movie'}
                    </button>
                </div>
            </form>
        </section>
    )
}
