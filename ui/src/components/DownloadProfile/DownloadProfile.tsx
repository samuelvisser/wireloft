import {useMemo} from 'react'
import DownloadProfilePodcast from './DownloadProfilePodcast'
import DownloadProfileSeries, {type SeasonItem} from './DownloadProfileSeries'
import {ShowTypeReg, type ShowTypeValue} from '../../types/show'

export type DownloadProfileProps = {
  showType?: ShowTypeValue | ''
  seasons?: SeasonItem[]
  onBack: () => void
  onFinish: () => void
  onCancel: () => void
}

export default function DownloadProfile({ showType, seasons: seasonsProp, onBack, onFinish, onCancel }: DownloadProfileProps) {
  // Determine effective type strictly from user selection (step 1)
  const isPodcast = useMemo(() => {
    if (showType === ShowTypeReg.Enum.podcast) return true
    if (showType === ShowTypeReg.Enum.series) return false
    return true // default to podcast if unknown
  }, [showType])

  const seasons: SeasonItem[] = useMemo(() => seasonsProp ?? [], [seasonsProp])

  if (isPodcast) {
    return (
      <DownloadProfilePodcast
        onBack={onBack}
        onFinish={() => onFinish()}
        onCancel={onCancel}
      />
    )
  }

  return (
    <DownloadProfileSeries
      seasons={seasons}
      onBack={onBack}
      onFinish={() => onFinish()}
      onCancel={onCancel}
    />
  )
}
