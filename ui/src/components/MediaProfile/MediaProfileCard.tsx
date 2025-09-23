import {MediaProfileRead} from '../../types/schemas/media_profile'
import {PreferredFormatReg} from "../../types/media_profile";

export type MediaProfileCardProps = {
  profile: MediaProfileRead
  selected?: boolean
  onClick?: () => void
}

export default function MediaProfileCard({ profile, selected = false, onClick }: MediaProfileCardProps) {
  return (
    <button
      type="button"
      role="listitem"
      className={selected ? 'card selected' : 'card'}
      aria-pressed={selected}
      onClick={onClick}
    >
      <div className="card-title">{profile.name}</div>
      <div className="card-sub">{profile.outputTemplate}</div>
      <div className="card-meta">
        <span>{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</span>
        <span>• {profile.downloadSeriesImages ? 'Series images ✓' : 'Series images ✕'}</span>
      </div>
    </button>
  )
}
