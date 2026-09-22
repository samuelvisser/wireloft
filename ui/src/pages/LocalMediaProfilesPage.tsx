import {useCallback, useRef} from 'react'
import {useNavigate} from 'react-router-dom'
import type {IconProp} from '@fortawesome/fontawesome-svg-core'
import {useLocalMediaProfiles} from '../lib/queries'
import {LocalMediaProfileRead} from "../types/schemas/local_media_profile";
import {
    LocalMediaProfileTypeReg,
    PreferredFormatReg,
    ShowLocalMediaProfileScopeReg,
} from "../types/local_media_profile";
import DataTable, { Column } from '../components/DataTable/DataTable';
import ConfirmDeleteDialog, { ConfirmDeleteDialogRef } from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import PageSubtitle from "../components/common/PageSubtitle";
import './LocalMediaProfilesPage.css'

function getAvailableForLabel(profile: LocalMediaProfileRead) {
    return profile.type === 'show'
        ? ShowLocalMediaProfileScopeReg.getLabelLoose(profile.showScope)
        : 'Movies'
}

export default function LocalMediaProfilesPage() {
    const navigate = useNavigate()
    const onAdd = useCallback(() => navigate('/add-local-media-profile'), [navigate])
    const editIcon: IconProp = ['fas', 'pen-to-square']
    const deleteIcon: IconProp = ['fas', 'trash']

    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)

    const columns: Column<LocalMediaProfileRead>[] = [
        {
            header: 'Name',
            cell: (p) => (
                <span className="local-media-profile-name" title={p.name}>
                    {p.name}
                </span>
            ),
            width: '1%',
            headerStyle: {minWidth: 180, maxWidth: '30%', whiteSpace: 'nowrap'},
            cellStyle: {minWidth: 180, maxWidth: '30%', whiteSpace: 'nowrap', overflow: 'hidden'},
            mobileHidden: true,
        },
        {
            header: 'Output Path Template',
            cell: (p) => (
                <span className="mono local-media-profile-output-template" title={p.outputTemplate}>
                    {p.outputTemplate}
                </span>
            ),
            width: '100%',
            cellStyle: {maxWidth: 0},
        },
        {
            header: 'Type',
            accessor: (p) => LocalMediaProfileTypeReg.getLabelLoose(p.type),
            width: 90,
        },
        {
            header: 'Available for',
            accessor: getAvailableForLabel,
            width: '1%',
            headerStyle: {whiteSpace: 'nowrap'},
            cellStyle: {whiteSpace: 'nowrap'},
        },
        {
            header: 'Preferred Format',
            accessor: (p) => PreferredFormatReg.getLabelLoose(p.preferredFormat),
            width: '1%',
            headerStyle: {whiteSpace: 'nowrap'},
            cellStyle: {whiteSpace: 'nowrap'},
        }
    ]

    const {data: profiles, isLoading, error} = useLocalMediaProfiles()

    return (
        <section className="view" aria-labelledby="profiles-title">
            <div className="view-header">
                <h1 id="profiles-title">Local Media Profiles</h1>
                <PageSubtitle summary={<>Define how downloaded files are stored and in what format.</>}>
                    <p>A Local Media Profile controls the output path and the preferred file format for your downloads
                        across shows and movies. You can create multiple profiles (e.g., “Podcasts to ABS”, “Videos to NAS”) and
                        reuse them.</p>
                </PageSubtitle>
                <button className="btn btn-primary" onClick={onAdd}>Add media profile</button>
            </div>

            <div className="form-row">
                <DataTable<LocalMediaProfileRead>
                    ariaLabel="Existing media profiles"
                    columns={columns}
                    data={profiles}
                    loading={isLoading}
                    error={error}
                    rowKey={(p) => p.id}
                    rowAriaLabel={(p) => p.name}
                    className="table local-media-profiles-table"
                    wrapperClassName="table-wrapper local-media-profiles-table-wrapper"
                    mobileSummary={(p) => (
                        <>
                            <span className="mobile-summary-title">{p.name}</span>
                            <span className="mobile-summary-meta">
                                <span>{LocalMediaProfileTypeReg.getLabelLoose(p.type)}</span>
                                <span>{getAvailableForLabel(p)}</span>
                                <span>{PreferredFormatReg.getLabelLoose(p.preferredFormat)}</span>
                            </span>
                        </>
                    )}
                    onRowClick={(p) => navigate(`/edit-local-media-profile/${p.slug}`, { state: { ...p, outputPathTemplate: p.outputTemplate } })}
                    actions={(p) => [
                        {
                            onClick: () => navigate(`/edit-local-media-profile/${p.slug}`, { state: p }),
                            icon: editIcon,
                            text: 'Edit',
                            classes: 'btn',
                        },
                        {
                            onClick: () => confirmRef.current?.open(p),
                            icon: deleteIcon,
                            text: 'Delete',
                            classes: 'btn btn-danger',
                        },
                    ]}
                />
            </div>

            <ConfirmDeleteDialog
                ref={confirmRef}
                title="Delete media profile"
                subjectProp="name"
                deleteRequest={(p) => {
                    const endpoint = p.type === 'movie'
                        ? 'movie-local-media-profiles'
                        : 'show-local-media-profiles'
                    const path = `${endpoint}/${p.slug}`
                    return fetch(`${(window as any).appConfig.API_URL}/${path}`, { method: 'DELETE', credentials: 'include' })
                }}
                invalidateQueries={[["localMediaProfiles"]]}
                inUseMessage="This media profile is in use, it cannot be deleted"
            />
        </section>
    )
}
