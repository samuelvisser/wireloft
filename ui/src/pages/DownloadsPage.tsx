import {useRef, useState} from 'react'
import {useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import toast from 'react-hot-toast'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@awesome.me/kit-83fa1ac5a9/icons'
import {Column, DataTable, DataTableAction} from '../components/DataTable/DataTable'
import ConfirmDeleteDialog, {ConfirmDeleteDialogRef} from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import DownloadLogDialog from '../components/MediaDownload/DownloadLogDialog'
import PageSubtitle from '../components/common/PageSubtitle'
import ProgressBar from '../components/common/ProgressBar'
import {useMediaDownloadsView} from '../lib/queries'
import {MediaDownloadStatusReg} from '../types/media_download'
import {MediaDownloadViewRead} from '../types/schemas/media_download'
import {getErrorMessageFromResponse} from '../utils/helpers'

// Ensure icons from the kit are registered (idempotent)
library.add(fas)

function formatBytes(n: number | null | undefined) {
    if (!n && n !== 0) return '—'
    if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GiB`
    if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`
    return `${Math.round(n / 1024)} KiB`
}

function StatusCell({row}: {row: MediaDownloadViewRead}) {
    const status = String(row.downloadStatus)
    if (status === 'downloading' || status === 'pending') {
        return (
            <div style={{display: 'flex', alignItems: 'center', gap: 8, minWidth: 140}} aria-live="polite">
                <div style={{flex: 1}}>
                    <ProgressBar value={row.progress} ariaLabel={`Progress for ${row.episodeTitle}`}/>
                </div>
                <span style={{minWidth: 52}}>{status === 'pending' ? 'Queued' : `${row.progress}%`}</span>
            </div>
        )
    }
    if (status === 'error') {
        return (
            <span style={{color: 'var(--error, #d64545)'}} title={row.errorMessage ?? undefined}>
                Error: {row.errorMessage ?? 'unknown'}
            </span>
        )
    }
    return <span>{MediaDownloadStatusReg.getLabelLoose(status)}</span>
}

export default function DownloadsPage() {
    const navigate = useNavigate()
    const qc = useQueryClient()
    const {data: downloads, isLoading, error} = useMediaDownloadsView()
    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)
    const [logRow, setLogRow] = useState<MediaDownloadViewRead | null>(null)

    const retry = async (row: MediaDownloadViewRead) => {
        try {
            const base = (window as any).appConfig.API_URL
            const r = await fetch(`${base}/media-downloads/${row.id}/retry`, {method: 'POST', credentials: 'include'})
            if (!r.ok) {
                const {error: message} = await getErrorMessageFromResponse(r)
                toast.error(message || 'Could not retry the download')
            }
        } catch {
            toast.error('Could not retry the download')
        }
        await qc.invalidateQueries({queryKey: ['mediaDownloadsView']})
        if (row.episodeSlug) await qc.invalidateQueries({queryKey: ['episodeDownloads', row.episodeSlug]})
    }

    const columns: Column<MediaDownloadViewRead>[] = [
        {
            header: 'Episode',
            cell: (row) => (
                <div>
                    <div>{row.episodeTitle ?? '—'}</div>
                    <div style={{color: 'var(--muted, #777)', fontSize: '0.85rem'}}>{row.showTitle ?? ''}</div>
                </div>
            ),
            dataLabel: 'Episode',
        },
        {header: 'Profile', accessor: (row) => row.localMediaProfileName ?? '—', dataLabel: 'Profile'},
        {header: 'Format', accessor: (row) => row.formatDownloaded ?? '—', align: 'center', dataLabel: 'Format'},
        {header: 'Status', cell: (row) => <StatusCell row={row}/>, dataLabel: 'Status', width: 260},
        {header: 'Size', accessor: (row) => formatBytes(row.downloadedBytes), align: 'right', dataLabel: 'Size'},
    ]

    return (
        <section className="view" aria-labelledby="downloads-title">
            <div className="view-header">
                <h1 id="downloads-title">Downloads</h1>
                <PageSubtitle summary={<>All episode downloads: running, finished and failed.</>}>
                    <p>
                        Every download requested for an episode shows up here, one row per Local Media Profile.
                        Running downloads report live progress; failed ones show the error and can be retried.
                        Deleting a row only removes the record, never the downloaded file.
                    </p>
                </PageSubtitle>
            </div>
            <div className="form-row">
                <DataTable<MediaDownloadViewRead>
                    ariaLabel="Episode downloads"
                    columns={columns}
                    data={downloads}
                    loading={isLoading}
                    error={error}
                    emptyMessage="No downloads yet. Start one from an episode's page."
                    rowKey={(row) => row.id}
                    rowAriaLabel={(row) => `${row.episodeTitle} (${row.localMediaProfileName})`}
                    onRowClick={(row) => {
                        if (row.showSlug && row.episodeSlug) navigate(`/show/${row.showSlug}/episode/${row.episodeSlug}`)
                    }}
                    actions={(row) => {
                        const actions: DataTableAction<MediaDownloadViewRead>[] = [
                            {
                                onClick: (r) => setLogRow(r),
                                icon: ['fas', 'file-lines'],
                                text: 'View log',
                                classes: 'btn',
                            },
                        ]
                        if (String(row.downloadStatus) === 'error') {
                            actions.push({
                                onClick: () => void retry(row),
                                icon: ['fas', 'rotate-right'],
                                text: 'Retry',
                                classes: 'btn',
                            })
                        }
                        if (String(row.downloadStatus) !== 'downloading') {
                            actions.push({
                                onClick: () => confirmRef.current?.open(row),
                                icon: ['fas', 'trash'],
                                text: 'Delete',
                                classes: 'btn btn-danger',
                            })
                        }
                        return actions
                    }}
                />
            </div>
            <ConfirmDeleteDialog
                ref={confirmRef}
                title="Delete download record"
                subjectProp={(row: MediaDownloadViewRead) => `${row.episodeTitle} (${row.localMediaProfileName})`}
                deleteRequest={(row: MediaDownloadViewRead) =>
                    fetch(`${(window as any).appConfig.API_URL}/media-downloads/${row.id}`, {
                        method: 'DELETE',
                        credentials: 'include',
                    })
                }
                invalidateQueries={[['mediaDownloadsView'], ['episodeDownloads']]}
            />
            <DownloadLogDialog row={logRow} onClose={() => setLogRow(null)}/>
        </section>
    )
}
