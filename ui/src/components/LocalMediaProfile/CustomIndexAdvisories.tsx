import {useMemo} from 'react'
import CodeMirror from '@uiw/react-codemirror'
import {EditorView} from '@codemirror/view'

import {customIndexAdvisoryRequest, customIndexReferences, type IndexDefinition} from '../../lib/customIndexAdvisory'
import {useCustomIndexAdvisory} from '../../lib/useCustomIndexAdvisory'
import {outputTemplateSyntaxExtensions} from './outputTemplateCodeMirror'
import {parseOutputTemplate, renderEditorOutputTemplate} from './outputTemplateFormatting'
import './CustomIndexAdvisories.css'

type Props = {
    template: string
    indexingValues: IndexDefinition[]
    onApply: (template: string) => void
}

function exampleCode(source: string) {
    return renderEditorOutputTemplate(parseOutputTemplate(source, 'editor')).value
}

const exampleCodeExtensions = [
    ...outputTemplateSyntaxExtensions,
    EditorView.lineWrapping,
]

function SuggestionCode({source, label}: {source: string; label: string}) {
    return (
        <CodeMirror
            className="output-template-code-editor template-index-code-editor"
            value={exampleCode(source)}
            editable={false}
            extensions={exampleCodeExtensions}
            basicSetup={{
                lineNumbers: false,
                foldGutter: false,
                highlightActiveLine: false,
                highlightActiveLineGutter: false,
                autocompletion: false,
            }}
            aria-label={label}
        />
    )
}

export default function CustomIndexAdvisories({template, indexingValues, onApply}: Props) {
    const references = useMemo(() => customIndexReferences(template), [template])
    const request = customIndexAdvisoryRequest(template, indexingValues)
    const {advisories, unavailable} = useCustomIndexAdvisory(request)
    const definitions = new Set(indexingValues.map(({key}) => key))
    const missing = references.filter((key) => !definitions.has(key))

    if (!missing.length && !advisories.length && !unavailable) return null
    return (
        <div className="template-index-advisories" aria-label="Custom Index advice">
            {missing.map((key) => (
                <div className="template-metadata-warning template-index-advisory" role="status" key={key}>
                    <strong>Indexing Value <code>{key}</code> is not defined</strong>
                    <p>
                        It will render as empty. Add it in Indexing Values, or remove its reference.
                        This warning does not prevent saving.
                    </p>
                </div>
            ))}
            {advisories.map(({key, kind, suggestion}) => (
                <div className="template-metadata-warning template-index-advisory" role="status" key={key}>
                    <strong>{kind === 'episode_index'
                        ? <>Use <code>episode_index</code> instead of Custom Index <code>{key}</code></>
                        : <>Custom Index <code>{key}</code> numbers every episode</>
                    }</strong>
                    <p>{kind === 'episode_index'
                        ? <>This Custom Index runs for every episode and has no conditional uses. Use WireLoft's <code>episode_index</code> variable for this show-wide numbering instead of maintaining a separate Custom Index. The stored episode index includes all episode types and can contain gaps, so review the preview before saving.</>
                        : <>Custom Indexes are designed to apply an index to only some episodes within a show. As currently set up, this Custom Index runs for every episode, even when its number is not used in the path. If you intend to use an all-episode sequence, you should probably use the <code>episode_index</code> variable WireLoft provides. To number only some episodes, put the <code>custom_index</code> call inside the condition that selects them.</>
                    }</p>
                    {suggestion && (
                        <details className="template-index-suggestion">
                            <summary>Suggested change for <code>{key}</code></summary>
                            <p>{kind === 'episode_index'
                                ? <>Use the existing show-wide episode index. The <code>int</code> filter preserves numeric formatting and arithmetic.</>
                                : <>Keep the existing output logic, but request the index only where its value is needed.</>
                            }</p>
                            <div className="template-index-code-label">Replace this code</div>
                            <SuggestionCode source={suggestion.before} label={`Code to replace for Custom Index ${key}`}/>
                            <div className="template-index-code-label">{kind === 'episode_index' ? 'With the built-in variable' : 'With this'}</div>
                            <SuggestionCode source={suggestion.after} label={`Suggested replacement for Custom Index ${key}`}/>
                            <p>{kind === 'episode_index'
                                ? <>Other template code is kept. Stored episode indexes can contain gaps; review the preview before saving. You can remove the Indexing Value definition once nothing uses it.</>
                                : <>This changes which episodes receive a number. Other template code is kept. Review the preview before saving; saving may renumber this index.</>
                            }</p>
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => onApply(suggestion.outputTemplate)}
                                aria-label={`Use suggested change for Custom Index ${key}`}
                            >
                                Use suggested change
                            </button>
                        </details>
                    )}
                </div>
            ))}
            {unavailable && (
                <p className="template-preview-status" role="status">
                    Custom Index advice is temporarily unavailable. Previewing and saving still work.
                </p>
            )}
        </div>
    )
}
