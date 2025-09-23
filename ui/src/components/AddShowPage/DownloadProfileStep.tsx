import DailywireShowCard from './DailywireShowCard'
import DownloadProfile from '../DownloadProfile/DownloadProfile'
import type {ShowTypeValue} from '../../types/show'
import type { SeasonItem } from '../DownloadProfile/DownloadProfileSeries'


type Props = {
  onBack: () => void
  onFinish: () => void
  onCancel: () => void
  showSlug?: string
  showType?: ShowTypeValue | ''
  seasons?: SeasonItem[]
}

export default function DownloadProfileStep({onBack, onFinish, onCancel, showSlug, showType, seasons}: Props) {
  return (
    <div className="wizard-with-aside">
      <div className="wizard-main">
        <DownloadProfile
          showType={showType}
          seasons={seasons}
          onBack={onBack}
          onFinish={onFinish}
          onCancel={onCancel}
        />
      </div>

      {showSlug ? (
        <aside className="wizard-aside" aria-label="Selected show details">
          <DailywireShowCard showSlug={showSlug} />
        </aside>
      ) : null}
    </div>
  )
}
