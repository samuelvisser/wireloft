import {useEffect, useMemo, useState, type ReactNode} from 'react'
import {useQuery} from '@tanstack/react-query'
import CodeMirror from '@uiw/react-codemirror'
import {
    autocompletion,
    startCompletion,
    type Completion,
    type CompletionContext,
} from '@codemirror/autocomplete'
import {jinja} from '@codemirror/lang-jinja'
import {HighlightStyle, syntaxHighlighting} from '@codemirror/language'
import {EditorView} from '@codemirror/view'
import {tags} from '@lezer/highlight'
import {Controller, type UseFormReturn, useWatch} from 'react-hook-form'

import ReadMore from '../../utils/ReadMore'
import type {LocalMediaProfileMode} from './LocalMediaProfileForm'
import {
    findUsedOutputTemplateVariables,
    getOutputTemplateVariables,
} from './outputTemplateVariables'
import './OutputTemplateEditor.css'

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

export default function OutputTemplateEditor({form, mode, placeholder, help}: Props) {
    const {control, formState: {errors}} = form
    const template = useWatch({control, name: 'outputTemplate'}) ?? ''
    const preferredFormat = useWatch({control, name: 'preferredFormat'}) ?? ''
    const variables = useMemo(() => getOutputTemplateVariables(mode), [mode])
    const usedVariables = useMemo(
        () => findUsedOutputTemplateVariables(template, variables),
        [template, variables],
    )
    const usedVariablesKey = usedVariables.map(({name}) => name).join('|')

    const completionOptions = useMemo<Completion[]>(
        () => variables.map((variable) => ({
            label: variable.name,
            type: 'variable',
            detail: variable.description,
            apply: variable.name,
        })),
        [variables],
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
        const openVariablesAfterDoubleBrace = EditorView.updateListener.of((update) => {
            if (!update.docChanged || !update.state.selection.main.empty) return
            const cursor = update.state.selection.main.head
            if (cursor >= 2 && update.state.doc.sliceString(cursor - 2, cursor) === '{{') {
                queueMicrotask(() => startCompletion(update.view))
            }
        })
        return [
            jinja(),
            autocompletion({override: [variableCompletionSource]}),
            syntaxHighlighting(jinjaHighlightStyle),
            EditorView.lineWrapping,
            openVariablesAfterDoubleBrace,
            EditorView.theme({
                '&': {fontSize: '16px'},
                '.cm-content': {fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'},
            }),
        ]
    }, [completionOptions])

    const {data: sourceData, isLoading: sourcesLoading, isError: sourcesFailed} = useQuery<TemplateSourcesResponse>({
        queryKey: ['localMediaProfileTemplateSources', mode],
        queryFn: async ({signal}) => {
            const response = await fetch(
                `${(window as any).appConfig.API_URL}/local-media-profiles/template-sources?type=${mode}`,
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
    const exampleOutputPath = useMemo(
        () => previewPath.replace(/\.ext$/, preferredFormat === 'format_audio_only' ? '.m4a' : '.mp4'),
        [preferredFormat, previewPath],
    )

    useEffect(() => {
        if (!selectedSource || !template) return
        const controller = new AbortController()
        const timer = window.setTimeout(async () => {
            setPreviewLoading(true)
            try {
                const response = await fetch(
                    `${(window as any).appConfig.API_URL}/local-media-profiles/template-preview`,
                    {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        credentials: 'include',
                        signal: controller.signal,
                        body: JSON.stringify({type: mode, outputTemplate: template, values: testValues}),
                    },
                )
                const payload = await response.json()
                if (!response.ok) {
                    setPreviewError(responseErrorMessage(payload))
                    return
                }
                const result = payload as TemplatePreviewResponse
                setPreviewPath(result.outputPath)
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
    }, [mode, previewValuesKey, selectedSource, template])

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
                        <p>Type <code>{'{{'}</code> to insert an available variable.</p>
                    </div>
                </div>
                <Controller
                    control={control}
                    name="outputTemplate"
                    render={({field}) => (
                        <CodeMirror
                            id="mp-path"
                            className="output-template-code-editor"
                            value={field.value ?? ''}
                            minHeight="96px"
                            placeholder={placeholder}
                            extensions={editorExtensions}
                            basicSetup={{
                                lineNumbers: false,
                                foldGutter: false,
                                highlightActiveLine: false,
                                highlightActiveLineGutter: false,
                                autocompletion: false,
                            }}
                            onChange={(value) => {
                                field.onChange(value)
                                form.clearErrors('outputTemplate')
                            }}
                            onBlur={field.onBlur}
                            aria-label="Output path template"
                            aria-invalid={!!errors.outputTemplate}
                            aria-describedby={errors.outputTemplate ? 'mp-path-error' : 'mp-path-help'}
                        />
                    )}
                />
                {errors.outputTemplate && (
                    <div id="mp-path-error" className="error" role="alert" aria-live="polite">
                        {String(errors.outputTemplate.message)}
                    </div>
                )}

                <div className="template-workbench-divider"/>
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
                        : <code>{exampleOutputPath || (previewLoading ? 'Rendering…' : 'Add a variable to preview this path.')}</code>
                    }
                </div>

                <div className="template-test-values">
                    {!testValuesExpanded && (
                        <button
                            type="button"
                            className="btn btn-small template-test-values-toggle"
                            aria-expanded={false}
                            aria-controls="template-test-values-fields"
                            onClick={() => setTestValuesExpanded(true)}
                        >
                            Test different values
                        </button>
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
                                            <span><code>{variable.name}</code> <small>{variable.description}</small></span>
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
