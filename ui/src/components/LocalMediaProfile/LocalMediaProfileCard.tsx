import {LocalMediaProfileRead} from '../../types/schemas/local_media_profile'
import {LocalMediaProfileTypeReg, PreferredFormatReg} from "../../types/local_media_profile";

export type LocalMediaProfileCardProps = {
  profile: LocalMediaProfileRead
  selected?: boolean
  onClick?: () => void
}

export default function LocalMediaProfileCard({ profile, selected = false, onClick }: LocalMediaProfileCardProps) {
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
        <span>{LocalMediaProfileTypeReg.getLabelLoose(profile.type)}</span>
        <span>{PreferredFormatReg.getLabelLoose(profile.preferredFormat)}</span>
      </div>
    </button>
  )
}
