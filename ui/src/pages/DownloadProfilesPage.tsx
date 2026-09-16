import {useCallback, useRef} from 'react'
import {useNavigate} from 'react-router-dom'
import {useQueryClient} from '@tanstack/react-query'
import {toast} from 'react-hot-toast'
import {useDownloadProfilesView} from '../lib/queries'
import {DownloadProfileReadView} from '../types/schemas/download_profile_view'
import {PreferredFormatReg} from '../types/local_media_profile'
import DataTable, {Column} from '../components/DataTable/DataTable'
import ConfirmDeleteDialog, {ConfirmDeleteDialogRef} from '../components/ConfirmDeleteDialog/ConfirmDeleteDialog'
import PageSubtitle from "../components/common/PageSubtitle";
import ProfileEnabledSwitch from '../components/common/ProfileEnabledSwitch'
import {ShowTypeReg} from "../types/show";
import {PodcastDownloadProfileUpdateSchema} from '../types/schemas/podcast_download_profile'
import {SeriesDownloadProfileUpdateSchema} from '../types/schemas/series_download_profile'

export default function DownloadProfilesPage() {
    const navigate = useNavigate()
    const queryClient = useQueryClient()
    const onAdd = useCallback(() => navigate('/add-download-profile'), [navigate])

    const {data: profiles, isLoading, error} = useDownloadProfilesView()

    const confirmRef = useRef<ConfirmDeleteDialogRef>(null)

    const setProfileEnabled = useCallback(async (profile: DownloadProfileReadView, enableProfile: boolean) => {
        try {
            const endpoint = profile.type === 'podcast' ? 'podcast-download-profiles' : 'series-download-profiles'
            const body = profile.type === 'podcast'
                ? PodcastDownloadProfileUpdateSchema.parse({...profile.downloadProfileImpl, enableProfile})
                : SeriesDownloadProfileUpdateSchema.parse({...profile.downloadProfileImpl, enableProfile})

            const response = await fetch(`${(window as any).appConfig.API_URL}/${endpoint}/${profile.id}`, {
                method: 'PATCH',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify(body),
            })
            if (!response.ok) throw new Error(`Failed to update download profile (${response.status})`)

            queryClient.setQueryData<DownloadProfileReadView[]>(['downloadProfilesView'], (current) => (
                current?.map((item) => (
                    item.id === profile.id && item.type === profile.type
                        ? {...item, enableProfile}
                        : item
                ))
            ))

            await Promise.allSettled([
                queryClient.invalidateQueries({queryKey: ['downloadProfilesView']}),
                queryClient.invalidateQueries({queryKey: ['podcastDownloadProfiles']}),
                queryClient.invalidateQueries({queryKey: ['seriesDownloadProfiles']}),
            ])
        } catch (updateError) {
            toast.error(`Failed to ${enableProfile ? 'enable' : 'disable'} download profile`)
            throw updateError
        }
    }, [queryClient])

    const columns: Column<DownloadProfileReadView>[] = [
        {
            header: 'Show Title',
            accessor: (p) => p.showTitle,
            mobileHidden: true,
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
            cell: (p) => (
                <ProfileEnabledSwitch
                    checked={p.enableProfile}
                    ariaLabel={`Automatic downloads for ${p.showTitle}`}
                    onChange={(checked) => setProfileEnabled(p, checked)}
                />
            ),
            align: 'center',
        },
    ]

    return (
        <section className="view" aria-labelledby="profiles-title">
            <div className="view-header">
                <h1 id="profiles-title">Download Profiles</h1>
                <PageSubtitle summary={<>Create rules for how each show is downloaded.</>}>
                    <p>A Download Profile tells WireLoft what to download and how long to retain your downloads.
                        Each show can contain multiple download profiles, allowing you to
                        download both audio and video versions of episodes for example.</p>
                    <p>Download Profiles are always connected to a Local Media Profile, which defines where your
                        downloads will be stored and what their file name should be.</p>
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
                    mobileSummary={(p) => (
                        <>
                            <span className="mobile-summary-title">{p.showTitle}</span>
                            <span className="mobile-summary-meta">
                                <span>{PreferredFormatReg.getLabelLoose(p.localMediaProfilePreferredFormat)}</span>
                                <span aria-hidden="true">•</span>
                                <span>{ShowTypeReg.getLabelLoose(p.type)}</span>
                                <span className={`mobile-summary-status ${p.enableProfile ? 'is-success' : ''}`}>
                                    {p.enableProfile ? 'Enabled' : 'Disabled'}
                                </span>
                            </span>
                        </>
                    )}
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
