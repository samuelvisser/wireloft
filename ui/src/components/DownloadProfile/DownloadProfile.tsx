import {useMemo} from 'react'
import DownloadProfilePodcast from './DownloadProfilePodcast'
import DownloadProfileSeries, {type SeasonItem} from './DownloadProfileSeries'
import {ShowTypeReg, type ShowTypeValue} from '../../types/show'
import {
    DownloadProfilePodcastCreateIn,
    DownloadProfilePodcastCreateOut
} from "../../types/schemas/download_profile_podcast";
import {
    DownloadProfileSeriesCreateIn,
    DownloadProfileSeriesCreateOut
} from "../../types/schemas/download_profile_series";

export type DownloadProfileProps = {
    value: {
        podcast: Partial<DownloadProfilePodcastCreateIn>,
        series: Partial<DownloadProfileSeriesCreateIn>
    }
    onChange: {
        podcast: (v: Partial<DownloadProfilePodcastCreateIn>) => void,
        series: (v: Partial<DownloadProfileSeriesCreateIn>) => void,
    }
    onSubmit: {
        podcast: (v: DownloadProfilePodcastCreateOut) => void,
        series: (v: DownloadProfileSeriesCreateOut) => void,
    }
    showType?: ShowTypeValue | ''
    seasons?: SeasonItem[]
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
}

export default function DownloadProfile({
                                            value, onChange, onSubmit,
                                            showType,
                                            seasons: seasonsProp,
                                            onBack,
                                            onFinish,
                                            onCancel
                                        }: DownloadProfileProps) {
    // Determine the show type from user selection (step 1)
    const isPodcast = useMemo(() => {
        if (showType === ShowTypeReg.Enum.podcast) return true
        return showType !== ShowTypeReg.Enum.series;      // default to podcast if unknown
    }, [showType])

    const seasons: SeasonItem[] = useMemo(() => seasonsProp ?? [], [seasonsProp])

    if (isPodcast) {
        return (
            <DownloadProfilePodcast
                value={value.podcast}
                onChange={onChange.podcast}
                onSubmit={onSubmit.podcast}
                onBack={onBack}
                onFinish={onFinish}
                onCancel={onCancel}
            />
        )
    }

    return (
        <DownloadProfileSeries
            value={value.series}
            onChange={onChange.series}
            onSubmit={onSubmit.series}
            seasons={seasons}
            onBack={onBack}
            onFinish={onFinish}
            onCancel={onCancel}
        />
    )
}
