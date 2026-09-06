import {type FormEvent, useCallback, useEffect, useRef, useState} from 'react'
import {useNavigate, useParams} from 'react-router-dom'
import LocalMediaProfileForm from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useForm} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {toast} from 'react-hot-toast'
import {LocalMediaProfileUpdateIn, LocalMediaProfileUpdateOut, LocalMediaProfileUpdateSchema} from '../../types/schemas/local_media_profile'
import {WithRoot} from '../../types/form'
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {LocalMediaProfileTypeReg} from '../../types/local_media_profile'
import {
    clearLocalMediaProfileDraft,
    editLocalMediaProfileDraftKey,
    loadLocalMediaProfileDraft,
    saveLocalMediaProfileDraft,
} from '../../components/LocalMediaProfile/localMediaProfileDraft'

export default function EditLocalMediaProfilePage() {
    const navigate = useNavigate()
    const {slug} = useParams<{ slug: string }>()
    const qc = useQueryClient()
    const initializedSlug = useRef<string | undefined>(undefined)
    const renameDecisionRef = useRef<boolean | null>(null)
    const [draftReady, setDraftReady] = useState(false)
    const [renameTemplateConfirm, setRenameTemplateConfirm] = useState(false)

    // Fetch the latest profile by slug
    const {data: profile, isLoading, error} = useQuery<LocalMediaProfileUpdateIn | undefined>({
        queryKey: ['localMediaProfile', slug],
        enabled: !!slug,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${slug}`, { signal, credentials: 'include' })
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<LocalMediaProfileUpdateIn>
        },
    })

    // Initialize form unconditionally to keep hooks order consistent
    const form = useForm<WithRoot<LocalMediaProfileUpdateIn>>({
        resolver: zodResolver(LocalMediaProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
        defaultValues: profile,
    })

    // Restore a versioned browser draft once the canonical profile type and
    // values have loaded. The slug keeps drafts isolated per profile.
    useEffect(() => {
        if (!profile || !slug || initializedSlug.current === slug) return
        const draftKey = editLocalMediaProfileDraftKey(slug)
        const draft = loadLocalMediaProfileDraft<LocalMediaProfileUpdateIn>(draftKey)
        const values = draft?.mode === profile.type
            ? {...profile, ...draft.values, type: profile.type, id: profile.id, slug: profile.slug}
            : profile
        form.reset(values as WithRoot<LocalMediaProfileUpdateIn>)
        initializedSlug.current = slug
        setDraftReady(true)
    }, [profile, slug, form])

    useEffect(() => {
        if (!draftReady || !profile || !slug) return
        const draftKey = editLocalMediaProfileDraftKey(slug)
        const subscription = form.watch((values) => {
            saveLocalMediaProfileDraft<LocalMediaProfileUpdateIn>(draftKey, {
                mode: profile.type,
                values: values as Partial<LocalMediaProfileUpdateIn>,
            })
        })
        return () => subscription.unsubscribe()
    }, [draftReady, form, profile, slug])

    const onCancel = useCallback(() => {
        if (slug) clearLocalMediaProfileDraft(editLocalMediaProfileDraftKey(slug))
        navigate('/local-media-profiles')
    }, [navigate, slug])

    if (isLoading) {
        return (
            <section className="view" aria-labelledby="edit-media-profile-title">
                <div className="view-header">
                    <h1 id="edit-media-profile-title">Edit media profile</h1>
                </div>
                <p>Loading…</p>
            </section>
        )
    }

    if (!slug || !profile || error) {
        return (
            <section className="view" aria-labelledby="edit-media-profile-title">
                <div className="view-header">
                    <h1 id="edit-media-profile-title">Edit media profile</h1>
                </div>
                <p>Profile not found.</p>
                <div className="actions" style={{marginTop: 12}}>
                    <button type="button" className="btn" onClick={onCancel}>Back</button>
                </div>
            </section>
        )
    }

    const submitFn = async (data: LocalMediaProfileUpdateOut): Promise<Response> => {
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${data.slug}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(data),
            })
            if (!response.ok) renameDecisionRef.current = null
            return response
        } catch (error) {
            renameDecisionRef.current = null
            throw error
        }
    }

    const onSuccess = async () => {
        if (renameDecisionRef.current) {
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/local-media-profiles/${slug}/rename-files`,
                    {method: 'POST', credentials: 'include'},
                )
                if (!response.ok) {
                    throw new Error(`File Rename could not be started (HTTP ${response.status})`)
                }
            } catch (error) {
                toast.error(
                    error instanceof Error
                        ? `Profile saved, but ${error.message}`
                        : 'Profile saved, but File Rename could not be started.',
                )
            }
        }

        renameDecisionRef.current = null
        await qc.invalidateQueries({queryKey: ['localMediaProfiles']})
        await qc.invalidateQueries({queryKey: ['localMediaProfile', slug]})
        clearLocalMediaProfileDraft(editLocalMediaProfileDraftKey(slug))
        navigate('/local-media-profiles')
    }

    const onUpdate = buildLocalMediaProfileOnSubmit(form, submitFn, {
        onSuccess,
        mode: 'update',
    })

    const onFormSubmit = (event: FormEvent<HTMLFormElement>) => {
        const outputTemplateChanged = (
            profile.type === 'show'
            && form.getValues('outputTemplate') !== profile.outputTemplate
        )
        if (outputTemplateChanged && renameDecisionRef.current === null) {
            void form.handleSubmit(() => setRenameTemplateConfirm(true))(event)
            return
        }
        void onUpdate(event)
    }

    const continueTemplateSave = (renameFiles: boolean) => {
        renameDecisionRef.current = renameFiles
        setRenameTemplateConfirm(false)
        void onUpdate()
    }

    const {formState: {isSubmitting}} = form

    return (
        <section className="view" aria-labelledby="edit-media-profile-title">
            <div className="view-header">
                <h1 id="edit-media-profile-title">Edit local media profile</h1>
            </div>

            <form className="form" onSubmit={onFormSubmit} noValidate>
                <div className="form-row">
                    <label>Profile type</label>
                    <div style={{padding: '6px 0'}}>{LocalMediaProfileTypeReg.getLabelLoose(profile.type)}</div>
                </div>

                <LocalMediaProfileForm form={form} mode={profile.type}/>

                <div className="actions">
                    <button type="button" className="btn" onClick={onCancel}>Cancel</button>
                    <input type="submit" className="btn btn-primary" value="Save changes" disabled={isSubmitting}/>
                </div>
            </form>

            {renameTemplateConfirm && (
                <div
                    className="modal-overlay"
                    role="presentation"
                    onClick={() => {
                        if (!isSubmitting) setRenameTemplateConfirm(false)
                    }}
                >
                    <div
                        className="modal"
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="rename-template-title"
                        aria-describedby="rename-template-desc"
                        onClick={(event) => event.stopPropagation()}
                    >
                        <div className="modal-header">
                            <h2 id="rename-template-title" className="modal-title">Rename existing files?</h2>
                        </div>
                        <p id="rename-template-desc" className="modal-text">
                            The output template changed. WireLoft can rename every existing episode file that uses this Local Media Profile so its path matches the new template.
                        </p>
                        <p className="modal-text">
                            You can also save the new template without moving existing files and run File Rename later from a show's Actions menu.
                        </p>
                        <div className="modal-actions">
                            <button
                                type="button"
                                className="btn"
                                disabled={isSubmitting}
                                onClick={() => setRenameTemplateConfirm(false)}
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                className="btn"
                                disabled={isSubmitting}
                                onClick={() => continueTemplateSave(false)}
                            >
                                Save without renaming
                            </button>
                            <button
                                type="button"
                                className="btn btn-primary"
                                disabled={isSubmitting}
                                onClick={() => continueTemplateSave(true)}
                            >
                                Save and rename files
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </section>
    )
}