import {createSelectRegistry, SelectRegistry} from "../utils/selectRegistry";
import {ShowRead} from "./schemas/show";
import {useMemo} from "react";

// ShowType
export const ShowTypeReg = createSelectRegistry("ShowType", {
    podcast: {label: "Podcast", help: "Episodes identified by date or number"},
    series: {label: "Series", help: "Episodic series without podcast semantics"},
});
export type ShowTypeValue = (typeof ShowTypeReg)["values"][number];


// EpisodeIdentifier (only for podcasts)
export const EpisodeIdentifierReg = createSelectRegistry("EpisodeIdentifier", {
    numbered: {label: "Numbered", help: "Parse 'Ep. N' from the title"},
    date_based: {label: "Date-based", help: "Use release date as identity"},
    seasonal: {label: "Seasonal", help: "Parse 'S01E01' from the order of episodes within the season"},
});
export type EpisodeIdentifierValue = (typeof EpisodeIdentifierReg)["values"][number];

/** Build a select registry for Shows from an array (no memoization). */
export function buildShowSelectRegistry(shows: readonly ShowRead[] | undefined | null): SelectRegistry {
    const spec: Record<string, { label: string }> = {}
    const values: string[] = []
    if (Array.isArray(shows)) {
        for (const s of shows) {
            const id = String(s.id)
            const name = s.title
            spec[id] = {label: String(name)}
            values.push(id)
        }
    }
    return createSelectRegistry('Show', spec, values)
}

/** React hook: memoized select registry for Shows */
export function useShowSelectRegistry(shows: readonly ShowRead[] | undefined | null): SelectRegistry {
    return useMemo((): SelectRegistry => buildShowSelectRegistry(shows), [shows])
}
