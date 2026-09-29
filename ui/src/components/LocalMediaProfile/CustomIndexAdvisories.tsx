import {useMemo} from 'react'

import {customIndexAdvisoryRequest, customIndexReferences, type IndexDefinition} from '../../lib/customIndexAdvisory'
import {useCustomIndexAdvisory} from '../../lib/useCustomIndexAdvisory'
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
            {advisories.map(({key, kind, message, suggestion}) => (
                <div className="template-metadata-warning template-index-advisory" role="status" key={key}>
                    <strong>{kind === 'episode_index'
                        ? <>Use <code>episode_index</code> instead of Custom Index <code>{key}</code></>
                        : <>Custom Index <code>{key}</code> numbers every episode</>
                    }</strong>
                    <p>{message}</p>
                    {suggestion && (
                        <details className="template-index-suggestion">
                            <summary>Suggested change for <code>{key}</code></summary>
                            <p>{kind === 'episode_index'
                                ? <>Use the existing show-wide episode index. The <code>int</code> filter preserves numeric formatting and arithmetic.</>
                                : <>Use the condition already in your template to control the index call. A Jinja set block builds the text only in the selected branch.</>
                            }</p>
                            <div className="template-index-code-label">Replace this code</div>
                            <pre><code>{exampleCode(suggestion.before)}</code></pre>
                            <div className="template-index-code-label">{kind === 'episode_index' ? 'With the built-in variable' : 'With this set block'}</div>
                            <pre><code>{exampleCode(suggestion.after)}</code></pre>
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
