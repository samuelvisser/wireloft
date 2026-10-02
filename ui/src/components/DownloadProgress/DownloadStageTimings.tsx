import {DownloadExecutionSchema} from '../../types/schemas/download_execution'
import {activityLabel} from '../../lib/downloadProgress'
import {waitingPresentation} from '../../lib/progressPresentation'

function duration(seconds: number): string {
    return seconds < 60 ? `${Math.max(0, seconds).toFixed(1)} s` : `${Math.floor(seconds / 60)} m ${Math.round(seconds % 60)} s`
}

/** Durations are concurrent activity times, never an additive wall-clock total. */
export default function DownloadStageTimings({value}: {value: unknown}) {
    const result = DownloadExecutionSchema.safeParse(value)
    if (!result.success) return null
    const snapshot = result.data
    return <details className="download-stage-timings">
        <summary>Execution stages</summary>
        <p>Activities may overlap. Their durations do not add up to the total elapsed time.</p>
        <table><thead><tr><th>Activity</th><th>Duration</th><th>Outcome / waiting</th></tr></thead>
            <tbody>{snapshot.stages.filter(stage => stage.started_at !== null).map(stage => <tr key={stage.id}>
                <td>{activityLabel(stage)}</td>
                <td>{duration((stage.finished_at ?? snapshot.heartbeat_at) - stage.started_at!)}</td>
                <td>{stage.state}{stage.waits.map((wait, index) => <div key={index}>
                    {waitingPresentation(wait.reason).label}: {duration((wait.finished_at ?? snapshot.heartbeat_at) - (wait.started_at ?? snapshot.heartbeat_at))}
                </div>)}</td>
            </tr>)}</tbody>
        </table>
        {!!snapshot.preparation_steps.length && <p>{snapshot.preparation_steps.map(step => `${activityLabel({code: step.code})}: ${duration(step.finished_at - step.started_at)}`).join(' / ')}</p>}
        {snapshot.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
    </details>
}
