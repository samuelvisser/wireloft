import {useEffect, useMemo, useRef, useState, type ComponentProps, type CSSProperties, type ReactNode} from 'react'
import {useQuery} from '@tanstack/react-query'
import CodeMirror from '@uiw/react-codemirror'
import {
    autocompletion,
    pickedCompletion,
    startCompletion,
    type Completion,
    type CompletionContext,
} from '@codemirror/autocomplete'
import {indentUnit, HighlightStyle, syntaxHighlighting} from '@codemirror/language'
import {jinja} from '@codemirror/lang-jinja'
import {EditorView, type ViewUpdate} from '@codemirror/view'
import {tags} from '@lezer/highlight'
import {Controller, type UseFormReturn, useWatch} from 'react-hook-form'

import ReadMore from '../../utils/ReadMore'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'
import {
    compactOutputTemplate,
    editorPositionForCompactOffset,
    formatOutputTemplateForEditor,
} from './outputTemplateFormatting'
import {getOutputTemplateVariables} from './outputTemplateVariables'
import './OutputTemplateEditor.css'
import './OutputTemplateEditorIde.css'

type TemplateSource = {
    id: string
    label: string
    values: Record<string, string>
    fallback: boolean
}

type TemplateSourcesResponse = {
    sources: TemplateSource[]
}

type TemplatePreviewResponse = {
    outputPath: string
    usedVariables: string[]
}

type Props = {
    form: UseFormReturn<any>
    mode: LocalMediaProfileMode
    placeholder: string
    help: ReactNode
}

type TemplateCodeEditorProps = {
    value: string
    placeholder: string
    extensions: ComponentProps<typeof CodeMirror>['extensions']
    invalid: boolean
    onChange: (value: string) => void
    onBlur: () => void
}

type JinjaStatement = {
    label: string
    detail: string
    acceptsExpression?: boolean
}

const jinjaStatements: JinjaStatement[] = [
    {label: 'if', detail: 'Start a conditional block', acceptsExpression: true},
    {label: 'elif', detail: 'Add another conditional branch', acceptsExpression: true},
    {label: 'else', detail: 'Add a fallback branch'},
    {label: 'endif', detail: 'End a conditional block'},
    {label: 'for', detail: 'Start a loop', acceptsExpression: true},
    {label: 'endfor', detail: 'End a loop'},
    {label: 'set', detail: 'Assign a value', acceptsExpression: true},
    {label: 'endset', detail: 'End a block assignment'},
    {label: 'block', detail: 'Start a named block', acceptsExpression: true},
    {label: 'endblock', detail: 'End a named block'},
    {label: 'macro', detail: 'Define a macro', acceptsExpression: true},
    {label: 'endmacro', detail: 'End a macro'},
    {label: 'call', detail: 'Call a macro with a body', acceptsExpression: true},
    {label: 'endcall', detail: 'End a call block'},
    {label: 'filter', detail: 'Apply a filter to a block', acceptsExpression: true},
    {label: 'endfilter', detail: 'End a filter block'},
    {label: 'with', detail: 'Start a scoped block', acceptsExpression: true},
    {label: 'endwith', detail: 'End a scoped block'},
    {label: 'raw', detail: 'Start a raw Jinja block'},
    {label: 'endraw', detail: 'End a raw Jinja block'},
    {label: 'autoescape', detail: 'Start an autoescape block', acceptsExpression: true},
    {label: 'endautoescape', detail: 'End an autoescape block'},
]

const jinjaHighlightStyle = HighlightStyle.define([
    {tag: tags.brace, class: 'cm-jinja-brace'},
    {
        tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.operatorKeyword],
        class: 'cm-jinja-keyword',
    },
    {
        tag: [tags.variableName, tags.propertyName, tags.special(tags.variableName)],
        class: 'cm-jinja-variable',
    },
    {tag: tags.string, class: 'cm-jinja-string'},
    {tag: [tags.number, tags.bool], class: 'cm-jinja-literal'},
    {
        tag: [tags.operator, tags.arithmeticOperator, tags.logicOperator, tags.compareOperator],
        class: 'cm-jinja-operator',
    },
    {tag: [tags.comment, tags.blockComment], class: 'cm-jinja-comment'},
])

function responseErrorMessage(payload: any): string {
    const detail = payload?.detail
    if (Array.isArray(detail) && detail.length) return detail[0]?.msg ?? 'The template could not be rendered.'
    if (typeof detail === 'string') return detail
    return 'The template could not be rendered.'
}

function structuralEdit(update: ViewUpdate): boolean {
    let structural = false
    update.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
        const added = inserted.toString()
        const removed = update.startState.doc.sliceString(fromA, toA)
        if (added.includes('\n') || added.includes('\r')) return
        if (
            added.includes('/')
            || added.includes('%}')
            || added.includes('}}')
            || added.includes('#}')
            || removed.includes('/')
            || removed.includes('%}')
            || removed.includes('}}')
            || removed.includes('#}')
        ) {
            structural = true
        }
    })
    return structural
}

function formatEditorAfterStructuralEdit(update: ViewUpdate) {
    if (!update.docChanged || !update.state.selection.main.empty || !structuralEdit(update)) return

    const original = update.state.doc.toString()
    const formatted = formatOutputTemplateForEditor(original)
    if (formatted === original) return

    const cursor = update.state.selection.main.head
    const compactOffset = compactOutputTemplate(original.slice(0, cursor)).length
    queueMicrotask(() => {
        const view = update.view
        if (view.state.doc.toString() !== original) return
        const anchor = editorPositionForCompactOffset(formatted, compactOffset)
        view.dispatch({
            changes: {from: 0, to: view.state.doc.length, insert: formatted},
            selection: {anchor},
        })
    })
}

function indentAfterNewline(update: ViewUpdate) {
    if (!update.docChanged || !update.state.selection.main.empty) return

    let insertedNewline = false
    update.changes.iterChanges((_fromA, _toA, _fromB, _toB, inserted) => {
        if (inserted.toString().includes('\n')) insertedNewline = true
    })
    if (!insertedNewline) return

    const documentAfterEnter = update.state.doc.toString()
    queueMicrotask(() => {
        const view = update.view
        if (view.state.doc.toString() !== documentAfterEnter || !view.state.selection.main.empty) return

        const cursor = view.state.selection.main.head
        const line = view.state.doc.lineAt(cursor)
        if (line.number <= 1) return

        const previousLine = view.state.doc.line(line.number - 1)
        const previousIndent = previousLine.text.match(/^\t*/)?.[0] ?? ''
        const previousContent = previousLine.text.slice(previousIndent.length).trimEnd()
        const statement = previousContent.match(/{%\s*([A-Za-z_][A-Za-z0-9_]*)\b[^%]*(?:%})?\s*$/)
        const keyword = statement?.[1] ?? ''
        const opensBlock = ['if', 'for', 'block', 'macro', 'call', 'filter', 'with', 'raw', 'autoescape'].includes(keyword)
            || (keyword === 'set' && !previousContent.slice(previousContent.indexOf('set') + 3).includes('='))
        const branch = keyword === 'else' || keyword === 'elif'
        const incompleteKeywordNeedsSpace = !!statement
            && !previousContent.includes('%}')
            && ['if', 'elif', 'for', 'set', 'block', 'macro', 'call', 'filter', 'with', 'autoescape'].includes(keyword)
            && previousContent.trimEnd().endsWith(keyword)

        const desiredIndent = `${previousIndent}${opensBlock || branch ? '\t' : ''}${incompleteKeywordNeedsSpace ? ' ' : ''}`
        const currentIndent = line.text.match(/^[\t ]*/)?.[0] ?? ''
        if (cursor > line.from + currentIndent.length || currentIndent === desiredIndent) return

        view.dispatch({
            changes: {from: line.from, to: line.from + currentIndent.length, insert: desiredIndent},
            selection: {anchor: line.from + desiredIndent.length},
        })
    })
}

function TemplateCodeEditor({
    value,
    placeholder,
    extensions,
    invalid,
    onChange,
    onBlur,
}: TemplateCodeEditorProps) {
    const canonicalValue = value ?? ''
    const [editorValue, setEditorValue] = useState(() => formatOutputTemplateForEditor(canonicalValue))
    const lastCanonicalValue = useRef(canonicalValue)

    useEffect(() => {
        if (canonicalValue === lastCanonicalValue.current) return
        lastCanonicalValue.current = canonicalValue
        setEditorValue(formatOutputTemplateForEditor(canonicalValue))
    }, [canonicalValue])

    return (
        <CodeMirror
            id="mp-path"
            className="output-template-code-editor"
            value={editorValue}
            minHeight="96px"
            placeholder={placeholder}
            extensions={extensions}
            basicSetup={{
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                autocompletion: false,
            }}
            onChange={(nextValue) => {
                setEditorValue(nextValue)
                const compactValue = compactOutputTemplate(nextValue)
                lastCanonicalValue.current = compactValue
                onChange(compactValue)
            }}
            onBlur={() => {
                setEditorValue((current) => formatOutputTemplateForEditor(current))
                onBlur()
            }}
            aria-label="Output path template"
            aria-invalid={invalid}
            aria-describedby={invalid ? 'mp-path-error' : 'mp-path-help'}
        />
    )
}

function PreviewPath({path}: {path: string}) {
    const absolute = path.startsWith('/')
    const parts = path.split('/').filter(Boolean)
    if (!absolute || parts.length < 2) return <code>{path}</code>

    return (
        <code className="template-preview-path-tree" title={path}>
            {parts.map((part, index) => (
                <span
                    key={`${part}-${index}`}
                    className="template-preview-path-segment"
                    style={{'--template-path-depth': index} as CSSProperties}
                >
                    <span className="template-preview-path-branch" aria-hidden="true">{index === 0 ? '' : '└─ '}</span>
                    {index === 0 ? '/' : ''}{part}{index < parts.length - 1 ? '/' : ''}
                </span>
            ))}
        </code>
    )
}

export default function OutputTemplateEditor({form, mode, placeholder, help}: Props) {
    const {control, formState: {errors}} = form
    const template = useWatch({control, name: 'outputTemplate'}) ?? ''
    const preferredFormat = useWatch({control, name: 'preferredFormat'}) ?? ''
    const variables = useMemo(() => getOutputTemplateVariables(mode), [mode])
    const [usedVariableNames, setUsedVariableNames] = useState<string[]>([])
    const usedVariables = useMemo(
        () => {
            const used = new Set(usedVariableNames)
            return variables.filter(({name}) => used.has(name))
        },
        [usedVariableNames, variables],
    )
    const usedVariablesKey = usedVariables.map(({name}) => name).join('|')

    const completionOptions = useMemo<Completion[]>(
        () => variables.map((variable) => ({
            label: variable.name,
            type: 'variable',
            detail: variable.description,
            apply: (view, completion, from, to) => {
                const variableStart = view.state.sliceDoc(0, from).lastIndexOf('{{')
                const replaceFrom = variableStart >= 0 ? variableStart + 2 : from
                const closingBraces = /^\s*}}/.exec(view.state.sliceDoc(to))
                const replaceTo = closingBraces ? to + closingBraces[0].length : to
                const insert = ` ${variable.name} }}`
                view.dispatch({
                    changes: {from: replaceFrom, to: replaceTo, insert},
                    selection: {anchor: replaceFrom + insert.length},
                    annotations: pickedCompletion.of(completion),
                })
            },
        })),
        [variables],
    )
    const statementCompletionOptions = useMemo<Completion[]>(
        () => jinjaStatements.map((statement) => ({
            label: statement.label,
            type: 'keyword',
            detail: statement.detail,
            apply: (view, completion, from, to) => {
                const statementStart = view.state.sliceDoc(0, from).lastIndexOf('{%')
                const replaceFrom = statementStart >= 0 ? statementStart + 2 : from
                const closingTag = /^\s*%}/.exec(view.state.sliceDoc(to))
                const replaceTo = closingTag ? to + closingTag[0].length : to
                const insert = ` ${statement.label}${statement.acceptsExpression ? '  ' : ' '}%}`
                const anchor = statement.acceptsExpression
                    ? replaceFrom + ` ${statement.label} `.length
                    : replaceFrom + insert.length
                view.dispatch({
                    changes: {from: replaceFrom, to: replaceTo, insert},
                    selection: {anchor},
                    annotations: pickedCompletion.of(completion),
                })
            },
        })),
        [],
    )
    const editorExtensions = useMemo(() => {
        const variableCompletionSource = (context: CompletionContext) => {
            const beforeCursor = context.state.sliceDoc(0, context.pos)
            const variableStart = beforeCursor.lastIndexOf('{{')
            const variableEnd = beforeCursor.lastIndexOf('}}')
            if (variableStart <= variableEnd) return null

            const expression = beforeCursor.slice(variableStart + 2)
            if (!/^\s*[A-Za-z_]*$/.test(expression)) return null
            const currentWord = expression.match(/[A-Za-z_]*$/)?.[0] ?? ''

            return {
                from: context.pos - currentWord.length,
                options: completionOptions,
                validFor: /^[A-Za-z_]*$/,
            }
        }
        const statementCompletionSource = (context: CompletionContext) => {
            const beforeCursor = context.state.sliceDoc(0, context.pos)
            const statementStart = beforeCursor.lastIndexOf('{%')
            const statementEnd = beforeCursor.lastIndexOf('%}')
            if (statementStart <= statementEnd) return null

            const statement = beforeCursor.slice(statementStart + 2)
            if (!/^\s*[A-Za-z_]*$/.test(statement)) return null
            const currentWord = statement.match(/[A-Za-z_]*$/)?.[0] ?? ''

            return {
                from: context.pos - currentWord.length,
                options: statementCompletionOptions,
                validFor: /^[A-Za-z_]*$/,
            }
        }
        const openCompletionsAfterJinjaDelimiter = EditorView.updateListener.of((update) => {
            if (!update.docChanged || !update.state.selection.main.empty) return
            const cursor = update.state.selection.main.head
            if (cursor < 2) return
            const delimiter = update.state.doc.sliceString(cursor - 2, cursor)
            if (delimiter === '{{' || delimiter === '{%') {
                queueMicrotask(() => startCompletion(update.view))
            }
        })
        return [
            jinja(),
            indentUnit.of('\t'),
            autocompletion({override: [variableCompletionSource, statementCompletionSource]}),
            syntaxHighlighting(jinjaHighlightStyle),
            EditorView.lineWrapping,
            openCompletionsAfterJinjaDelimiter,
            EditorView.updateListener.of(indentAfterNewline),
            EditorView.updateListener.of(formatEditorAfterStructuralEdit),
            EditorView.theme({
                '&': {fontSize: '16px'},
                '.cm-content': {fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'},
            }),
        ]
    }, [completionOptions, statementCompletionOptions])

    const {data: sourceData, isLoading: sourcesLoading, isError: sourcesFailed} = useQuery<TemplateSourcesResponse>({
        queryKey: ['localMediaProfileTemplateSources', mode],
        queryFn: async ({signal}) => {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/local-media-profiles/template/sources?type=${mode}`,
                {signal, credentials: 'include'},
            )
            if (!response.ok) throw new Error(`Failed to load template examples (${response.status})`)
            return response.json()
        },
        staleTime: 30_000,
    })
    const sources = sourceData?.sources ?? []
    const [selectedSourceId, setSelectedSourceId] = useState('')
    const [testValues, setTestValues] = useState<Record<string, string>>({})
    const [testValuesExpanded, setTestValuesExpanded] = useState(false)
    const selectedSource = sources.find(({id}) => id === selectedSourceId) ?? sources[0]

    useEffect(() => {
        if (!sources.length) return
        if (!sources.some(({id}) => id === selectedSourceId)) {
            setSelectedSourceId(sources[0].id)
            setTestValues({...sources[0].values})
        }
    }, [selectedSourceId, sources])

    useEffect(() => {
        setTestValues((current) => {
            const next = {...current}
            let changed = false
            for (const {name} of usedVariables) {
                if (!(name in next)) {
                    next[name] = selectedSource?.values[name] ?? ''
                    changed = true
                }
            }
            return changed ? next : current
        })
    }, [selectedSource, usedVariablesKey])

    const [previewPath, setPreviewPath] = useState('')
    const [previewError, setPreviewError] = useState('')
    const [previewLoading, setPreviewLoading] = useState(false)
    const previewValuesKey = JSON.stringify(testValues)
    useEffect(() => {
        if (!template) {
            setUsedVariableNames([])
            setPreviewPath('')
            setPreviewError('')
            return
        }
        if (!selectedSource) return
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            setPreviewLoading(true)
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/local-media-profiles/template/preview`,
                    {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        credentials: 'include',
                        signal: controller.signal,
                        body: JSON.stringify({
                            type: mode,
                            outputTemplate: template,
                            preferredFormat,
                            values: testValues,
                        }),
                    },
                )
                const payload = await response.json()
                if (!response.ok) {
                    setPreviewError(responseErrorMessage(payload))
                    return
                }
                const result = payload as TemplatePreviewResponse
                setPreviewPath(result.outputPath)
                setUsedVariableNames(result.usedVariables)
                setPreviewError('')
            } catch (error) {
                if ((error as Error).name !== 'AbortError') {
                    setPreviewError('The preview is temporarily unavailable.')
                }
            } finally {
                if (!controller.signal.aborted) setPreviewLoading(false)
            }
        }, 300)
        return () => {
            window.clearTimeout(timer)
            controller.abort()
        }
    }, [mode, preferredFormat, previewValuesKey, selectedSource, template])

    function chooseSource(sourceId: string) {
        const source = sources.find(({id}) => id === sourceId)
        setSelectedSourceId(sourceId)
        if (source) setTestValues({...source.values})
    }

    return (
        <div className="form-row output-template-field">
            <section className="template-workbench" aria-labelledby="template-editor-heading">
                <div className="template-editor-heading">
                    <div>
                        <label id="template-editor-heading" htmlFor="mp-path">Output path template</label>
                        <p>Type <code>{'{{'}</code> for variables or <code>{'{%'}</code> for Jinja statements.</p>
                    </div>
                    <span className="template-language-badge">Jinja</span>
                </div>
                <Controller
                    control={control}
                    name="outputTemplate"
                    render={({field}) => (
                        <TemplateCodeEditor
                            value={field.value ?? ''}
                            placeholder={placeholder}
                            extensions={editorExtensions}
                            invalid={!!errors.outputTemplate}
                            onChange={(value) => {
                                field.onChange(value)
                                form.clearErrors('outputTemplate')
                            }}
                            onBlur={field.onBlur}
                        />
                    )}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}

                <div className="template-workbench-divider"/>
                <div className="template-preview-area">
                    <div className="template-playground-heading">
                        <div>
                            <h3 id="template-preview-heading">Example output</h3>
                            <p>Try different values here. Your profile is not changed.</p>
                        </div>
                        {sources.length > 0 && (
                            <label className="template-source-label">
                                <span>Example source</span>
                                <select
                                    className="input"
                                    value={selectedSource?.id ?? ''}
                                    onChange={(event) => chooseSource(event.target.value)}
                                >
                                    {sources.map((source) => (
                                        <option key={source.id} value={source.id}>{source.label}</option>
                                    ))}
                                </select>
                            </label>
                        )}
                    </div>

                    {sourcesLoading && <p className="template-preview-status">Loading an example…</p>}
                    {sourcesFailed && (
                        <p className="error" role="alert">Examples could not be loaded. Try refreshing the page.</p>
                    )}
                    {selectedSource?.fallback && (
                        <p className="template-preview-status">No {mode === 'movie' ? 'movies' : 'episodes'} found yet, so example values are being used.</p>
                    )}

                    <div className={`template-preview-output${previewError ? ' has-error' : ''}`} aria-live="polite">
                        <span className="template-preview-output-label">Path</span>
                        {previewError
                            ? <span className="error">{previewError}</span>
                            : previewPath
                                ? <PreviewPath path={previewPath}/>
                                : <code>{previewLoading ? 'Rendering…' : 'Add a variable to preview this path.'}</code>
                        }
                    </div>

                    <div className="template-test-values">
                        {!testValuesExpanded && (
                            <>
                                <span className="template-preview-live-note">Preview updates as you type</span>
                                <button
                                    type="button"
                                    className="btn btn-small template-test-values-toggle"
                                    aria-expanded={false}
                                    aria-controls="template-test-values-fields"
                                    onClick={() => setTestValuesExpanded(true)}
                                >
                                    Test different values
                                </button>
                            </>
                        )}
                        {testValuesExpanded && (
                            <div id="template-test-values-fields" className="template-test-values-content">
                                <div className="template-test-values-heading">
                                    <h4>Test values</h4>
                                    <div className="template-test-values-actions">
                                        {selectedSource && usedVariables.length > 0 && (
                                            <button
                                                type="button"
                                                className="btn btn-small"
                                                onClick={() => setTestValues({...selectedSource.values})}
                                            >
                                                Reset values
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            className="btn btn-small"
                                            aria-expanded={true}
                                            aria-controls="template-test-values-fields"
                                            onClick={() => setTestValuesExpanded(false)}
                                        >
                                            Hide test values
                                        </button>
                                    </div>
                                </div>
                                {usedVariables.length === 0 ? (
                                    <p className="template-preview-status">Variables you add to the template will appear here automatically.</p>
                                ) : (
                                    <div className="template-test-values-grid">
                                        {usedVariables.map((variable) => (
                                            <label key={variable.name}>
                                                <span><code>{`{{ ${variable.name} }}`}</code> <small>{variable.description}</small></span>
                                                <input
                                                    className="input"
                                                    type="text"
                                                    value={testValues[variable.name] ?? ''}
                                                    onChange={(event) => setTestValues((current) => ({
                                                        ...current,
                                                        [variable.name]: event.target.value,
                                                    }))}
                                                />
                                            </label>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            </section>

            <div className="help output-template-help" id="mp-path-help">
                <ReadMore summary="Jinja syntax and all available variables.">
                    <div className="output-template-guidance">{help}</div>
                    <h4>Available variables</h4>
                    <dl className="output-template-variable-reference">
                        {variables.map((variable) => (
                            <div key={variable.name}>
                                <dt><code>{`{{ ${variable.name} }}`}</code></dt>
                                <dd>{variable.description}</dd>
                            </div>
                        ))}
                    </dl>
                </ReadMore>
            </div>
        </div>
    )
}
