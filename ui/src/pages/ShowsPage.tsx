import {useCallback, useRef} from 'react'
import {useNavigate} from 'react-router-dom'
import {useShows} from '../lib/queries'
import {ShowRead} from '../types/schemas/show'
import DataTable, {Column} from '../components/DataTable/DataTable'
import ConfirmDeleteDialog, {ConfirmDeleteDialogRef} from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import {EpisodeIdentifierReg, ShowTypeReg} from "../types/show";

export default function ShowsPage() {
    const navigate = useNavigate()
    const onAdd = useCallback(() => navigate('/add-show'), [navigate])

    const {data: shows, isLoading, error} = useShows()

    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)

    const columns: Column<ShowRead>[] = [
        {
            header: 'Title',
            accessor: (s) => s.title,
        },
        {
            header: 'Author',
            accessor: (s) => s.authorName,
        },
        {
            header: 'Type',
            accessor: (s) => ShowTypeReg.getLabelLoose(s.type),
            align: 'center',
        },
        {
            header: 'Episode ID',
            accessor: (s) => EpisodeIdentifierReg.getLabelLoose(s.episodeIdentifier),
            align: 'center',
        },
    ]

    return (
        <section className="view" aria-labelledby="shows-title">
            <div className="view-header">
                <h1 id="shows-title">Shows</h1>
                <button className="btn btn-primary" onClick={onAdd}>Add show</button>
            </div>

            <div className="form-row">
                <DataTable<ShowRead>
                    ariaLabel="Existing shows"
                    columns={columns}
                    data={shows}
                    loading={isLoading}
                    error={error}
                    rowKey={(s) => s.slug}
                    rowAriaLabel={(s) => s.title}
                    onRowClick={(s) => navigate(`/show/${s.slug}`)}
                    actions={(s) => [
                        {
                            onClick: () => navigate(`/edit-show/${s.slug}`),
                            icon: ['fas', 'pen-to-square'],
                            text: 'Edit',
                            classes: 'btn',
                        },
                        {
                            onClick: () => confirmRef.current?.open(s),
                            icon: ['fas', 'trash'],
                            text: 'Delete',
                            classes: 'btn btn-danger',
                        },
                    ]}
                />
            </div>

            <ConfirmDeleteDialog
                ref={confirmRef}
                title="Delete show"
                subjectProp={(s) => s.title}
                deleteRequest={(s) => fetch(`${(window as any).appConfig.API_URL}/shows/${encodeURIComponent(s.slug)}`, {method: 'DELETE', credentials: 'include'})}
                invalidateQueries={[['shows']]}
                inUseMessage="This show is in use, it cannot be deleted"
            />
        </section>
    )
}
