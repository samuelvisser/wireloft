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

type CoverageRequirementProps = {
    coverage: Coverage
    preferredFormat?: string
    showSlug?: string
    canOpenDownloadProfiles: boolean
    useDownloads: boolean
    onEnableDownloads: () => void
    latestFive?: boolean
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

function requiredDownloadKinds(
    preferredFormat?: string,
    videoOutputMode?: string,
): DownloadMediaKind[] {
    if (preferredFormat === 'format_audio_only') return ['audio']
    if (videoOutputMode === 'audio_hls') return ['audio', 'hls']
    if (videoOutputMode === 'audio_mp4') return ['audio', 'video']
    if (videoOutputMode === 'mp4_hls') return ['video', 'hls']
    return ['video']
}

function matchingProfilesForKind(
    profiles: StreamDownloadProfileDefault[],
    kind: DownloadMediaKind,
) {
    return profiles.filter((profile) => {
        if (profile.enabled === false) return false
        if (kind === 'audio') return profile.preferredFormat === 'format_audio_only'
        if (kind === 'hls') return profile.preferredFormat === 'format_hls'
        return STANDARD_VIDEO_FORMATS.has(profile.preferredFormat)
    })
}

function coverageForKind(
    profiles: StreamDownloadProfileDefault[],
    selectedEpisodeTypes: string[],
    kind: DownloadMediaKind,
): Coverage {
    const matchingProfiles = matchingProfilesForKind(profiles, kind)
    const coveredEpisodeTypes = new Set(
        matchingProfiles.flatMap((profile) => profile.episodeTypes)
    )
    const uncoveredEpisodeTypes = selectedEpisodeTypes.filter(
        (episodeType) => !coveredEpisodeTypes.has(episodeType)
    )
    const bestProfile = [...matchingProfiles].sort((a, b) => {
        const aCoverage = selectedEpisodeTypes.filter((type) => a.episodeTypes.includes(type)).length
        const bCoverage = selectedEpisodeTypes.filter((type) => b.episodeTypes.includes(type)).length
        return bCoverage - aCoverage
    })[0]

    return {
        kind,
        profiles: matchingProfiles,
        uncoveredEpisodeTypes,
        bestProfile,
    }
}

function downloadFormatForKind(
    kind: DownloadMediaKind,
    preferredFormat?: string,
) {
    if (kind === 'audio') return 'format_audio_only'
    if (kind === 'hls') return 'format_hls'
    if (STANDARD_VIDEO_FORMATS.has(preferredFormat ?? '')) return preferredFormat as string
    return 'format_1080p'
}

function createDownloadProfileHref(
    kind: DownloadMediaKind,
    showSlug?: string,
    preferredFormat?: string,
    {latestFive = false}: {latestFive?: boolean} = {},
) {
    if (!showSlug) return undefined

    const params = new URLSearchParams({
        show: showSlug,
        preferredFormat: downloadFormatForKind(kind, preferredFormat),
    })
    if (latestFive) params.set('downloadEpisodeCount', '5')
    return `/add-download-profile?${params.toString()}`
}

function CoverageRequirement({
    coverage,
    preferredFormat,
    showSlug,
    canOpenDownloadProfiles,
    useDownloads,
    onEnableDownloads,
    latestFive = false,
}: CoverageRequirementProps) {
    const {kind, profiles, uncoveredEpisodeTypes, bestProfile} = coverage
    const editHref = bestProfile?.id && bestProfile.type
        ? `/edit-download-profile/${bestProfile.type}/${bestProfile.id}`
        : undefined
    const createHref = createDownloadProfileHref(
        kind,
        showSlug,
        preferredFormat,
        {latestFive},
    )
    const hasExistingProfile = profiles.length > 0
    const handleDownloadProfileAction = () => {
        if (!useDownloads) onEnableDownloads()
    }

    return (
        <div className="stream-profile-advisory-requirement">
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
    const isRssProfile = mode === 'rss'
    const downloadProfilesLoaded = downloadProfileDefaults !== undefined
    const downloadProfiles = downloadProfileDefaults ?? []

    const usesVideo = preferredFormat !== 'format_audio_only'
    const usesDirectMp4Video = usesVideo
        && (videoOutputMode === 'audio_mp4' || videoOutputMode === 'mp4')

    const requiredKinds = requiredDownloadKinds(preferredFormat, videoOutputMode)
    const requiredCoverage = requiredKinds.map((kind) => (
        coverageForKind(downloadProfiles, selectedEpisodeTypes, kind)
    ))
    const missingRequirements = requiredCoverage.filter(
        ({uncoveredEpisodeTypes}) => uncoveredEpisodeTypes.length > 0
    )
    const hasPartialCoverage = missingRequirements.some(
        ({profiles}) => profiles.length > 0
    )
    const videoCoverage = coverageForKind(
        downloadProfiles,
        selectedEpisodeTypes,
        'video',
    )

    const showDirectMp4StreamingWarning = (
        isRssProfile
        && useDwStream
        && usesDirectMp4Video
    )
    const showMissingDownloadProfileWarning = (
        isRssProfile
        && !useDwStream
        && downloadProfilesLoaded
        && missingRequirements.length > 0
    )
    const showEnableDownloadsWarning = (
        isRssProfile
        && !useDwStream
        && downloadProfilesLoaded
        && missingRequirements.length === 0
        && !useDownloads
    )
    const showMp4HlsDownloadRecommendation = (
        isRssProfile
        && useDwStream
        && downloadProfilesLoaded
        && usesVideo
        && videoOutputMode === 'mp4_hls'
        && videoCoverage.uncoveredEpisodeTypes.length > 0
    )

    if (showDirectMp4StreamingWarning) {
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

    if (showMissingDownloadProfileWarning) {
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
                    {missingRequirements.map((coverage) => (
                        <CoverageRequirement
                            key={coverage.kind}
                            coverage={coverage}
                            preferredFormat={preferredFormat}
                            showSlug={showSlug}
                            canOpenDownloadProfiles={canOpenDownloadProfiles}
                            useDownloads={useDownloads}
                            onEnableDownloads={onEnableDownloads}
                        />
                    ))}
                </div>
            </AdvisoryCard>
        )
    }

    if (showEnableDownloadsWarning) {
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

    if (showMp4HlsDownloadRecommendation) {
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
                    <CoverageRequirement
                        coverage={videoCoverage}
                        preferredFormat={preferredFormat}
                        showSlug={showSlug}
                        canOpenDownloadProfiles={canOpenDownloadProfiles}
                        useDownloads={useDownloads}
                        onEnableDownloads={onEnableDownloads}
                        latestFive
                    />
                </div>
            </AdvisoryCard>
        )
    }

    return null
}
