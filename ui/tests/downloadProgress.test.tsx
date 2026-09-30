import assert from 'node:assert/strict'
import test from 'node:test'
import {renderToStaticMarkup} from 'react-dom/server'
import {library} from '@fortawesome/fontawesome-svg-core'
import {fas} from '@fortawesome/free-solid-svg-icons'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import FrontendPuller from '../src/lib/puller'
import {presentDownloadProgress} from '../src/lib/downloadProgress'
import {presentOperationProgress} from '../src/lib/operationProgress'
import {reconcileOperationSnapshots} from '../src/lib/operationSnapshots'
import ProgressBar from '../src/components/common/ProgressBar'
import DownloadProgressStatus from '../src/components/DownloadProgress/DownloadProgressStatus'
import DownloadProgressActionItem from '../src/components/DownloadProgress/DownloadProgressActionItem'
import DownloadProgressButton from '../src/components/DownloadProgress/DownloadProgressButton'
import type {TaskOperationRead} from '../src/types/schemas/operation'
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
test('unknown transfer size is indeterminate',()=>assert.equal(presentDownloadProgress(undefined,active('transferring','media',null)).mode,'indeterminate'))
test('global cooldown is not flattened into 0%',()=>{
    const view=presentDownloadProgress(undefined,operation({status:'WAITING',progressMeta:{wait_state:{reason:'daily_wire_request_cooldown'}}}))
    assert.equal(view.mode,'waiting');assert.equal(view.label,'Cooldown...');assert.equal(view.percent,null)
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
