import {useOperations} from '../OperationNotifier/OperationNotifier'
import './BackgroundMigrationBanner.css'


const ACTIVE_STATUSES = new Set(['QUEUED', 'RUNNING', 'WAITING'])


export default function BackgroundMigrationBanner() {
  const {operations} = useOperations()
  const operation = operations.find((candidate) => (
    candidate.kind === 'system.background_migrations'
    && ACTIVE_STATUSES.has(candidate.status)
  ))

  if (!operation) return null

  const progress = operation.progress ?? 0

  return (
    <aside className="background-migration-banner" role="status" aria-live="polite">
      <strong>
        Background migration in progress
        {progress > 0 ? ` — ${progress}%` : ''}
      </strong>
      <p>
        A background migration is currently running. WireLoft might be a little slow for a few
        minutes. Please keep WireLoft running while the migration is in progress.
      </p>
      {operation.message && operation.message !== 'Running' && (
        <span>{operation.message}</span>
      )}
    </aside>
  )
}
