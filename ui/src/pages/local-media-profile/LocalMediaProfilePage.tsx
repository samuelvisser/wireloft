import {useState} from 'react'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import {useQueryClient} from '@tanstack/react-query'
import {useNavigate, useParams} from 'react-router-dom'
import toast from 'react-hot-toast'

import ActionConfirmDialogue from '../../components/ActionConfirmDialogue/ActionConfirmDialogue'
import ActionMenu from '../../components/ActionMenu/ActionMenu'
import ConfirmDialog from '../../components/ConfirmDialog/ConfirmDialog'
import {useActiveOperation} from '../../components/OperationNotifier/OperationNotifier'
import {useLocalMediaProfileView} from '../../lib/queries'
import {frontendOperationDefinitions} from '../../lib/operationDefinitions'
import {
    OperationControlError,
    type OperationControlAction,
    useControlOperation,
} from '../../lib/operations'
import {
    LocalMediaProfileTypeReg,
    PreferredFormatReg,
    ShowLocalMediaProfileScopeReg,
} from '../../types/local_media_profile'
import {formatBytes} from '../../utils/formatting'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import './LocalMediaProfilePage.css'

const OPERATION_WAITING_MESSAGE = 'Operation is waiting, it should resume soon.'

export default function LocalMediaProfilePage() {
    const {slug} = useParams<{slug: string}>()
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const controlOperation = useControlOperation()
    const {data, isLoading, error} = useLocalMediaProfileView(slug)

    const [renameConfirm, setRenameConfirm] = useState(false)
    const [deleteDownloadsConfirm, setDeleteDownloadsConfirm] = useState(false)
    const [deleteProfileConfirm, setDeleteProfileConfirm] = useState(false)
    const [deletingProfile, setDeletingProfile] = useState(false)
    const [operationControlBusy, setOperationControlBusy] = useState<string | null>(null)

    const profile = data?.profile
    const statistics = data?.statistics

    const renameOperation = useActiveOperation(
        'local_media_profile.rename_files',
        'local_media_profile',
        profile?.id ?? null,
    )
    const deleteDownloadsOperation = useActiveOperation(
        'local_media_profile.delete_downloads',
        'local_media_profile',
        profile?.id ?? null,
    )

    if (isLoading) {
        return (
            <section className="view local-media-profile-view" aria-labelledby="local-media-profile-title">
                <div className="view-header">
                    <h1 id="local-media-profile-title">Local Media Profile</h1>
                </div>
                <p>Loading…</p>
            </section>
        )
    }

    if (!slug || !profile || !statistics || error) {
        return (
            <section className="view local-media-profile-view" aria-labelledby="local-media-profile-title">
                <div className="view-header">
                    <h1 id="local-media-profile-title">Local Media Profile</h1>
                </div>
                <p role="alert">This Local Media Profile could not be loaded.</p>
            </section>
        )
    }

    const actionBusy = Boolean(renameOperation || deleteDownloadsOperation)
    const managedLabel = profile.type === 'show' ? 'Managed episodes' : 'Managed items'
    const downloadedLabel = profile.type === 'show' ? 'Downloaded episodes' : 'Downloaded items'

    const controlTaskOperation = async (
        operationId: string,
        action: OperationControlAction,
        label: string,
    ) => {
        if (operationControlBusy !== null) return
        const busyKey = `${operationId}:${action}`
        setOperationControlBusy(busyKey)
        try {
            await controlOperation(operationId, action)
            toast.success(action === 'restart' ? `${label} restarted` : `${label} canceled`)
        } catch (controlError) {
            const detail = controlError instanceof OperationControlError
                ? controlError.message
                : undefined
            toast.error(
                `Could not ${action} ${label}${detail ? `: ${detail}` : ''}`,
            )
        } finally {
            setOperationControlBusy((current) => current === busyKey ? null : current)
        }
    }

    const operationControls = (
        operationId: string | undefined,
        label: string,
    ) => {
        if (!operationId) return undefined
        const controlsBusy = operationControlBusy !== null
        return [
            {
                label: `Restart ${label}`,
                icon: ['fas', 'rotate-right'],
                disabled: controlsBusy,
                onSelect: () => void controlTaskOperation(operationId, 'restart', label),
            },
            {
                label: `Cancel ${label}`,
                icon: ['fas', 'xmark'],
                tone: 'danger' as const,
                disabled: controlsBusy,
                onSelect: () => void controlTaskOperation(operationId, 'cancel', label),
            },
        ]
    }

    const deleteProfile = async () => {
        if (deletingProfile || actionBusy) return
        setDeletingProfile(true)
        try {
            const endpoint = profile.type === 'movie'
                ? 'movie-local-media-profiles'
                : 'show-local-media-profiles'
            const base = (window as any).appConfig?.API_URL || '/api'
            const response = await fetch(
                `${base}/${endpoint}/${encodeURIComponent(profile.slug)}`,
                {method: 'DELETE', credentials: 'include'},
            )
            if (!response.ok) {
                const {error: message} = await getErrorMessageFromResponse(response)
                throw new Error(message)
            }

            await Promise.all([
                queryClient.invalidateQueries({queryKey: ['localMediaProfiles']}),
                queryClient.invalidateQueries({queryKey: ['downloadProfilesView']}),
                queryClient.invalidateQueries({queryKey: ['mediaDownloadsView']}),
            ])
            toast.success(`Deleted ${profile.name}`)
            navigate('/local-media-profiles', {replace: true})
        } catch (deleteError) {
            toast.error(
                deleteError instanceof Error
                    ? deleteError.message
                    : 'Could not delete Local Media Profile',
            )
        } finally {
            setDeletingProfile(false)
            setDeleteProfileConfirm(false)
        }
    }

    const availableFor = profile.type === 'show'
        ? ShowLocalMediaProfileScopeReg.getLabelLoose(profile.showScope)
        : 'Movies'

    return (
        <section className="view local-media-profile-view" aria-labelledby="local-media-profile-title">
            <div className="view-header">
                <h1 id="local-media-profile-title">{profile.name}</h1>
            </div>

            <article className="local-media-profile-details" aria-label="Local Media Profile details">
                <header className="local-media-profile-page-header">
                    <div className="local-media-profile-page-heading">
                        <div className="local-media-profile-kind">
                            {LocalMediaProfileTypeReg.getLabelLoose(profile.type)} Local Media Profile
                        </div>
                        <div className="local-media-profile-meta">
                            {PreferredFormatReg.getLabelLoose(profile.preferredFormat)} · {availableFor}
                        </div>
                    </div>

                    <div className="local-media-profile-page-actions">
                        <button
                            type="button"
                            className="btn"
                            onClick={() => navigate(`/edit-local-media-profile/${encodeURIComponent(profile.slug)}`)}
                        >
                            <FontAwesomeIcon icon={['fas', 'pen-to-square'] as any} aria-hidden="true"/>
                            <span>Edit</span>
                        </button>
                        <button
                            type="button"
                            className="btn btn-danger"
                            disabled={actionBusy}
                            title={actionBusy ? 'Wait for the active profile action to finish first' : undefined}
                            onClick={() => setDeleteProfileConfirm(true)}
                        >
                            <FontAwesomeIcon icon={['fas', 'trash'] as any} aria-hidden="true"/>
                            <span>Delete</span>
                        </button>
                        <ActionMenu
                            items={[
                                {
                                    label: 'Rename all managed files',
                                    icon: ['fas', 'file-pen'],
                                    disabled: Boolean(renameOperation || deleteDownloadsOperation),
                                    disabledReason: renameOperation
                                        ? 'A file rename operation is already running for this profile.'
                                        : deleteDownloadsOperation
                                            ? 'A delete downloads operation is running for this profile.'
                                            : undefined,
                                    progress: renameOperation?.progress ?? undefined,
                                    controls: operationControls(renameOperation?.id, 'file rename'),
                                    onSelect: () => setRenameConfirm(true),
                                },
                                {
                                    label: 'Delete all downloads',
                                    icon: ['fas', 'trash'],
                                    tone: 'danger',
                                    separatorBefore: true,
                                    disabled: Boolean(renameOperation || deleteDownloadsOperation) || statistics.managedMediaCount === 0,
                                    disabledReason: deleteDownloadsOperation
                                        ? 'A delete downloads operation is already running for this profile.'
                                        : renameOperation
                                            ? 'A file rename operation is running for this profile.'
                                            : statistics.managedMediaCount === 0
                                            ? 'This Local Media Profile does not manage any downloads.'
                                            : undefined,
                                    progress: deleteDownloadsOperation?.progress ?? undefined,
                                    controls: operationControls(
                                        deleteDownloadsOperation?.id,
                                        'delete downloads',
                                    ),
                                    onSelect: () => setDeleteDownloadsConfirm(true),
                                },
                            ]}
                        />
                    </div>
                </header>

                <div className="local-media-profile-statistics" aria-label="Profile statistics">
                    <div className="local-media-profile-stat">
                        <span className="local-media-profile-stat-value">{statistics.managedMediaCount}</span>
                        <span className="local-media-profile-stat-label">{managedLabel}</span>
                    </div>
                    <div className="local-media-profile-stat">
                        <span className="local-media-profile-stat-value">{statistics.downloadedMediaCount}</span>
                        <span className="local-media-profile-stat-label">{downloadedLabel}</span>
                    </div>
                    <div className="local-media-profile-stat">
                        <span className="local-media-profile-stat-value">
                            {formatBytes(statistics.storageSizeBytes) || '0 KiB'}
                        </span>
                        <span className="local-media-profile-stat-label">Storage used</span>
                    </div>
                    <div className="local-media-profile-stat">
                        <span className="local-media-profile-stat-value">{statistics.downloadProfileCount}</span>
                        <span className="local-media-profile-stat-label">Download Profiles</span>
                    </div>
                </div>

                <dl className="local-media-profile-properties">
                    <div>
                        <dt>Output path template</dt>
                        <dd className="mono">{profile.outputTemplate}</dd>
                    </div>
                    <div>
                        <dt>Preferred format</dt>
                        <dd>{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</dd>
                    </div>
                    <div>
                        <dt>Available for</dt>
                        <dd>{availableFor}</dd>
                    </div>
                </dl>
            </article>

            <ActionConfirmDialogue
                open={renameConfirm}
                operationDefinition={frontendOperationDefinitions['local_media_profile.rename_files']}
                requestPath={`/local-media-profiles/${encodeURIComponent(profile.slug)}/rename-files`}
                resourceLabel={profile.name}
                title="Rename all managed files"
                onDismiss={() => setRenameConfirm(false)}
                icon={['fas', 'file-pen']}
                confirmLabel="Rename files"
                disabled={Boolean(deleteDownloadsOperation)}
            >
                <p>
                    Rename all existing files managed by "{profile.name}" so their paths match
                    the profile's current output template and metadata.
                </p>
            </ActionConfirmDialogue>

            <ActionConfirmDialogue
                open={deleteDownloadsConfirm}
                operationDefinition={frontendOperationDefinitions['local_media_profile.delete_downloads']}
                requestPath={`/local-media-profiles/${encodeURIComponent(profile.slug)}/delete-downloads`}
                resourceLabel={profile.name}
                title="Delete all downloads"
                onDismiss={() => setDeleteDownloadsConfirm(false)}
                icon={['fas', 'trash']}
                iconTone="danger"
                confirmLabel="Delete downloads"
                disabled={Boolean(renameOperation)}
            >
                <p>
                    Delete every downloaded file managed by "{profile.name}". MediaDownload
                    records remain attached to the profile so their history is preserved.
                </p>
                {statistics.downloadProfileCount > 0 && (
                    <p>
                        WireLoft will disable Download Profiles that use this Local Media Profile
                        before deleting files so automatic downloads do not immediately recreate them.
                    </p>
                )}
            </ActionConfirmDialogue>

            <ConfirmDialog
                open={deleteProfileConfirm}
                title="Delete Local Media Profile"
                onDismiss={() => {
                    if (!deletingProfile) setDeleteProfileConfirm(false)
                }}
                icon={['fas', 'trash']}
                iconTone="danger"
                dismissOnOverlayClick={!deletingProfile}
                cancelButton={{disabled: deletingProfile}}
                confirmButton={{
                    label: deletingProfile ? 'Deleting…' : 'Delete profile',
                    className: 'btn btn-danger',
                    disabled: deletingProfile || actionBusy,
                    onClick: () => void deleteProfile(),
                }}
            >
                <p>
                    Delete "{profile.name}"? WireLoft will remove attached MediaDownload records
                    only when none of them still has a physical file.
                </p>
                {statistics.downloadProfileCount > 0 && (
                    <p>
                        This profile is still used by {statistics.downloadProfileCount} Download
                        {statistics.downloadProfileCount === 1 ? ' Profile' : ' Profiles'}.
                        Change or delete those profiles before deleting this Local Media Profile.
                    </p>
                )}
                {(renameOperation?.status === 'WAITING' || deleteDownloadsOperation?.status === 'WAITING') && (
                    <p>{renameOperation?.message || deleteDownloadsOperation?.message || OPERATION_WAITING_MESSAGE}</p>
                )}
            </ConfirmDialog>
        </section>
    )
}
