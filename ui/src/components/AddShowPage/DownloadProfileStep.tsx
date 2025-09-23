import DailywireShowCard from './DailywireShowCard'
import {ShowTypeReg, ShowTypeValue} from '../../types/show'
import DownloadProfileSeriesStep, {SeasonItem} from './DownloadProfileVersions/DownloadProfileSeriesStep'
import {
    DownloadProfilePodcastCreateIn,
    DownloadProfilePodcastCreateOut
} from "../../types/schemas/download_profile_podcast";
import {
    DownloadProfileSeriesCreateIn,
    DownloadProfileSeriesCreateOut
} from "../../types/schemas/download_profile_series";
import {useMemo} from "react";
import DownloadProfilePodcastStep from "./DownloadProfileVersions/DownloadProfilePodcastStep";


type Props = {
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
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
    showSlug?: string
    showType?: ShowTypeValue | ''
    seasons?: SeasonItem[]
}

export default function DownloadProfileStep({
                                                value, onChange, onSubmit, onBack, onFinish, onCancel,
                                                showSlug, showType, seasons: seasonsProp
                                            }: Props) {
    // Determine the show type from user selection (step 1)
    const isPodcast = useMemo(() => {
        if (showType === ShowTypeReg.Enum.podcast) return true
        return showType !== ShowTypeReg.Enum.series;      // default to podcast if unknown
    }, [showType])

    // Prepare seasons
    const seasons: SeasonItem[] = useMemo(() => seasonsProp ?? [], [seasonsProp])

    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                {isPodcast ? (
                    <DownloadProfilePodcastStep
                        value={value.podcast}
                        onChange={onChange.podcast}
                        onSubmit={onSubmit.podcast}
                        onBack={onBack}
                        onFinish={onFinish}
                        onCancel={onCancel}
                    />
                ) : (
                    <DownloadProfileSeriesStep
                        value={value.series}
                        onChange={onChange.series}
                        onSubmit={onSubmit.series}
                        seasons={seasons}
                        onBack={onBack}
                        onFinish={onFinish}
                        onCancel={onCancel}
                    />
                )}
            </div>

            {showSlug ? (
                <aside className="wizard-aside" aria-label="Selected show details">
                    <DailywireShowCard showSlug={showSlug}/>
                </aside>
            ) : null}
        </div>
    )
}
