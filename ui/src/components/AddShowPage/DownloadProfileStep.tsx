import DailywireShowCard from './DailywireShowCard'
import {ShowTypeReg, ShowTypeValue} from '../../types/show'
import SeriesDownloadProfileStep from './DownloadProfileVersions/SeriesDownloadProfileStep'
import PodcastDownloadProfileStep from "./DownloadProfileVersions/PodcastDownloadProfileStep";
import {
    DownloadProfileUnifiedCreateIn, DownloadProfileUnifiedCreateOut
} from "../../types/schemas/show_as_bundle";
import {SeasonDetachedOut} from "../../types/schemas/season";


type Props = {
    value: {
        podcast: Partial<DownloadProfileUnifiedCreateIn>,
        series: Partial<DownloadProfileUnifiedCreateIn>
    }
    onChange: {
        podcast: (v: Partial<DownloadProfileUnifiedCreateIn>) => void,
        series: (v: Partial<DownloadProfileUnifiedCreateIn>) => void,
    }
    onSubmit: {
        podcast: (v: DownloadProfileUnifiedCreateOut) => void,
        series: (v: DownloadProfileUnifiedCreateOut) => void,
    }
    onBack: () => void
    onFinish: () => void
    onCancel: () => void
    showSlug?: string
    showType?: ShowTypeValue | ''
    seasons: SeasonDetachedOut[]
}

export default function DownloadProfileStep({value, onChange, onSubmit, onBack, onFinish, onCancel, showSlug, showType, seasons}: Props) {
    // Return the appropriate step component based on the show type
    return (
        <div className="wizard-with-aside">
            <div className="wizard-main">
                {showType === ShowTypeReg.Enum.podcast ? (
                    <PodcastDownloadProfileStep
                        value={value.podcast}
                        onChange={onChange.podcast}
                        onSubmit={onSubmit.podcast}
                        onBack={onBack}
                        onFinish={onFinish}
                        onCancel={onCancel}
                    />
                ) : (
                    <SeriesDownloadProfileStep
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
