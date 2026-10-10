import {formatDateTimeForDeadline} from '../../utils/formatting'
import {faIcon} from '../../icons/faIcon'
import ConfirmDialog from '../ConfirmDialog/ConfirmDialog'

const SCHEDULE_PREFERRED_WITHIN_MS = 10 * 60 * 1000

export function shouldPromptForSafeDelay(
    confirmSafeDelayDownload: boolean,
    safeDelayReadyAt: Date | null,
    nowMs = Date.now(),
): boolean {
    return (
        confirmSafeDelayDownload
        && (
            safeDelayReadyAt === null
            || safeDelayReadyAt.getTime() > nowMs
        )
    )
}

export function freezeSafeDelaySchedulePreference(
    current: boolean | null,
    safeDelayReadyAt: Date | null,
    nowMs = Date.now(),
): boolean {
    return current ?? (
        safeDelayReadyAt !== null
        && safeDelayReadyAt.getTime() - nowMs <= SCHEDULE_PREFERRED_WITHIN_MS
    )
}

function RedownloadAfterDelayOption({
    checked,
    disabled,
    onChange,
}: {
    checked: boolean
    disabled: boolean
    onChange: (checked: boolean) => void
}) {
    return (
        <label className="confirm-dialog-option">
            <input
                type="checkbox"
                checked={checked}
                onChange={(event) => onChange(event.target.checked)}
                disabled={disabled}
            />
            <span>Re-download automatically when the safety delay has passed</span>
        </label>
    )
}

export function SafeDelayConfirmDialog({
    open,
    isRetry,
    safeDelayReadyAt,
    schedulePreferred,
    busy,
    submitting,
    redownloadWhenDelayPassed,
    onRedownloadWhenDelayPassedChange,
    onDismiss,
    onSchedule,
    onImmediate,
}: {
    open: boolean
    isRetry: boolean
    safeDelayReadyAt: Date | null
    schedulePreferred: boolean
    busy: boolean
    submitting: 'schedule' | 'immediate' | null
    redownloadWhenDelayPassed: boolean
    onRedownloadWhenDelayPassedChange: (checked: boolean) => void
    onDismiss: () => void
    onSchedule: () => void | Promise<void>
    onImmediate: () => void | Promise<void>
}) {
    const scheduleActionLabel = isRetry ? 'Schedule re-download' : 'Schedule download'
    const immediateActionLabel = isRetry ? 'Re-download now' : 'Download now'
    const safeDelayReadyLabel = safeDelayReadyAt
        ? formatDateTimeForDeadline(safeDelayReadyAt)
        : null

    return (
        <ConfirmDialog
            open={open}
            className="safe-delay-confirm-dialog"
            title="Download before the safety delay has passed?"
            onDismiss={onDismiss}
            icon={faIcon('fass', 'circle-exclamation')}
            dismissOnOverlayClick={!busy}
            cancelButton={{disabled: busy}}
            confirmButton={schedulePreferred ? {
                label: submitting === 'schedule' ? 'Scheduling…' : scheduleActionLabel,
                onClick: onSchedule,
                icon: faIcon('fass', 'clock'),
                disabled: busy,
            } : {
                label: submitting === 'immediate' ? 'Starting…' : immediateActionLabel,
                onClick: onImmediate,
                icon: faIcon('fass', 'download'),
                disabled: busy,
            }}
            secondaryButton={schedulePreferred ? {
                label: submitting === 'immediate' ? 'Starting…' : immediateActionLabel,
                onClick: onImmediate,
                icon: faIcon('fass', 'download'),
                disabled: busy,
            } : {
                label: submitting === 'schedule' ? 'Scheduling…' : scheduleActionLabel,
                onClick: onSchedule,
                icon: faIcon('fass', 'clock'),
                disabled: busy,
            }}
        >
            <p>
                WireLoft&apos;s configured post-publication safety delay has not passed yet. The Daily Wire may still be
                processing this episode, so the current file may be incomplete.
            </p>
            {safeDelayReadyLabel && (
                <p>
                    WireLoft considers this episode safe to download at <strong>{safeDelayReadyLabel}</strong>.
                </p>
            )}
            <p>
                You can schedule it for that time, or download it immediately.
            </p>
            {!schedulePreferred && (
                <RedownloadAfterDelayOption
                    checked={redownloadWhenDelayPassed}
                    disabled={busy}
                    onChange={onRedownloadWhenDelayPassedChange}
                />
            )}
        </ConfirmDialog>
    )
}

export function ImmediateSafeDelayConfirmDialog({
    open,
    isRetry,
    busy,
    submitting,
    redownloadWhenDelayPassed,
    onRedownloadWhenDelayPassedChange,
    onDismiss,
    onImmediate,
}: {
    open: boolean
    isRetry: boolean
    busy: boolean
    submitting: 'schedule' | 'immediate' | null
    redownloadWhenDelayPassed: boolean
    onRedownloadWhenDelayPassedChange: (checked: boolean) => void
    onDismiss: () => void
    onImmediate: () => void | Promise<void>
}) {
    const immediateActionLabel = isRetry ? 'Re-download now' : 'Download now'

    return (
        <ConfirmDialog
            open={open}
            title={isRetry ? 'Re-download before the safety delay?' : 'Download before the safety delay?'}
            onDismiss={onDismiss}
            icon={faIcon('fass', 'circle-exclamation')}
            dismissOnOverlayClick={!busy}
            cancelButton={{disabled: busy}}
            confirmButton={{
                label: submitting === 'immediate' ? 'Starting…' : immediateActionLabel,
                onClick: onImmediate,
                icon: faIcon('fass', 'download'),
                disabled: busy,
            }}
        >
            <p>
                This download will start immediately, before WireLoft considers the episode safely ready.
            </p>
            <RedownloadAfterDelayOption
                checked={redownloadWhenDelayPassed}
                disabled={busy}
                onChange={onRedownloadWhenDelayPassedChange}
            />
        </ConfirmDialog>
    )
}
