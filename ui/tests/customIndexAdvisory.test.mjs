import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {dirname, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {test} from 'node:test'

const require = createRequire(import.meta.url)
const ts = require('typescript')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// Test-only loader: exercise the actual TypeScript without requiring a browser
// or adding a second application test framework. TypeScript is a UI devDependency.
function loadTs(relative, mocks = {}) {
    const filename = resolve(root, relative)
    const source = readFileSync(filename, 'utf8')
    const js = ts.transpileModule(source, {
        compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
        fileName: filename,
    }).outputText
    const module = {exports: {}}
    new Function('require', 'module', 'exports', js)((name) => {
        if (name in mocks) return mocks[name]
        if (name.startsWith('.')) return loadTs(resolve(dirname(filename), name + '.ts'), mocks)
        return require(name)
    }, module, module.exports)
    return module.exports
}

const {customIndexReferences, customIndexAdvisoryRequest} = loadTs('src/lib/customIndexAdvisory.ts')
const formatting = loadTs('src/components/LocalMediaProfile/outputTemplateFormatting.ts')

for (const template of [
    '{# {{ "extra" | custom_index }} #}/downloads/{{ title }}.ext',
    '{% raw %}{{ "extra" | custom_index }}{% endraw %}',
    '{%- raw -%}{{ "extra" | custom_index }}{%- endraw -%}',
    '{{ "text containing custom_index" }}',
    '{% set text = "\'extra\' | custom_index" %}',
    'custom_index in ordinary text',
]) {
    test('ignore non-code: ' + template, () => {
        assert.deepEqual(customIndexReferences(template), [])
        assert.equal(customIndexAdvisoryRequest(template, [{key: 'extra'}]), null)
    })
}

test('discover distinct literal keys in expressions, assignments and branches', () => {
    const template = '{% set n="extra-one"|custom_index %}{% if flag %}{{("other")|custom_index}}{% endif %}{{ "extra-one"|custom_index }}'
    assert.deepEqual(customIndexReferences(template), ['extra-one', 'other'])
})

test('no request for absent definitions, no references or undefined-only references', () => {
    const source = '{{ "extra" | custom_index }}'
    assert.equal(customIndexAdvisoryRequest(source, []), null)
    assert.equal(customIndexAdvisoryRequest(source, [{key: 'other'}]), null)
    assert.equal(customIndexAdvisoryRequest('{{ title }}', [{key: 'extra'}]), null)
})

test('request reflects unsaved definitions, not example values or profile state', () => {
    const source = '{{ "extra" | custom_index }}'
    assert.deepEqual(JSON.parse(customIndexAdvisoryRequest(source, [{key: 'extra'}])), {
        outputTemplate: source, indexingValueKeys: ['extra'],
    })
    assert.equal(customIndexAdvisoryRequest(source, []), null)
    assert.equal(customIndexAdvisoryRequest(source, [{key: 'extra'}, {key: 'extra'}]),
        customIndexAdvisoryRequest(source, [{key: 'extra'}]))
})

test('set-block suggestion survives editor display/compact round-trip without output whitespace', () => {
    const compact = "{% set plex_ep_id %}{% if is_extra %}other{{ 'extra' | custom_index }}{% else %}S{{ season_num }}E{{ ep_num }}{% endif %}{% endset %}"
    const displayed = formatting.renderEditorOutputTemplate(formatting.parseOutputTemplate(compact)).value
    assert.ok(displayed.includes('\n'))
    assert.equal(formatting.renderCompactOutputTemplate(formatting.parseOutputTemplate(displayed, 'editor')), compact)
})

function deferred() {
    let resolve
    let reject
    const promise = new Promise((yes, no) => {resolve = yes; reject = no})
    return {promise, resolve, reject}
}

function hookHarness() {
    let state = null
    let dependencies
    let cleanup
    let scheduled
    let requests = []
    const timers = new Set()
    const useState = () => [state, (value) => {state = value}]
    const useEffect = (effect, deps) => {
        if (!dependencies || dependencies[0] !== deps[0]) {
            cleanup?.()
            dependencies = deps
            scheduled = effect
        }
    }
    const fetch = (url, options) => {
        const request = deferred()
        requests.push({url, options, ...request})
        return request.promise
    }
    const window = {
        appConfig: {API_URL: '/api'},
        setTimeout: (callback) => {timers.add(callback); return callback},
        clearTimeout: (callback) => timers.delete(callback),
    }
    // Only React scheduling and network are mocked. The hook itself is the
    // production source; response-schema validation has its own API tests.
    const file = resolve(root, 'src/lib/useCustomIndexAdvisory.ts')
    const js = ts.transpileModule(readFileSync(file, 'utf8'), {
        compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
    }).outputText
    const exports = {}
    new Function('require', 'exports', 'window', 'fetch', js)((name) => {
        if (name === 'react') return {useState, useEffect}
        return {CustomIndexAdvisoryResultSchema: {parse: (value) => value}}
    }, exports, window, fetch)
    return {
        requests,
        render(body) {
            const result = exports.useCustomIndexAdvisory(body)
            if (scheduled) {cleanup = scheduled(); scheduled = null}
            return result
        },
        start() {for (const callback of timers) {timers.delete(callback); void callback()}},
        unmount() {cleanup?.()},
    }
}

async function flush() {for (let i = 0; i < 5; i++) await Promise.resolve()}
const payload = {advisories: [{key: 'extra', message: 'Every episode', suggestion: null}], error: null}

test('advisory is debounced, abortable and independent of the preview pipeline', async () => {
    const hook = hookHarness()
    hook.render(null)
    hook.start()
    assert.equal(hook.requests.length, 0)
    hook.render('draft A')
    hook.render('draft B')
    assert.equal(hook.requests.length, 0)
    hook.start()
    assert.equal(hook.requests.length, 1)
    assert.ok(hook.requests[0].url.endsWith('/advisory/custom-index'))
    assert.equal(hook.requests[0].options.body, 'draft B')
    assert.equal(hook.requests[0].options.credentials, 'include')
    hook.requests[0].resolve({ok: true, json: async () => payload})
    await flush()
    assert.equal(hook.render('draft B').advisories.length, 1)
    hook.unmount()
})

test('late responses cannot show warnings or replacements for a newer draft', async () => {
    const hook = hookHarness()
    hook.render('draft A'); hook.start()
    const old = hook.requests[0]
    hook.render('draft B'); hook.start()
    assert.equal(old.options.signal.aborted, true)
    old.resolve({ok: true, json: async () => payload})
    await flush()
    assert.equal(hook.render('draft B').advisories.length, 0)
    hook.requests[1].resolve({ok: true, json: async () => ({advisories: [], error: null})})
    await flush()
    assert.equal(hook.render('draft B').advisories.length, 0)
    hook.unmount()
})

test('removing the definition immediately removes existing advice', async () => {
    const hook = hookHarness()
    hook.render('defined'); hook.start()
    hook.requests[0].resolve({ok: true, json: async () => payload})
    await flush()
    assert.equal(hook.render('defined').advisories.length, 1)
    assert.deepEqual(hook.render(null), {advisories: [], unavailable: false})
    hook.start()
    assert.equal(hook.requests.length, 1)
})

test('unavailable advisory and syntax errors do not become form-validation errors', async () => {
    const hook = hookHarness()
    hook.render('offline'); hook.start()
    hook.requests[0].reject(new Error('offline'))
    await flush()
    assert.deepEqual(hook.render('offline'), {advisories: [], unavailable: true})
    hook.render('incomplete'); hook.start()
    hook.requests[1].resolve({ok: true, json: async () => ({advisories: [], error: 'Incomplete Jinja'})})
    await flush()
    assert.deepEqual(hook.render('incomplete'), {advisories: [], unavailable: false})
    hook.unmount()
})

function componentTree(props, advisoryState = {advisories: [], unavailable: false}) {
    const filename = resolve(root, 'src/components/LocalMediaProfile/CustomIndexAdvisories.tsx')
    const js = ts.transpileModule(readFileSync(filename, 'utf8'), {
        compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
        fileName: filename,
    }).outputText
    const exports = {}
    let sentRequest
    const jsx = (type, props, key) => ({type, props, key})
    const dependencies = {
        'react/jsx-runtime': {jsx, jsxs: jsx},
        react: {useMemo: (factory) => factory()},
        '../../lib/customIndexAdvisory': {customIndexReferences, customIndexAdvisoryRequest},
        '../../lib/useCustomIndexAdvisory': {useCustomIndexAdvisory: (request) => {
            sentRequest = request
            return advisoryState
        }},
        './outputTemplateFormatting': formatting,
        './CustomIndexAdvisories.css': {},
    }
    new Function('require', 'exports', js)((name) => dependencies[name], exports)
    const tree = exports.default(props)
    const elements = []
    function visit(node) {
        if (Array.isArray(node)) {node.forEach(visit); return}
        if (node && typeof node === 'object') {
            elements.push(node)
            visit(node.props?.children)
        }
    }
    visit(tree)
    return {tree, elements, sentRequest}
}

test('component shows one nonblocking missing-definition warning per key without API work', () => {
    const result = componentTree({
        template: '{{"a"|custom_index}}-{{"b"|custom_index}}', indexingValues: [], onApply: assert.fail,
    })
    assert.equal(result.sentRequest, null)
    assert.equal(result.elements.filter((node) => node.props.role === 'status').length, 2)
    assert.equal(result.elements.filter((node) => node.type === 'button').length, 0)
})

test('suggestions require explicit review/apply; warnings without suggestions remain visible', () => {
    const applied = []
    const result = componentTree({
        template: '{{"a"|custom_index}}-{{"b"|custom_index}}',
        indexingValues: [{key: 'a'}, {key: 'b'}],
        onApply: (value) => applied.push(value),
    }, {advisories: [
        {key: 'a', message: 'Every episode', suggestion: {
            before: '{% set n="a"|custom_index %}', after: '{% set n %}{{"a"|custom_index}}{% endset %}',
            outputTemplate: 'explicitly reviewed replacement',
        }},
        {key: 'b', message: 'Every episode', suggestion: null},
    ], unavailable: false})
    assert.deepEqual(applied, [])
    assert.equal(result.elements.filter((node) => node.props.role === 'status').length, 2)
    assert.equal(result.elements.filter((node) => node.type === 'details').length, 1)
    const button = result.elements.find((node) => node.type === 'button')
    assert.equal(button.props.type, 'button')
    button.props.onClick()
    assert.deepEqual(applied, ['explicitly reviewed replacement'])
})
