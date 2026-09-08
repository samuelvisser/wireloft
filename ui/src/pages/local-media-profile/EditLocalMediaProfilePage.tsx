import {type FormEvent, useCallback, useEffect, useRef, useState} from 'react'
import {useNavigate, useParams} from 'react-router-dom'
import LocalMediaProfileForm from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useForm, UseFormReturn} from 'react-hook-form'
import {zodResolver} from '@hookform/resolvers/zod'
import {toast} from 'react-hot-toast'
import {
    LocalMediaProfileRead,
    LocalMediaProfileUpdateIn,
    LocalMediaProfileUpdateOut,
} from '../../types/schemas/local_media_profile'
import {
    MovieLocalMediaProfileUpdateIn,
    MovieLocalMediaProfileUpdateSchema,
} from '../../types/schemas/movie_local_media_profile'
import {
    ShowLocalMediaProfileUpdateIn,
    ShowLocalMediaProfileUpdateSchema,
} from '../../types/schemas/show_local_media_profile'
import {WithRoot} from '../../types/form'
import {buildLocalMediaProfileOnSubmit} from '../../components/LocalMediaProfile/LocalMediaProfileForm'
import {LocalMediaProfileTypeReg} from '../../types/local_media_profile'
import {useStartOperation} from '../../lib/operations'
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
    const startOperation = useStartOperation()
    const initializedSlug = useRef<string | undefined>(undefined)
    const renameDecisionRef = useRef<boolean | null>(null)
    const [draftReady, setDraftReady] = useState(false)
    const [renameTemplateConfirm, setRenameTemplateConfirm] = useState(false)

    const {data: profile, isLoading, error} = useQuery<LocalMediaProfileRead | undefined>({
        queryKey: ['localMediaProfile', slug],
        enabled: !!slug,
        refetchOnMount: 'always',
        queryFn: async ({signal}) => {
            const res = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${slug}`, {signal, credentials: 'include'})
            if (!res.ok) throw new Error(`Failed to load profile (${res.status})`)
            return await res.json() as Promise<LocalMediaProfileRead>
        },
    })

    const formShow = useForm<WithRoot<ShowLocalMediaProfileUpdateIn>>({
        resolver: zodResolver(ShowLocalMediaProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
    })

    const formMovie = useForm<WithRoot<MovieLocalMediaProfileUpdateIn>>({
        resolver: zodResolver(MovieLocalMediaProfileUpdateSchema),
        mode: 'onBlur',
        shouldFocusError: true,
    })

    const form = (profile?.type === 'movie' ? formMovie : formShow) as UseFormReturn<any>

    useEffect(() => {
        if (!profile || !slug || initializedSlug.current === slug) return

        const canonical = profile.type === 'movie'
            ? MovieLocalMediaProfileUpdateSchema.parse(profile)
            : ShowLocalMediaProfileUpdateSchema.parse(profile)
        const draftKey = editLocalMediaProfileDraftKey(slug)
        const draft = loadLocalMediaProfileDraft<LocalMediaProfileUpdateIn>(draftKey)
        const values = draft?.mode === profile.type
            ? {
                ...canonical,
                ...draft.values,
                type: canonical.type,
                id: canonical.id,
                slug: canonical.slug,
            }
            : canonical

        form.reset(values)
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

    const submitFn = async (data: LocalMediaProfileUpdateOut) => {
        try {
            const response = await fetch(`${(window as any).appConfig.API_URL}/local-media-profiles/${data.slug}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(data),
            })
            if (!response.ok) renameDecisionRef.current = null
            return response
        } catch (submitError) {
            renameDecisionRef.current = null
            throw submitError
        }
    }

    const onSuccess = async () => {
        if (renameDecisionRef.current) {
            try {
                const base = (window as any).appConfig?.API_URL || '/api'
                await startOperation(
                    `${base}/local-media-profiles/${encodeURIComponent(slug)}/rename-files`,
                    {method: 'POST'},
                )
            } catch (renameError) {
                const detail = renameError instanceof Error ? `: ${renameError.message}` : ''
                toast.error(`Profile saved, but File Rename could not be started${detail}`)
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

            <ConfirmDialog
                open={renameTemplateConfirm}
                title="Rename existing files?"
                onDismiss={() => {
                    if (!isSubmitting) setRenameTemplateConfirm(false)
                }}
                dismissOnOverlayClick={!isSubmitting}
                cancelButton={{
                    label: 'Save without renaming',
                    disabled: isSubmitting,
                    onClick: () => continueTemplateSave(false),
                }}
                confirmButton={{
                    label: isSubmitting ? 'Saving…' : 'Save and rename files',
                    disabled: isSubmitting,
                    onClick: () => continueTemplateSave(true),
                }}
            >
                <p>
                    The output template changed. WireLoft can rename every existing episode file that uses this Local Media Profile so its path matches the new template.
                </p>
                <p>
                    Close this dialog to keep editing, or save without moving existing files and run File Rename later from a show's Actions menu.
                </p>
            </ConfirmDialog>
        </section>
    )
}
