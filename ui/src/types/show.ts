import {createSelectRegistry, SelectRegistry} from "../utils/selectRegistry";
import {ShowRead} from "./schemas/show";
import {useMemo} from "react";

// ShowType
export const ShowTypeReg = createSelectRegistry("ShowType", {
  podcast: { label: "Podcast", help: "Episodes identified by date or number" },
  series:  { label: "Series",  help: "Episodic series without podcast semantics" },
});
export type ShowTypeValue = (typeof ShowTypeReg)["values"][number];


// EpisodeIdentifier (only for podcasts)
export const EpisodeIdentifierReg = createSelectRegistry("EpisodeIdentifier", {
  date_based: { label: "Date-based", help: "Use release date as identity" },
  numbered:   { label: "Numbered",   help: "Parse 'Ep. N' from the title" },
});
export type EpisodeIdentifierValue = (typeof EpisodeIdentifierReg)["values"][number];

/** Build a select registry for Shows from an array (no memoization). */
export function buildShowSelectRegistry(shows: readonly ShowRead[] | undefined | null): SelectRegistry {
    const spec: Record<string, { label: string }> = {}
    if (Array.isArray(shows)) {
        for (const s of shows) {
            const id = s.id
            const name = s.title
            spec[String(id)] = {label: String(name)}
        }
    }
    return createSelectRegistry('Show', spec as any)
}

/** React hook: memoized select registry for Shows */
export function useShowSelectRegistry(shows: readonly ShowRead[] | undefined | null): SelectRegistry {
    return useMemo((): SelectRegistry => buildShowSelectRegistry(shows), [shows])
}
