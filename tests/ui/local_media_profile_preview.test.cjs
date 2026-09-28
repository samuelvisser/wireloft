// Run with: node --test tests/ui/local_media_profile_preview.test.cjs
// Small effect/state harness: tests request ordering without a browser or React
// renderer. The response-schema boundary is stubbed; Python tests cover the API.
const {test} = require('node:test')
const assert = require('node:assert/strict')
const {readFileSync} = require('node:fs')
const {createRequire} = require('node:module')
const path = require('node:path')
const vm = require('node:vm')
const root = path.resolve(__dirname, '../..')
const ts = createRequire(path.join(root, 'ui/package.json'))('typescript')
const source = readFileSync(path.join(root, 'ui/src/lib/localMediaProfilePreview.ts'), 'utf8')
const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText

function harness() {
    let state = null, dependency, cleanup, pendingEffect
    const timers = new Map(), requests = []
    let timerId = 0
    const exports = {}
    const react = {
        useState: () => [state, (value) => { state = value }],
        useEffect: (effect, dependencies) => {
            if (dependencies[0] !== dependency) {
                dependency = dependencies[0]
                pendingEffect = effect
            }
        },
    }
    vm.runInNewContext(code, {
        exports, AbortController,
        require: (name) => name === 'react' ? react : {LocalMediaProfilePreviewSchema: {parse: (value) => value}},
        window: {
            appConfig: {API_URL: '/api'},
            setTimeout: (callback) => { timers.set(++timerId, callback); return timerId },
            clearTimeout: (id) => timers.delete(id),
        },
        fetch: (url, options) => new Promise((resolve) => requests.push({url, options, resolve})),
    })
    return {
        requests,
        render: (request) => {
            const result = exports.useLocalMediaProfilePreview(request)
            if (pendingEffect) {
                cleanup?.()
                cleanup = pendingEffect()
                pendingEffect = null
            }
            return result
        },
        start: () => {
            const callbacks = [...timers.values()]
            timers.clear()
            return Promise.all(callbacks.map((callback) => callback()))
        },
    }
}

const request = (show, sourceId = 'episode:1') => ({
    type: 'show', sourceId, outputTemplate: '/downloads/{{ show_title }}/{{ title }}.ext',
    preferredFormat: 'format_1080p', localMediaProfileId: null, indexingValues: [],
    values: {show_title: show, title: 'Episode'},
})
const payload = (show) => ({output: {outputPath: `/media/${show}/Episode.mp4`, error: null}, showRoot: {path: `/media/${show}`}})
const respond = (call, data, ok = true) => call.resolve({ok, json: async () => data})

test('one request carries selected source and edits and supplies both paths', async () => {
    const h = harness(), body = request('Edited', 'episode:2')
    assert.equal(h.render(body).loading, true)
    const job = h.start()
    assert.equal(h.requests.length, 1)
    assert.equal(h.requests[0].url, '/api/local-media-profiles/preview')
    assert.deepEqual(JSON.parse(h.requests[0].options.body), body)
    respond(h.requests[0], payload('Edited')); await job
    const state = h.render(body)
    assert.equal(state.loading, false)
    assert.equal(state.result.showRoot.path, '/media/Edited')
    assert.equal(state.result.output.outputPath, '/media/Edited/Episode.mp4')
})

test('edited values keep the last preview stable until the next response arrives', async () => {
    const h = harness(), first = request('First'), second = request('Second')
    h.render(first); const firstJob = h.start()
    respond(h.requests[0], payload('First')); await firstJob
    assert.equal(h.render(first).result.showRoot.path, '/media/First')

    const pending = h.render(second)
    assert.equal(pending.loading, true)
    assert.equal(pending.result.showRoot.path, '/media/First')
    assert.equal(pending.result.output.outputPath, '/media/First/Episode.mp4')

    const secondJob = h.start()
    respond(h.requests[1], payload('Second')); await secondJob
    const settled = h.render(second)
    assert.equal(settled.loading, false)
    assert.equal(settled.result.showRoot.path, '/media/Second')
    assert.equal(settled.result.output.outputPath, '/media/Second/Episode.mp4')
})

test('out-of-order responses cannot restore paths from an older example', async () => {
    const h = harness(), a = request('A'), b = request('B', 'episode:2')
    h.render(a); const first = h.start()
    h.render(b)
    assert.equal(h.render(b).loading, true)
    const second = h.start()
    assert.equal(h.requests[0].options.signal.aborted, true)
    respond(h.requests[1], payload('B')); await second
    respond(h.requests[0], payload('A')); await first
    const current = h.render(b)
    assert.equal(current.result.showRoot.path, '/media/B')
    assert.equal(current.result.output.outputPath, '/media/B/Episode.mp4')
})

test('errors and cleared inputs never retain successful paths', async () => {
    const h = harness(), body = request('Example')
    h.render(body); const job = h.start()
    respond(h.requests[0], {detail: [{msg: 'Invalid example'}]}, false); await job
    assert.equal(h.render(body).error, 'Invalid example')
    assert.equal(h.render(body).result, null)
    const cleared = h.render(null)
    assert.equal(cleared.result, null)
    assert.equal(cleared.error, '')
    assert.equal(cleared.loading, false)
})
