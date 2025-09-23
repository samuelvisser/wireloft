import {useMemo} from 'react'
import {useDailywireShow} from '../../lib/queries'
import DownloadProfilePodcast from './DownloadProfilePodcast'
import DownloadProfileSeries, {type SeasonItem} from './DownloadProfileSeries'
import {ShowTypeReg, type ShowTypeValue} from '../../types/show'

export type DownloadProfileProps = {
  showSlug?: string
  showType?: ShowTypeValue | ''
  onBack: () => void
  onFinish: () => void
  onCancel: () => void
}

export default function DownloadProfile({ showSlug, showType, onBack, onFinish, onCancel }: DownloadProfileProps) {
  const dw = useDailywireShow(showSlug)

  // Determine effective type: prefer explicit showType from step 1; fall back to Dailywire inference
  const isPodcast = useMemo(() => {
    if (showType === ShowTypeReg.Enum.podcast) return true
    if (showType === ShowTypeReg.Enum.series) return false
    const anyData: any = dw.data
    const v = (anyData?.probableShowType ?? anyData?.probable_show_type) as string | undefined
    return v === 'podcast'
  }, [dw.data, showType])

  const seasons: SeasonItem[] = useMemo(() => {
    const arr: any[] = (dw.data?.seasons as any[]) || []
    return arr.map((s: any) => ({
      slug: s?.slug ?? s?.slug ?? '',
      name: s?.name ?? s?.name ?? s?.slug ?? 'Unknown',
    })).filter(s => !!s.slug)
  }, [dw.data])

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
