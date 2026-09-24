import {ReactNode} from 'react'
import {Link} from 'react-router-dom'
import ReadMore from '../../utils/ReadMore'
import {EpisodeTypeReg} from '../../types/episode'
import './StreamProfileAdvisory.css'

export type StreamDownloadProfileDefault = {
    id?: number
    type?: 'podcast' | 'series'
    preferredFormat: string
    episodeTypes: string[]
    enabled?: boolean
}

type DownloadMediaKind = 'audio' | 'video' | 'hls'

type Props = {
    mode: 'rss' | 'base'
    preferredFormat?: string
    videoOutputMode?: string
    useDownloads: boolean
    useDwStream: boolean
    selectedEpisodeTypes: string[]
    downloadProfileDefaults?: StreamDownloadProfileDefault[]
    showSlug?: string
    canOpenDownloadProfiles?: boolean
    onEnableDownloads: () => void
    onDisableDwStream: () => void
}

type AdvisoryCardProps = {
    title: ReactNode
    children: ReactNode
    helpSummary?: ReactNode
    help?: ReactNode
    actions?: ReactNode
}

type Coverage = {
    kind: DownloadMediaKind
    profiles: StreamDownloadProfileDefault[]
    uncoveredEpisodeTypes: string[]
    bestProfile?: StreamDownloadProfileDefault
}

const STANDARD_VIDEO_FORMATS = new Set(['format_4k', 'format_1080p', 'format_720p'])

function AdvisoryCard({
    title,
    children,
    helpSummary,
    help,
    actions,
}: AdvisoryCardProps) {
    return (
        <div className="stream-profile-advisory" role="status">
            <div className="stream-profile-advisory-title">{title}</div>
            <div>{children}</div>
            {helpSummary && help ? (
                <div className="help">
                    <ReadMore summary={<span>{helpSummary}</span>}>
                        {help}
                    </ReadMore>
                </div>
            ) : null}
            {actions ? (
                <div className="stream-profile-advisory-actions">
                    {actions}
                </div>
            ) : null}
        </div>
    )
}

function kindLabel(kind: DownloadMediaKind) {
    if (kind === 'audio') return 'Audio'
    if (kind === 'hls') return 'HLS video'
    return 'MP4 video'
}

function profileButtonLabel(kind: DownloadMediaKind) {
    if (kind === 'audio') return 'audio'
    if (kind === 'hls') return 'HLS video'
    return 'MP4 video'
}

function episodeTypeLabels(values: string[]) {
    return values.map((value) => EpisodeTypeReg.getLabelLoose(value)).join(', ')
}

export default function StreamProfileAdvisory({
    mode,
    preferredFormat,
    videoOutputMode,
    useDownloads,
    useDwStream,
    selectedEpisodeTypes,
    downloadProfileDefaults,
    showSlug,
    canOpenDownloadProfiles = true,
    onEnableDownloads,
    onDisableDwStream,
}: Props) {
    if (mode !== 'rss') return null

    const usesVideo = preferredFormat !== 'format_audio_only'
    const usesDirectMp4Video = usesVideo
        && (videoOutputMode === 'audio_mp4' || videoOutputMode === 'mp4')

    if (useDwStream && usesDirectMp4Video) {
        return (
            <AdvisoryCard
                title="Disable Daily Wire streaming for immediate MP4 playback"
                helpSummary="Why MP4 behaves differently from HLS"
                help={(
                    <>
                        <p>
                            MP4 clients expect one complete seekable file. WireLoft cannot return the beginning of that MP4 while it is still building the rest of the file from The Daily Wire&apos;s HLS stream.
                        </p>
                        <p>
                            Keep matching video episodes downloaded and use those local files for immediate MP4 playback. After disabling Daily Wire streaming, WireLoft will show whether matching Download Profile coverage is missing.
                        </p>
                    </>
                )}
                actions={(
                    <button type="button" className="btn" onClick={onDisableDwStream}>
                        Disable Daily Wire streaming
                    </button>
                )}
            >
                The Daily Wire provides video as HLS, not as a ready-to-stream MP4. If a podcast app requests the stable MP4 URL before a local video download exists, WireLoft must first download and prepare the complete episode, which can make playback take several minutes to start.
            </AdvisoryCard>
        )
    }

    if (downloadProfileDefaults === undefined) return null

    const requiredDownloadKinds: DownloadMediaKind[] = preferredFormat === 'format_audio_only'
        ? ['audio']
        : videoOutputMode === 'audio_hls'
            ? ['audio', 'hls']
            : videoOutputMode === 'audio_mp4'
                ? ['audio', 'video']
                : videoOutputMode === 'mp4_hls'
                    ? ['video', 'hls']
                    : ['video']

    const matchingProfilesForKind = (kind: DownloadMediaKind) => (
        downloadProfileDefaults.filter((profile) => {
            if (profile.enabled === false) return false
            if (kind === 'audio') return profile.preferredFormat === 'format_audio_only'
            if (kind === 'hls') return profile.preferredFormat === 'format_hls'
            return STANDARD_VIDEO_FORMATS.has(profile.preferredFormat)
        })
    )

    const coverageForKind = (kind: DownloadMediaKind): Coverage => {
        const profiles = matchingProfilesForKind(kind)
        const coveredEpisodeTypes = new Set(
            profiles.flatMap((profile) => profile.episodeTypes)
        )
        const uncoveredEpisodeTypes = selectedEpisodeTypes.filter(
            (episodeType) => !coveredEpisodeTypes.has(episodeType)
        )
        const bestProfile = [...profiles].sort((a, b) => {
            const aCoverage = selectedEpisodeTypes.filter((type) => a.episodeTypes.includes(type)).length
            const bCoverage = selectedEpisodeTypes.filter((type) => b.episodeTypes.includes(type)).length
            return bCoverage - aCoverage
        })[0]

        return {
            kind,
            profiles,
            uncoveredEpisodeTypes,
            bestProfile,
        }
    }

    const createDownloadProfileHref = (
        kind: DownloadMediaKind,
        {latestFive = false}: {latestFive?: boolean} = {},
    ) => {
        if (!showSlug) return undefined

        const targetFormat = kind === 'audio'
            ? 'format_audio_only'
            : kind === 'hls'
                ? 'format_hls'
                : STANDARD_VIDEO_FORMATS.has(preferredFormat ?? '')
                    ? preferredFormat!
                    : 'format_1080p'
        const params = new URLSearchParams({
            show: showSlug,
            preferredFormat: targetFormat,
        })
        if (latestFive) params.set('downloadEpisodeCount', '5')
        return `/add-download-profile?${params.toString()}`
    }

    const handleDownloadProfileAction = () => {
        if (!useDownloads) onEnableDownloads()
    }

    const renderCoverageRequirement = (
        coverage: Coverage,
        {latestFive = false}: {latestFive?: boolean} = {},
    ) => {
        const {kind, profiles, uncoveredEpisodeTypes, bestProfile} = coverage
        const editHref = bestProfile?.id && bestProfile.type
            ? `/edit-download-profile/${bestProfile.type}/${bestProfile.id}`
            : undefined
        const createHref = createDownloadProfileHref(kind, {latestFive})
        const hasExistingProfile = profiles.length > 0

        return (
            <div className="stream-profile-advisory-requirement" key={kind}>
                <div className="stream-profile-advisory-requirement-text">
                    <strong>{kindLabel(kind)}</strong>
                    <span>
                        {hasExistingProfile
                            ? `Existing Download Profile coverage does not include ${episodeTypeLabels(uncoveredEpisodeTypes)}.`
                            : `No enabled ${kindLabel(kind)} Download Profile exists.`}
                    </span>
                </div>
                {canOpenDownloadProfiles && showSlug ? (
                    <div className="stream-profile-advisory-requirement-actions">
                        {editHref ? (
                            <Link
                                className="btn"
                                to={editHref}
                                target="_blank"
                                rel="noreferrer"
                                onClick={handleDownloadProfileAction}
                            >
                                Edit {profileButtonLabel(kind)} profile
                            </Link>
                        ) : null}
                        {createHref ? (
                            <Link
                                className="btn btn-primary"
                                to={createHref}
                                target="_blank"
                                rel="noreferrer"
                                onClick={handleDownloadProfileAction}
                            >
                                {hasExistingProfile ? 'Create another' : 'Create'} {profileButtonLabel(kind)} profile
                            </Link>
                        ) : null}
                    </div>
                ) : null}
            </div>
        )
    }

    if (!useDwStream) {
        const missingRequirements = requiredDownloadKinds
            .map(coverageForKind)
            .filter(({uncoveredEpisodeTypes}) => uncoveredEpisodeTypes.length > 0)

        if (missingRequirements.length > 0) {
            const hasPartialCoverage = missingRequirements.some(
                ({profiles}) => profiles.length > 0
            )

            return (
                <AdvisoryCard
                    title={hasPartialCoverage
                        ? 'Download profile coverage is incomplete'
                        : 'No matching download profile is setup'}
                    helpSummary="What counts as matching download coverage"
                    help={(
                        <>
                            <p>
                                Every media type used by this RSS output needs enabled Download Profile coverage for every selected episode type. Multiple Download Profiles can combine to provide that coverage.
                            </p>
                            <p>
                                Without complete local coverage, episodes missing any required media are left out of the RSS feed because Daily Wire streaming is disabled.
                            </p>
                            {!useDownloads ? (
                                <p>
                                    <strong>Use Downloads</strong> is also disabled on this Stream Profile. Creating or editing a Download Profile from this warning enables it automatically.
                                </p>
                            ) : null}
                        </>
                    )}
                >
                    <p>
                        {hasPartialCoverage
                            ? 'Daily Wire streaming is disabled, but the existing Download Profiles do not fully cover this Stream Profile.'
                            : 'Daily Wire streaming is disabled and no enabled Download Profile matches the media coverage this Stream Profile is setup to include.'}
                    </p>
                    <div className="stream-profile-advisory-requirements">
                        {missingRequirements.map((coverage) => renderCoverageRequirement(coverage))}
                    </div>
                </AdvisoryCard>
            )
        }

        if (!useDownloads) {
            return (
                <AdvisoryCard
                    title="Enable downloads for this Stream Profile"
                    actions={(
                        <button type="button" className="btn btn-primary" onClick={onEnableDownloads}>
                            Enable downloads
                        </button>
                    )}
                >
                    Matching Download Profiles exist, but both Daily Wire streaming and Use Downloads are disabled. Enable downloads so this Stream Profile can serve its local media.
                </AdvisoryCard>
            )
        }

        return null
    }

    if (!usesVideo || videoOutputMode !== 'mp4_hls') return null

    const videoCoverage = coverageForKind('video')
    if (videoCoverage.uncoveredEpisodeTypes.length === 0) return null

    return (
        <AdvisoryCard
            title="Recommended: keep the latest 5 video episodes downloaded"
            helpSummary="Why downloading recent MP4 fallbacks is recommended"
            help={(
                <>
                    <p>
                        The HLS stream can start immediately from The Daily Wire, but the MP4 fallback still has to be prepared completely before playback if no normal video download exists.
                    </p>
                    <p>
                        Keeping the latest 5 episodes downloaded gives recent episodes immediate MP4 fallback delivery while older episodes can still use The Daily Wire.
                    </p>
                    {!useDownloads ? (
                        <p>
                            Creating or editing a Download Profile from this recommendation enables <strong>Use Downloads</strong> automatically.
                        </p>
                    ) : null}
                </>
            )}
        >
            <p>
                MP4 delivery is very slow for episodes that are not already downloaded locally, as those would first need
                to be downloaded before they can be served.
            </p>
            <div className="stream-profile-advisory-requirements">
                {renderCoverageRequirement(videoCoverage, {latestFive: true})}
            </div>
        </AdvisoryCard>
    )
}
