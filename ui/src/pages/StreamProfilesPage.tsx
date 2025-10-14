import {useCallback, useRef} from 'react'
import {useNavigate} from 'react-router-dom'
import {useStreamProfilesView} from '../lib/queries'
import {StreamProfileReadView} from '../types/schemas/stream_profile_base'
import DataTable, {Column} from '../components/DataTable/DataTable'
import ConfirmDeleteDialog, {ConfirmDeleteDialogRef} from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import {PreferredFormatReg} from "../types/local_media_profile";

export default function StreamProfilesPage() {
    const navigate = useNavigate()
    const onAdd = useCallback(() => navigate('/add-stream-profile'), [navigate])

    const {data: profiles, isLoading, error} = useStreamProfilesView()

    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)

    const columns: Column<StreamProfileReadView>[] = [
        {
            header: 'Show Title',
            accessor: (p) => p.showTitle,
        },
        {
            header: 'Preferred Format',
            accessor: (p) => PreferredFormatReg.getLabelLoose(p.preferredFormat),
        },
        {
            header: 'Type',
            accessor: (p) => p.type,
        },
        {
            header: 'Stream Downloads',
            accessor: (p) => (p.useDownloads ? '✓' : '✕'),
            align: 'center',
        },
        {
            header: 'Stream from DW',
            accessor: (p) => (p.useDwStream ? '✓' : '✕'),
            align: 'center',
        },
        {
            header: 'Enabled',
            accessor: (p) => (p.enableProfile ? '✓' : '✕'),
            align: 'center',
        },
    ]

    return (
        <section className="view" aria-labelledby="stream-profiles-title">
            <div className="view-header">
                <h1 id="stream-profiles-title">Stream Profiles</h1>
                <button className="btn btn-primary" onClick={onAdd}>Add stream profile</button>
            </div>

            <div className="form-row">
                <DataTable<StreamProfileReadView>
                    ariaLabel="Existing stream profiles"
                    columns={columns}
                    data={profiles}
                    loading={isLoading}
                    error={error}
                    rowKey={(p) => `${p.type}-${p.id}`}
                    rowAriaLabel={(p) => `${p.type} ${p.showTitle}`}
                    onRowClick={(p) => navigate(`/edit-stream-profile/${p.type}/${p.id}`, {state: p})}
                    actions={(p) => [
                        {
                            onClick: () => navigate(`/edit-stream-profile/${p.type}/${p.id}`, {state: p}),
                            icon: ['fas', 'pen-to-square'],
                            text: 'Edit',
                            classes: 'btn',
                        },
                        {
                            onClick: () => confirmRef.current?.open(p),
                            icon: ['fas', 'trash'],
                            text: 'Delete',
                            classes: 'btn btn-danger',
                        },
                    ]}
                />
            </div>

            <ConfirmDeleteDialog
                ref={confirmRef}
                title="Delete stream profile"
                subjectProp="showTitle"
                deleteRequest={(p) => {
                    const path = `${p.type === 'rss' ? 'rss-stream-profiles' : 'stream-profiles'}/${p.id}`
                    return fetch(`${(window as any).appConfig.API_URL}/${path}`, {method: 'DELETE', credentials: 'include'})
                }}
                invalidateQueries={[["streamProfilesView"], ["rssStreamProfiles"]]}
                inUseMessage="This stream profile is in use, it cannot be deleted"
            />
        </section>
    )
}
