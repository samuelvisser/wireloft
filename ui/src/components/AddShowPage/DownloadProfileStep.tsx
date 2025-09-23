import DailywireShowCard from './DailywireShowCard'
import DownloadProfile from '../DownloadProfile/DownloadProfile'
import type {ShowTypeValue} from '../../types/show'
import type {SeasonItem} from '../DownloadProfile/DownloadProfileSeries'
import {
    DownloadProfilePodcastCreateIn,
    DownloadProfilePodcastCreateOut
} from "../../types/schemas/download_profile_podcast";
import {
    DownloadProfileSeriesCreateIn,
    DownloadProfileSeriesCreateOut
} from "../../types/schemas/download_profile_series";


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

export default function DownloadProfileStep({value, onChange, onSubmit, onBack, onFinish, onCancel, showSlug, showType, seasons}: Props) {
    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                <DownloadProfile
                    value={value}
                    onChange={onChange}
                    onSubmit={onSubmit}
                    showType={showType}
                    seasons={seasons}
                    onBack={onBack}
                    onFinish={onFinish}
                    onCancel={onCancel}
                />
            </div>

            {showSlug ? (
                <aside className="wizard-aside" aria-label="Selected show details">
                    <DailywireShowCard showSlug={showSlug}/>
                </aside>
            ) : null}
        </div>
    )
}
