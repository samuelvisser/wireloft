import {createContext} from 'react'

// Observe the editor's controlled source selection without persisting UI state
// in the profile or coupling the generic editor to show-only assets.
export const TemplateSourceSelectionContext = createContext<((sourceId: string | null) => void) | null>(null)
