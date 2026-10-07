import assert from 'node:assert/strict'
import test from 'node:test'
import {renderToStaticMarkup} from 'react-dom/server'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@fortawesome/free-solid-svg-icons'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'

import {EnsureSafeDelayToggle} from '../src/components/Settings/DownloadsSettingsTab'
import {EpisodeDownloadRow} from '../src/components/Episode/EpisodeDownloadRow'
import {
    ImmediateSafeDelayConfirmDialog,
    SafeDelayConfirmDialog,
    freezeSafeDelaySchedulePreference,
    shouldPromptForSafeDelay,
} from '../src/components/Episode/SafeDelayDownloadDialogs'
import {presentDownloadProgress} from '../src/lib/downloadProgress'
import {formatDate, formatTime} from '../src/utils/formatting'
import type {TaskOperationRead} from '../src/types/schemas/operation'

library.add(fas)

function operation(reason: string, status = 'WAITING'): TaskOperationRead {
    return {
        id: `download-${reason}`,
        kind: 'media.download',
        source: 'SYSTEM',
        resourceType: 'media_download',
        resourceId: 1,
        title: 'Example download',
        status,
        progress: null,
        progressCurrent: 0,
        progressTotal: 1,
        context: {},
        progressMeta: {wait_state: {reason}},
        createdAt: '2026-10-07T07:00:00Z',
        updatedAt: '2026-10-07T07:00:01Z',
    }
}

function downloadFor(reason: string, status = 'WAITING') {
    const op = operation(reason, status)
    return {
        id: 1,
        localMediaProfileId: 7,
        presentation: presentDownloadProgress(undefined, op),
        operation: op,
    } as any
}

function renderDownloadRow(reason: string, status = 'WAITING') {
    const client = new QueryClient()
    return renderToStaticMarkup(
        <QueryClientProvider client={client}>
            <EpisodeDownloadRow
                profile={{id: 7, name: 'Audio', preferredFormat: 'format_audio_only'} as any}
                download={downloadFor(reason, status)}
                episodeSlug="edge-case-episode"
                confirmCountdownDownload={false}
                confirmSafeDelayDownload={true}
                safeDelayReadyAt={new Date('2026-10-07T08:00:00Z')}
            />
        </QueryClientProvider>,
    )
}

function buttonClassForLabel(markup: string, label: string): string {
    const labelIndex = markup.indexOf(label)
    assert.notEqual(labelIndex, -1, `Expected button label "${label}"`)
    const buttonStart = markup.lastIndexOf('<button', labelIndex)
    const buttonEnd = markup.indexOf('</button>', buttonStart)
    assert.ok(buttonStart >= 0 && buttonEnd >= labelIndex, `Expected "${label}" inside a button`)
    const button = markup.slice(buttonStart, buttonEnd)
    return /class="([^"]+)"/.exec(button)?.[1] ?? ''
}

function renderSafeDelayDialog({
    schedulePreferred,
    isRetry = false,
    checked = true,
    safeDelayReadyAt = new Date('2026-10-07T08:00:00Z'),
}: {
    schedulePreferred: boolean
    isRetry?: boolean
    checked?: boolean
    safeDelayReadyAt?: Date | null
}) {
    return renderToStaticMarkup(
        <SafeDelayConfirmDialog
            open
            isRetry={isRetry}
            safeDelayReadyAt={safeDelayReadyAt}
            schedulePreferred={schedulePreferred}
            busy={false}
            submitting={null}
            redownloadWhenDelayPassed={checked}
            onRedownloadWhenDelayPassedChange={() => {}}
            onDismiss={() => {}}
            onSchedule={() => {}}
            onImmediate={() => {}}
        />,
    )
}

function renderImmediateSafeDelayDialog({
    isRetry = false,
    checked = true,
}: {
    isRetry?: boolean
    checked?: boolean
}) {
    return renderToStaticMarkup(
        <ImmediateSafeDelayConfirmDialog
            open
            isRetry={isRetry}
            busy={false}
            submitting={null}
            redownloadWhenDelayPassed={checked}
            onRedownloadWhenDelayPassedChange={() => {}}
            onDismiss={() => {}}
            onImmediate={() => {}}
        />,
    )
}

test('Ensure Safe Delay is hidden when automatic delay is zero', () => {
    const hidden = renderToStaticMarkup(
        <EnsureSafeDelayToggle
            delayMinutes={0}
            checked={false}
            onChange={() => {}}
        />,
    )
    assert.equal(hidden, '')

    const shown = renderToStaticMarkup(
        <EnsureSafeDelayToggle
            delayMinutes={10}
            checked={false}
            onChange={() => {}}
        />,
    )
    assert.match(shown, /Ensure Safe Delay/)
})

test('pre-delay dialog shows only the time when the deadline is less than 12 hours away', () => {
    const originalNow = Date.now
    const now = Date.parse('2026-10-07T07:00:00Z')
    Date.now = () => now
    try {
        const readyAt = new Date(now + 11 * 60 * 60 * 1000)
        const markup = renderSafeDelayDialog({schedulePreferred: true, safeDelayReadyAt: readyAt})
        assert.ok(markup.includes(formatTime(readyAt)))
        assert.doesNotMatch(markup, /2026/)
    } finally {
        Date.now = originalNow
    }
})

test('pre-delay dialog includes the date when the deadline is at least 12 hours away', () => {
    const originalNow = Date.now
    const now = Date.parse('2026-10-07T07:00:00Z')
    Date.now = () => now
    try {
        const readyAt = new Date(now + 12 * 60 * 60 * 1000)
        const markup = renderSafeDelayDialog({schedulePreferred: true, safeDelayReadyAt: readyAt})
        assert.ok(markup.includes(formatDate(readyAt)))
        assert.match(markup, /2026/)
    } finally {
        Date.now = originalNow
    }
})

test('pre-delay dialog uses the wider safety-delay modal', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: true})
    assert.match(markup, /class="modal safe-delay-confirm-dialog"/)
})

test('schedule is primary when the safety deadline is ten minutes or less away', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: true})
    assert.equal(buttonClassForLabel(markup, 'Schedule download'), 'btn btn-primary')
    assert.equal(buttonClassForLabel(markup, 'Download now'), 'btn')
})

test('download now is primary when the safety deadline is more than ten minutes away', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: false})
    assert.equal(buttonClassForLabel(markup, 'Download now'), 'btn btn-primary')
    assert.equal(buttonClassForLabel(markup, 'Schedule download'), 'btn')
})

test('re-download dialog uses re-download-specific action labels', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: true, isRetry: true})
    assert.match(markup, /Schedule re-download/)
    assert.match(markup, /Re-download now/)
})

test('schedule-primary choice hides the replacement checkbox', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: true, checked: true})
    assert.doesNotMatch(markup, /re-download automatically when the safety delay has passed/i)
    assert.doesNotMatch(markup, /type="checkbox"/)
})

test('download-now-primary choice shows the replacement checkbox', () => {
    const markup = renderSafeDelayDialog({schedulePreferred: false, checked: true})
    assert.match(markup, /re-download automatically when the safety delay has passed/i)
    assert.match(markup, /type="checkbox"[^>]*checked=""/)
})

test('second-stage immediate confirmation shows the replacement checkbox', () => {
    const markup = renderImmediateSafeDelayDialog({checked: true})
    assert.match(markup, /Download before the safety delay\?/)
    assert.match(markup, /Re-download automatically when the safety delay has passed/)
    assert.match(markup, /type="checkbox"[^>]*checked=""/)
    assert.equal(buttonClassForLabel(markup, 'Download now'), 'btn btn-primary')
})

test('second-stage immediate re-download uses the re-download action', () => {
    const markup = renderImmediateSafeDelayDialog({isRetry: true, checked: true})
    assert.match(markup, /Re-download before the safety delay\?/)
    assert.equal(buttonClassForLabel(markup, 'Re-download now'), 'btn btn-primary')
})

test('ten-minute preference calculation keeps the schedule action at the boundary', () => {
    const now = Date.parse('2026-10-07T07:00:00Z')
    assert.equal(
        freezeSafeDelaySchedulePreference(null, new Date(now + 10 * 60 * 1000), now),
        true,
    )
    assert.equal(
        freezeSafeDelaySchedulePreference(null, new Date(now + 10 * 60 * 1000 + 1), now),
        false,
    )
})

test('primary choice stays frozen after first display but reload recalculates it', () => {
    const openedAt = Date.parse('2026-10-07T07:00:00Z')
    const readyAt = new Date('2026-10-07T07:11:00Z')

    const firstChoice = freezeSafeDelaySchedulePreference(null, readyAt, openedAt)
    assert.equal(firstChoice, false)

    const nineMinutesRemaining = openedAt + 2 * 60 * 1000
    assert.equal(
        freezeSafeDelaySchedulePreference(firstChoice, readyAt, nineMinutesRemaining),
        false,
    )

    // A page reload remounts the row, so there is no frozen prior choice.
    assert.equal(
        freezeSafeDelaySchedulePreference(null, readyAt, nineMinutesRemaining),
        true,
    )
})

test('stale API readiness does not reopen the warning after the actual deadline passes', () => {
    const readyAt = new Date('2026-10-07T07:10:00Z')
    assert.equal(
        shouldPromptForSafeDelay(true, readyAt, Date.parse('2026-10-07T07:09:59Z')),
        true,
    )
    assert.equal(
        shouldPromptForSafeDelay(true, readyAt, Date.parse('2026-10-07T07:10:00Z')),
        false,
    )
})

test('scheduled publication-delay wait replaces the normal download button with status plus override', () => {
    const markup = renderDownloadRow('publication_delay')
    assert.match(markup, /Delayed\.\.\./)
    assert.doesNotMatch(markup, /aria-label="Download Audio"/)
    assert.match(markup, /aria-label="Download Audio now"/)
})

test('The Daily Wire cooldown wait does not expose the manual override', () => {
    const markup = renderDownloadRow('daily_wire_request_cooldown')
    assert.match(markup, /Cooldown\.\.\./)
    assert.doesNotMatch(markup, /aria-label="Download Audio now"/)
})

test('other waiting states do not expose the manual override', () => {
    const markup = renderDownloadRow('retry_backoff')
    assert.doesNotMatch(markup, /aria-label="Download Audio now"/)
})

test('an active non-waiting download never exposes the publication-delay override', () => {
    const markup = renderDownloadRow('publication_delay', 'RUNNING')
    assert.doesNotMatch(markup, /aria-label="Download Audio now"/)
})
