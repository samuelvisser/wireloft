import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {dirname, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {test} from 'node:test'

const require = createRequire(import.meta.url)
const ts = require('typescript')
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function load(relative, mocks) {
    const filename = resolve(root, relative)
    const source = readFileSync(filename, 'utf8')
    const js = ts.transpileModule(source, {
        compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX},
        fileName: filename,
    }).outputText
    const exports = {}
    new Function('require', 'exports', js)((name) => {
        if (name in mocks) return mocks[name]
        throw new Error(`Unexpected dependency ${name}`)
    }, exports)
    return exports
}

function component(advisories) {
    const applied = []
    // Execute the small SuggestionCode function too, so read-only assertions
    // inspect its CodeMirror props rather than an unrendered component node.
    const jsx = (type, props) => typeof type === 'function' ? type(props) : {type, props}
    const {default: Advisory} = load('src/components/LocalMediaProfile/CustomIndexAdvisories.tsx', {
        'react/jsx-runtime': {jsx, jsxs: jsx, Fragment: 'fragment'},
        react: {useMemo: (factory) => factory()},
        '@uiw/react-codemirror': {default: 'static-code'},
        '@codemirror/view': {EditorView: {lineWrapping: 'line-wrapping'}},
        '../../lib/customIndexAdvisory': {
            customIndexReferences: () => advisories.map(({key}) => key),
            customIndexAdvisoryRequest: () => 'draft',
        },
        '../../lib/useCustomIndexAdvisory': {
            useCustomIndexAdvisory: () => ({advisories, unavailable: false}),
        },
        './outputTemplateCodeMirror': {outputTemplateSyntaxExtensions: ['jinja', 'highlighting']},
        './outputTemplateFormatting': {
            parseOutputTemplate: (source) => source,
            renderEditorOutputTemplate: (source) => ({value: source}),
        },
        './CustomIndexAdvisories.css': {},
    })
    const tree = Advisory({
        template: 'draft', indexingValues: advisories.map(({key}) => ({key})),
        onApply: (source) => applied.push(source),
    })
    const elements = []
    let text = ''
    function visit(node) {
        if (Array.isArray(node)) {node.forEach(visit); return}
        if (typeof node === 'string') {text += node; return}
        if (node && typeof node === 'object') {
            elements.push(node)
            visit(node.props?.children)
        }
    }
    visit(tree)
    return {elements, text, applied}
}

const builtin = {
    key: 'extra', kind: 'episode_index', message: 'Use the stored episode index.',
    suggestion: {
        before: "{% set n='extra'|custom_index %}",
        after: '{% set n=(episode_index | int) %}',
        outputTemplate: '{% set n=(episode_index | int) %}/downloads/{{ n }}.ext',
    },
}

test('unconditional advisory explains the built-in variable, not a conditional set block', () => {
    const result = component([builtin])
    assert.match(result.text, /Use episode_index instead of Custom Index extra/)
    assert.match(result.text, /With the built-in variable/)
    assert.match(result.text, /gaps/)
    assert.match(result.text, /int/)
    assert.doesNotMatch(result.text, /A Jinja set block/)
    assert.deepEqual(result.applied, [])
    const examples = result.elements.filter(({type}) => type === 'static-code')
    assert.equal(examples.length, 2)
    assert.ok(examples.every(({props}) => props.editable === false))
    assert.equal(examples[0].props.value, builtin.suggestion.before)
    assert.equal(examples[1].props.value, builtin.suggestion.after)
    const button = result.elements.find(({type}) => type === 'button')
    assert.equal(button.props.type, 'button')
    button.props.onClick()
    assert.deepEqual(result.applied, [builtin.suggestion.outputTemplate])
})

test('mixed advisories remain independent and keep the existing conditional guidance', () => {
    const result = component([builtin, {
        key: 'bonus', kind: 'all_episodes', message: 'Move the call behind its condition.',
        suggestion: {before: 'before', after: 'after', outputTemplate: 'conditional suggestion'},
    }])
    assert.equal(result.elements.filter(({props}) => props.role === 'status').length, 2)
    assert.equal(result.elements.filter(({type}) => type === 'button').length, 2)
    assert.match(result.text, /With this code/)
    assert.match(result.text, /Keep the existing output logic/)
    assert.match(result.text, /With the built-in variable/)
})

test('builtin advice without a safe edit still shows its warning', () => {
    const result = component([{...builtin, suggestion: null}])
    assert.match(result.text, /Use episode_index/)
    assert.equal(result.elements.filter(({type}) => type === 'button').length, 0)
})

test('episode_index is exposed in the shared show variable reference, not movies', () => {
    const {getOutputTemplateVariables} = load('src/components/LocalMediaProfile/outputTemplateVariables.ts', {})
    const variable = getOutputTemplateVariables('show').find(({name}) => name === 'episode_index')
    assert.ok(variable)
    assert.match(variable.description, /whole show/)
    assert.match(variable.readMore.paragraphs.join(' '), /gaps/)
    assert.ok(!getOutputTemplateVariables('movie').some(({name}) => name === 'episode_index'))
})

for (const after of [
    "{% if is_extra %}{{ 'extra' | custom_index }}{% endif %}",
    "{% macro label(flag) %}{{ ('extra' | custom_index) if flag else 'normal' }}{% endmacro %}",
]) {
    test('non-capture replacement remains static and explicitly applied: ' + after, () => {
        const suggestion = {before: 'original source', after, outputTemplate: 'complete replacement ' + after}
        const result = component([{key: 'extra', kind: 'all_episodes', message: 'Every episode', suggestion}])
        assert.match(result.text, /With this code/)
        assert.doesNotMatch(result.text, /With this set block/)
        assert.deepEqual(result.applied, [])
        const examples = result.elements.filter(({type}) => type === 'static-code')
        assert.equal(examples.length, 2)
        assert.ok(examples.every(({props}) => props.editable === false))
        assert.equal(examples[1].props.value, after)
        result.elements.find(({type}) => type === 'button').props.onClick()
        assert.deepEqual(result.applied, [suggestion.outputTemplate])
    })
}
