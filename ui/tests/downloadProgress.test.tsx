import assert from 'node:assert/strict'
import test from 'node:test'
import {renderToStaticMarkup} from 'react-dom/server'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@fortawesome/free-solid-svg-icons'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import FrontendPuller from '../src/lib/puller'
import {isPublicationDelayWait, presentDownloadProgress} from '../src/lib/downloadProgress'
import {presentOperationProgress} from '../src/lib/operationProgress'
import {invalidateForOperation} from '../src/lib/operationDefinitions'
import {reconcileOperationSnapshots} from '../src/lib/operationSnapshots'
import ProgressBar from '../src/components/common/ProgressBar'
import DownloadProgressStatus from '../src/components/DownloadProgress/DownloadProgressStatus'
import DownloadProgressActionItem from '../src/components/DownloadProgress/DownloadProgressActionItem'
import DownloadProgressButton from '../src/components/DownloadProgress/DownloadProgressButton'
import type {TaskOperationRead} from '../src/types/schemas/operation'
import {FrontendPullReadSchema, FrontendPullVersionSchema} from '../src/types/schemas/puller'
library.add(fas)

function operation(extra: Partial<TaskOperationRead> = {}): TaskOperationRead {
    return {id:'download',kind:'media.download',source:'UI',resourceType:'media_download',resourceId:1,title:'Example',status:'RUNNING',progress:99,progressCurrent:0,progressTotal:1,createdAt:'2026-09-30T00:00:00Z',updatedAt:'2026-09-30T00:00:01Z',...extra}
}
function execution(phase = 'transferring', main = 'media', fraction: number | null = .42) {
    const stage = (id: string, code: string) => ({id,code,phase,resource:'none',weight:1,asset_id:null,state:'running',started_at:1,finished_at:null,fraction:id==='media'?fraction:null,bytes_received:42,total_bytes:100,segments_done:null,segments_total:null,wait:null,waits:[],last_activity_at:2,deadline_at:null})
    return {attempt_id:'attempt-1',sequence:3,phase,main_activity:main,stages:[stage('media','download_media'),stage('embed','embed_artwork_metadata')],started_at:1,heartbeat_at:2,last_activity_at:2,primary_transfer_complete:phase==='finishing',canceling:false,preparation_steps:[],warnings:[]}
}
function active(phase='transferring',main='media',fraction: number|null=.42) {
    return operation({progressMeta:{download:execution(phase,main,fraction)}})
}
for (const [phase, main] of [['preparing','media'],['finishing','embed']]) test(`${phase} never uses the task percentage`,()=>{
    const view=presentDownloadProgress(undefined,active(phase,main))
    assert.equal(view.mode,'indeterminate');assert.equal(view.percent,null)
})
test('individual percentage describes the network only',()=>{
    const view=presentDownloadProgress(undefined,active())
    assert.equal(view.percent,42);assert.equal(view.label,'42%')
})
test('audio transfer detail uses human-readable downloaded and total sizes',()=>{
    const snapshot=execution()
    Object.assign(snapshot.stages[0], {
        bytes_received: Math.round(50.5 * 1024 ** 2),
        total_bytes: Math.round(67.8 * 1024 ** 2),
    })
    const view=presentDownloadProgress(
        {preferredFormat:'format_audio_only'} as any,
        operation({progressMeta:{download:snapshot}}),
    )
    assert.equal(view.detail,'Primary media transfer: 50.5 MiB / 67.8 MiB downloaded.')
})
test('non-audio direct transfer detail keeps the byte-count wording',()=>{
    const view=presentDownloadProgress(undefined,active())
    assert.equal(view.detail,'Primary media transfer: 42/100 bytes.')
})
test('unknown transfer size is indeterminate',()=>assert.equal(presentDownloadProgress(undefined,active('transferring','media',null)).mode,'indeterminate'))
test('global cooldown is not flattened into 0%',()=>{
    const view=presentDownloadProgress(undefined,operation({status:'WAITING',progressMeta:{wait_state:{reason:'daily_wire_request_cooldown'}}}))
    assert.equal(view.mode,'waiting');assert.equal(view.label,'Cooldown...');assert.equal(view.percent,null)
})
test('post-publication wait within 12 hours shows only its delay time inline',()=>{
    const originalNow=Date.now
    const now=Date.UTC(2026,9,7,18,0)
    Date.now=()=>now
    try {
        const until=(now+11*60*60*1000)/1000
        const op=operation({status:'WAITING',progressMeta:{wait_state:{reason:'publication_delay',until}}})
        const view=presentDownloadProgress(undefined,op)
        assert.equal(view.mode,'waiting');assert.match(view.label,/^Delayed until /);assert.doesNotMatch(view.label,/2026/)
        assert.equal(view.compactLabel,'Delayed...');assert.equal(view.percent,null)
        const markup=renderToStaticMarkup(<DownloadProgressStatus download={{id:1,presentation:view,operation:op} as any}/>)
        assert.match(markup,/Delayed until /);assert.doesNotMatch(markup,/2026/)
    } finally {
        Date.now=originalNow
    }
})
test('post-publication wait at least 12 hours away includes the date',()=>{
    const originalNow=Date.now
    const now=Date.UTC(2026,9,7,18,0)
    Date.now=()=>now
    try {
        const until=(now+12*60*60*1000)/1000
        const view=presentDownloadProgress(undefined,operation({status:'WAITING',progressMeta:{wait_state:{reason:'publication_delay',until}}}))
        assert.match(view.label,/^Delayed until /);assert.match(view.label,/2026/)
    } finally {
        Date.now=originalNow
    }
})
test('post-publication wait without a deadline is still presented as delayed',()=>{
    const view=presentDownloadProgress(undefined,operation({status:'WAITING',progressMeta:{wait_state:{reason:'publication_delay'}}}))
    assert.equal(view.mode,'waiting');assert.equal(view.label,'Delayed...');assert.equal(view.percent,null)
})
test('only a publication-delay wait is eligible for the manual override action',()=>{
    assert.equal(
        isPublicationDelayWait(operation({status:'WAITING',progressMeta:{wait_state:{reason:'publication_delay'}}})),
        true,
    )
    assert.equal(
        isPublicationDelayWait(operation({status:'WAITING',progressMeta:{wait_state:{reason:'daily_wire_request_cooldown'}}})),
        false,
    )
    assert.equal(
        isPublicationDelayWait(operation({status:'RUNNING',progressMeta:{wait_state:{reason:'publication_delay'}}})),
        false,
    )
})
test('sidecar wait does not hide an active media transfer',()=>{
    const snapshot=execution();snapshot.stages[1].wait={reason:'upstream_retry'} as any
    const view=presentDownloadProgress(undefined,operation({progressMeta:{download:snapshot}}))
    assert.equal(view.mode,'determinate');assert.equal(view.percent,42)
})
test('old available artifact cannot hide a re-download',()=>{
    const view=presentDownloadProgress({artifactStatus:'available'} as any,active())
    assert.equal(view.active,true);assert.equal(view.outcome,undefined)
})
test('completed transfer switches to finishing, not success',()=>{
    const view=presentDownloadProgress(undefined,active('finishing','embed',1))
    assert.equal(view.active,true);assert.equal(view.percent,null);assert.equal(view.compactLabel,'Embedding...')
})
test('bulk has its own estimate and completion counts',()=>{
    const view=presentOperationProgress(operation({kind:'media.bulk_retry',progress:55,progressMeta:{batch:{requested:2,completed:1,finishing:1}}}))!
    assert.equal(view.percent,55);assert.equal(view.label,'~55%');assert.equal(view.estimated,true)
    assert.match(view.detail,/1\/2 complete; 1 finishing/)
})
test('media download completion invalidates cached history for that download', async()=>{
    const client=new QueryClient()
    const history50=['mediaDownloadHistory',1,50] as const
    const history100=['mediaDownloadHistory',1,100] as const
    const otherHistory=['mediaDownloadHistory',2,50] as const
    client.setQueryData(history50,{items:[]})
    client.setQueryData(history100,{items:[]})
    client.setQueryData(otherHistory,{items:[]})
    await invalidateForOperation(client,operation({status:'SUCCEEDED'}))
    assert.equal(client.getQueryState(history50)?.isInvalidated,true)
    assert.equal(client.getQueryState(history100)?.isInvalidated,true)
    assert.equal(client.getQueryState(otherHistory)?.isInvalidated,false)
})
test('application version remains readable from a future incompatible pull payload',()=>{
    const incompatible={appVersion:'2.0.0',mode:'future',data:null}
    assert.equal(FrontendPullVersionSchema.parse(incompatible).appVersion,'2.0.0')
    assert.throws(()=>FrontendPullReadSchema.parse(incompatible))
})
test('stale sequence is rejected but newer attempt and removals win',()=>{
    const previous={mode:'fast' as const,data:{operations:[active()]}}
    const stale=active();(stale.progressMeta!.download as any).sequence=2
    assert.equal(reconcileOperationSnapshots(previous,{...previous,data:{operations:[stale]}}).data.operations[0],previous.data.operations[0])
    const next=active();Object.assign(next.progressMeta!.download as any,{attempt_id:'attempt-2',started_at:5,sequence:1})
    assert.equal(reconcileOperationSnapshots(previous,{...previous,data:{operations:[next]}}).data.operations[0],next)
    assert.equal(reconcileOperationSnapshots(previous,{...previous,data:{operations:[]}}).data.operations.length,0)
})
test('indeterminate progress omits a false accessible numeric value',()=>{
    const markup=renderToStaticMarkup(<ProgressBar mode="indeterminate" value={null} ariaLabel="Preparing"/>)
    assert.match(markup,/role="progressbar"/);assert.doesNotMatch(markup,/aria-valuenow/)
    assert.match(renderToStaticMarkup(<ProgressBar mode="determinate" value={42}/>),/aria-valuenow="42"/)
})
test('all three layouts render the same activity',()=>{
    const op=active('finishing','embed',1)
    const presentation=presentDownloadProgress(undefined,op)
    const download={id:1,presentation,operation:op} as any
    const client=new QueryClient()
    const button=renderToStaticMarkup(<QueryClientProvider client={client}><FrontendPuller><DownloadProgressButton download={download} onStart={()=>{}}/></FrontendPuller></QueryClientProvider>)
    const standalone=renderToStaticMarkup(<DownloadProgressStatus download={download}/>)
    const menu=renderToStaticMarkup(<DownloadProgressActionItem presentation={presentation}/>)
    assert.match(button,/Embedding\.\.\./);assert.match(menu,/Embedding\.\.\./);assert.match(standalone,/Embedding artwork and metadata/)
    assert.doesNotMatch(button,/aria-valuenow/);assert.doesNotMatch(standalone,/aria-valuenow/)
})
test('download progress button can name the completed artifact',()=>{
    const presentation=presentDownloadProgress({artifactStatus:'available'} as any)
    const download={id:1,presentation} as any
    const client=new QueryClient()
    const markup=renderToStaticMarkup(
        <QueryClientProvider client={client}>
            <FrontendPuller>
                <DownloadProgressButton download={download} downloadedLabel="Trailer downloaded" onStart={()=>{}}/>
            </FrontendPuller>
        </QueryClientProvider>,
    )
    assert.match(markup,/Trailer downloaded/)
    assert.doesNotMatch(markup,/>Downloaded</)
})
test('idle re-download uses the same plain icon button treatment as ledger actions',()=>{
    const presentation=presentDownloadProgress({artifactStatus:'available'} as any)
    const download={id:1,presentation} as any
    const client=new QueryClient()
    const markup=renderToStaticMarkup(
        <QueryClientProvider client={client}>
            <FrontendPuller>
                <DownloadProgressButton download={download} onStart={()=>{}}/>
            </FrontendPuller>
        </QueryClientProvider>,
    )
    assert.match(markup,/class="icon-btn"/)
    assert.doesNotMatch(markup,/class="progress-button-control"/)
})
