import {useCallback, useRef} from 'react'
import {useNavigate} from 'react-router-dom'
import {useDownloadProfilesView} from '../lib/queries'
import {DownloadProfileReadView} from '../types/schemas/download_profile_view'
import {PreferredFormatReg} from '../types/local_media_profile'
import DataTable, {Column} from '../components/DataTable/DataTable'
import ConfirmDeleteDialog, {ConfirmDeleteDialogRef} from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import PageSubtitle from "../components/common/PageSubtitle";
import {ShowTypeReg} from "../types/show";

export default function DownloadProfilesPage() {
    const navigate = useNavigate()
    const onAdd = useCallback(() => navigate('/add-download-profile'), [navigate])

    const {data: profiles, isLoading, error} = useDownloadProfilesView()

    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)

    const columns: Column<DownloadProfileReadView>[] = [
        {
            header: 'Show Title',
            accessor: (p) => p.showTitle,
        },
        {
            header: 'Preferred Format',
            accessor: (p) => PreferredFormatReg.getLabelLoose(p.localMediaProfilePreferredFormat),
        },
        {
            header: 'Type',
            accessor: (p) => ShowTypeReg.getLabelLoose(p.type),
        },
        {
            header: 'Enabled',
            accessor: (p) => (p.enableProfile ? '✓' : '✕'),
            align: 'center',
        },
    ]

    return (
        <section className="view" aria-labelledby="profiles-title">
            <div className="view-header">
                <h1 id="profiles-title">Download Profiles</h1>
                <PageSubtitle summary={<>Create rules for how each show is downloaded and organized on disk.</>}>
                    <p>A Download Profile tells WireLoft what to download and where to put it, including quality, file
                        naming, and grouping. Each show can contain multiple download profiles, allowing you to
                        download both audio and video versions of episodes for example.</p>
                </PageSubtitle>
                <button className="btn btn-primary" onClick={onAdd}>Add download profile</button>
            </div>

            <div className="form-row">
                <DataTable<DownloadProfileReadView>
                    ariaLabel="Existing download profiles"
                    columns={columns}
                    data={profiles}
                    loading={isLoading}
                    error={error}
                    rowKey={(p) => `${p.type}-${p.id}`}
                    rowAriaLabel={(p) => `${p.type} ${p.showTitle}`}
                    onRowClick={(p) => navigate(`/edit-download-profile/${p.type}/${p.id}`, {state: p})}
                    actions={(p) => [
                        {
                            onClick: () => navigate(`/edit-download-profile/${p.type}/${p.id}`, {state: p}),
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
                title="Delete download profile"
                subjectProp="showTitle"
                deleteRequest={(p) => {
                    const path = `${p.type === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'}/${p.id}`
                    return fetch(`${(window as any).appConfig.API_URL}/${path}`, {method: 'DELETE', credentials: 'include'})
                }}
                invalidateQueries={[["downloadProfilesView"], ["podcastDownloadProfiles"], ["seriesDownloadProfiles"]]}
                inUseMessage="This download profile is in use, it cannot be deleted"
            />
        </section>
    )
}