import { useDailywireShow } from '../../lib/queries'

type Props = {
  slug?: string
  membershipPlan?: string
}

export default function DailywireShowCard({ slug, membershipPlan }: Props) {
  const q = useDailywireShow(slug, membershipPlan)

  // Nothing to show until URL is valid and slug exists
  if (!slug) return null

  if (q.isPending) {
    return (
      <div className="dw-card" aria-busy="true" aria-live="polite">
        <div className="dw-card-body">
          <div className="dw-card-title">Checking show…</div>
          <div className="dw-card-desc">Fetching DailyWire show details</div>
        </div>
      </div>
    )
  }

  if (q.isError) {
    const err = q.error as any
    const msg = (err?.message as string) || 'Failed to load show'
    let code: number | undefined = typeof err?.status === 'number' ? err.status : undefined
    if (!code) {
      const m = msg.match(/HTTP\s+(\d{3})/i)
      if (m) code = parseInt(m[1], 10)
    }

    const codeTextMap: Record<number, string> = {
      400: 'Bad Request',
      401: 'Unauthorized',
      403: 'Forbidden',
      404: 'Not Found',
      408: 'Request Timeout',
      429: 'Too Many Requests',
      500: 'Internal Server Error',
      502: 'Bad Gateway',
      503: 'Service Unavailable',
      504: 'Gateway Timeout',
    }
    const codeText = code ? (codeTextMap[code] || 'HTTP Error') : 'HTTP Error'
    const longLine = code === 404 ? 'That show does not exist on The Dailywire' : (code ? `${code} ${codeText}` : msg)

    return (
      <div className="dw-card dw-card-error" role="alert" aria-live="polite">
        <div className="dw-card-media">
          <div className="dw-card-img dw-card-img-error">
            <span className="dw-error-code">{code ?? 'ERR'}</span>
          </div>
        </div>
        <div className="dw-card-body">
          <div className="dw-card-title">We could not find that show</div>
          <div className="dw-card-author">HTTP error code {code ?? 'unknown'}</div>
          <div className="dw-card-desc">{longLine}</div>
        </div>
      </div>
    )
  }

  const data: any = q.data
  if (!data) return null

  const author = data?.author_name ?? data?.authorName
  const portraitUrl: string | undefined = data?.thumbnail?.portrait ?? undefined
  const bgUrl: string | undefined = data?.background_image || data?.backgroundImage || data?.thumbnail?.landscape || portraitUrl

  return (
    <div className="dw-card" role="region" aria-label="Show preview">
      {bgUrl ? <div className="dw-card-bg" style={{ backgroundImage: `url(${bgUrl})` }} /> : null}
      <div className="dw-card-media">
        {portraitUrl ? (
          <img className="dw-card-img" src={portraitUrl} alt={`${data.title} portrait`} />
        ) : (
          <div className="dw-card-img dw-card-img-placeholder" aria-hidden="true" />
        )}
      </div>
      <div className="dw-card-body">
        <div className="dw-card-title">{data.title}</div>
        {author ? <div className="dw-card-author">{author}</div> : null}
        {data.description && <div className="dw-card-desc">{data.description}</div>}
      </div>
    </div>
  )
}
