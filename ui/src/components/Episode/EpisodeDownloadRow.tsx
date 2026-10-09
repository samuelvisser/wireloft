import {useState} from 'react'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'

import {isPublicationDelayWait} from '../../lib/downloadProgress'
import {PreferredFormatReg} from '../../types/local_media_profile'
import type {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import type {MediaDownloadViewRead} from '../../types/schemas/media_download'
import {getErrorMessageFromResponse} from '../../utils/helpers'
import {faIcon} from '../../icons/faIcon'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'
import DownloadProgressStatus from '../DownloadProgress/DownloadProgressStatus'
import DownloadLogDialog from '../MediaDownload/DownloadLogDialog'
import ProgressExplanation from '../common/ProgressExplanation'
import {
    ImmediateSafeDelayConfirmDialog,
    SafeDelayConfirmDialog,
    freezeSafeDelaySchedulePreference,
    shouldPromptForSafeDelay,
} from './SafeDelayDownloadDialogs'

type SafeDelayAction = 'download' | 'retry'
type SafeDelayDialogState = {
    action: SafeDelayAction
    step: 'choice' | 'immediate'
}

export function EpisodeDownloadRow({
    profile,
    download,
    downloadStateKnown = true,
    episodeSlug,
    confirmCountdownDownload,
    confirmSafeDelayDownload,
    safeDelayReadyAt,
}: {
    profile: LocalMediaProfileRead
    download?: MediaDownloadViewRead
    downloadStateKnown?: boolean
    episodeSlug: string
    confirmCountdownDownload: boolean
    confirmSafeDelayDownload: boolean
    safeDelayReadyAt: Date | null
}) {
    const qc = useQueryClient()
    const [busy, setBusy] = useState(false)
    const [showLog, setShowLog] = useState(false)
    const [countdownConfirm, setCountdownConfirm] = useState(false)
    const [safeDelayDialog, setSafeDelayDialog] = useState<SafeDelayDialogState | null>(null)
    const [safeDelaySchedulePreferred, setSafeDelaySchedulePreferred] = useState<boolean | null>(null)
    const [safeDelaySubmitting, setSafeDelaySubmitting] = useState<'schedule' | 'immediate' | null>(null)
    const [redownloadWhenFinal, setRedownloadWhenFinal] = useState(true)
    const [redownloadWhenDelayPassed, setRedownloadWhenDelayPassed] = useState(true)

    const publicationDelayWait = Boolean(
        download
        && isPublicationDelayWait(download.operation)
    )
    const schedulePreferred = safeDelaySchedulePreferred === true
    const safeDelayIsRetry = safeDelayDialog?.action === 'retry'

    const invalidate = () =>
        Promise.all([
            qc.invalidateQueries({queryKey: ['episodeDownloads', episodeSlug]}),
            qc.invalidateQueries({queryKey: ['mediaDownloads']}),
            qc.invalidateQueries({queryKey: ['mediaDownloadsView']}),
        ])

    async function request(url: string, init: RequestInit, failure: string) {
        setBusy(true)
        try {
            const response = await fetch(url, {credentials: 'include', ...init})
            if (!response.ok) {
                const {error} = await getErrorMessageFromResponse(response)
                toast.error(error || failure)
            }
            await invalidate()
        } catch {
            toast.error(failure)
        } finally {
            setBusy(false)
        }
    }

    const startDownload = ({
        redownloadFinal = false,
        redownloadDelayPassed = false,
        scheduleForDelay = false,
    }: {
        redownloadFinal?: boolean
        redownloadDelayPassed?: boolean
        scheduleForDelay?: boolean
    } = {}) =>
        request(
            `${(window as any).appConfig.API_URL}/episodes/${encodeURIComponent(episodeSlug)}/downloads`,
            {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    localMediaProfileId: profile.id,
                    redownloadWhenFinal: redownloadFinal,
                    redownloadWhenDelayPassed: redownloadDelayPassed,
                    scheduleForDelay,
                }),
            },
            scheduleForDelay ? 'Could not schedule the download' : 'Could not start the download',
        )

    const retryDownload = ({
        redownloadDelayPassed = false,
        scheduleForDelay = false,
    }: {
        redownloadDelayPassed?: boolean
        scheduleForDelay?: boolean
    } = {}) =>
        request(
            `${(window as any).appConfig.API_URL}/media-downloads/${download!.id}/retry`,
            {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    redownloadWhenDelayPassed: redownloadDelayPassed,
                    scheduleForDelay,
                }),
            },
            scheduleForDelay ? 'Could not schedule the re-download' : 'Could not retry the download',
        )

    const closeSafeDelayDialogs = () => {
        setSafeDelayDialog(null)
    }

    const openSafeDelayDialog = (action: SafeDelayAction) => {
        // Freeze the primary action for this mounted row. Unrelated re-renders
        // must not swap buttons under the user as the ten-minute threshold passes.
        // A page reload remounts the row and recalculates the preference.
        setSafeDelaySchedulePreferred((current) => (
            freezeSafeDelaySchedulePreference(current, safeDelayReadyAt)
        ))
        setSafeDelayDialog({action, step: 'choice'})
    }

    const requestDownload = () => {
        if (confirmCountdownDownload) {
            setRedownloadWhenFinal(true)
            setCountdownConfirm(true)
            return
        }
        if (shouldPromptForSafeDelay(confirmSafeDelayDownload, safeDelayReadyAt)) {
            setRedownloadWhenDelayPassed(true)
            openSafeDelayDialog('download')
            return
        }
        void startDownload()
    }

    const requestRetry = () => {
        if (shouldPromptForSafeDelay(confirmSafeDelayDownload, safeDelayReadyAt)) {
            setRedownloadWhenDelayPassed(true)
            openSafeDelayDialog('retry')
            return
        }
        void retryDownload()
    }

    const scheduleSafeDelayDownload = async () => {
        setSafeDelaySubmitting('schedule')
        try {
            if (safeDelayDialog?.action === 'retry') {
                await retryDownload({scheduleForDelay: true})
            } else {
                await startDownload({scheduleForDelay: true})
            }
            closeSafeDelayDialogs()
        } finally {
            setSafeDelaySubmitting(null)
        }
    }

    const downloadImmediately = async () => {
        setSafeDelaySubmitting('immediate')
        try {
            if (safeDelayDialog?.action === 'retry') {
                await retryDownload({redownloadDelayPassed: redownloadWhenDelayPassed})
            } else {
                await startDownload({redownloadDelayPassed: redownloadWhenDelayPassed})
            }
            closeSafeDelayDialogs()
        } finally {
            setSafeDelaySubmitting(null)
        }
    }

    const requestImmediateSafeDelayDownload = () => {
        if (!schedulePreferred) {
            void downloadImmediately()
            return
        }
        setRedownloadWhenDelayPassed(true)
        setSafeDelayDialog((current) => (
            current ? {...current, step: 'immediate'} : current
        ))
    }

    const cancelDownload = () =>
        request(
            `${(window as any).appConfig.API_URL}/media-downloads/${download!.id}/cancel`,
            {method: 'POST'},
            'Could not cancel the download',
        )

    const showDownloadButton = downloadStateKnown && (
        !download
        || (!download.presentation.active && download.presentation.status === 'not_downloaded')
    )
    const showRetryButton = Boolean(
        download
        && (
            (!download.presentation.active && download.presentation.canRetry)
            || publicationDelayWait
        )
    )

    return (
        <div className="download-row" role="listitem" aria-label={`Download for ${profile.name}`}>
            <div className="download-row-info">
                <div className="download-row-name">{profile.name}</div>
                <div className="download-row-format">{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</div>
            </div>
            <div className="download-row-state">
                {!downloadStateKnown
                    ? (
                        <span
                            className="download-row-loading"
                            role="status"
                            aria-label={`Loading download status for ${profile.name}`}
                        >
                            Loading…
                        </span>
                    )
                    : download && !showDownloadButton
                        ? <DownloadProgressStatus download={download} details={false}/>
                        : <button
                            type="button"
                            className="btn btn-primary"
                            onClick={requestDownload}
                            disabled={busy}
                            aria-label={`Download ${profile.name}`}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'download')}/>
                            Download
                        </button>}
            </div>
            {downloadStateKnown && download && (
                <div className="download-row-actions" aria-label={`Actions for ${profile.name}`}>
                    <ProgressExplanation
                        detail={download.presentation.detail + (download.presentation.secondary
                            ? ` ${download.presentation.secondary}.`
                            : '')}
                    />
                    {download.presentation.active && download.presentation.canCancel && (
                        <button
                            type="button"
                            className="icon-btn"
                            onClick={cancelDownload}
                            disabled={busy}
                            title="Cancel download"
                            aria-label={`Cancel download for ${profile.name}`}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'ban')}/>
                        </button>
                    )}
                    {showRetryButton && (
                        <button
                            type="button"
                            className="icon-btn"
                            onClick={requestRetry}
                            disabled={busy}
                            title={publicationDelayWait
                                ? 'Download now'
                                : download.presentation.outcome === 'success'
                                    ? 'Re-download'
                                    : 'Retry download'}
                            aria-label={publicationDelayWait
                                ? `Download ${profile.name} now`
                                : download.presentation.outcome === 'success'
                                    ? `Re-download ${profile.name}`
                                    : `Retry download for ${profile.name}`}
                        >
                            <FontAwesomeIcon icon={faIcon('fas', 'rotate-right')}/>
                        </button>
                    )}
                    <button
                        type="button"
                        className="icon-btn"
                        onClick={() => setShowLog(true)}
                        title="View log"
                        aria-label={`View log for ${profile.name}`}
                    >
                        <FontAwesomeIcon icon={faIcon('fas', 'file-lines')}/>
                    </button>
                </div>
            )}
            <ConfirmDialog
                open={countdownConfirm}
                title="Download episode with countdown?"
                onDismiss={() => {
                    if (!busy) setCountdownConfirm(false)
                }}
                icon={faIcon('fas', 'circle-exclamation')}
                dismissOnOverlayClick={!busy}
                cancelButton={{disabled: busy}}
                confirmButton={{
                    label: busy ? 'Starting…' : 'Yes, download',
                    onClick: async () => {
                        await startDownload({redownloadFinal: redownloadWhenFinal})
                        setCountdownConfirm(false)
                    },
                    icon: faIcon('fas', 'download'),
                    disabled: busy,
                }}
            >
                <p>
                    This episode is published, but its current media still contains The Daily Wire countdown.
                </p>
                <p>
                    If you continue, WireLoft will download the current media as-is, including that countdown.
                </p>
                <label className="confirm-dialog-option">
                    <input
                        type="checkbox"
                        checked={redownloadWhenFinal}
                        onChange={(event) => setRedownloadWhenFinal(event.target.checked)}
                        disabled={busy}
                    />
                    <span>Re-download automatically when the countdown is gone</span>
                </label>
            </ConfirmDialog>
            <SafeDelayConfirmDialog
                open={safeDelayDialog?.step === 'choice'}
                isRetry={safeDelayIsRetry}
                safeDelayReadyAt={safeDelayReadyAt}
                schedulePreferred={schedulePreferred}
                busy={busy}
                submitting={safeDelaySubmitting}
                redownloadWhenDelayPassed={redownloadWhenDelayPassed}
                onRedownloadWhenDelayPassedChange={setRedownloadWhenDelayPassed}
                onDismiss={() => {
                    if (!busy) closeSafeDelayDialogs()
                }}
                onSchedule={scheduleSafeDelayDownload}
                onImmediate={requestImmediateSafeDelayDownload}
            />
            <ImmediateSafeDelayConfirmDialog
                open={safeDelayDialog?.step === 'immediate'}
                isRetry={safeDelayIsRetry}
                busy={busy}
                submitting={safeDelaySubmitting}
                redownloadWhenDelayPassed={redownloadWhenDelayPassed}
                onRedownloadWhenDelayPassedChange={setRedownloadWhenDelayPassed}
                onDismiss={() => {
                    if (!busy) closeSafeDelayDialogs()
                }}
                onImmediate={downloadImmediately}
            />
            <DownloadLogDialog row={showLog ? (download ?? null) : null} onClose={() => setShowLog(false)}/>
        </div>
    )
}
