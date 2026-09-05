import {createSelectRegistry, SelectRegistry} from "../utils/selectRegistry";
import {useMemo} from "react";
import {LocalMediaProfileRead} from "./schemas/local_media_profile";


export const PreferredFormatReg = createSelectRegistry("PreferredFormat", {
  'format_4k':   { label: "4k",   help: "Download a 4k video" },
  'format_1080p':   { label: "1080p",   help: "Download an 1080p video" },
  'format_720p':   { label: "720p",   help: "Download an 720p video" },
  'format_audio_only':   { label: "Audio Only",   help: "Download audio only" },
});

export const MoviePreferredFormatReg = createSelectRegistry("MoviePreferredFormat", {
  'format_4k': { label: "4k", help: "Download a 4k video" },
  'format_1080p': { label: "1080p", help: "Download a 1080p video" },
  'format_720p': { label: "720p", help: "Download a 720p video" },
});

export const LocalMediaProfileTypeReg = createSelectRegistry("LocalMediaProfileType", {
  'show': { label: "Show", help: "Store downloaded show episodes" },
  'movie': { label: "Movie", help: "Store manually downloaded movies" },
});

export const ShowLocalMediaProfileScopeReg = createSelectRegistry("ShowLocalMediaProfileScope", {
  'both': { label: "Both", help: "Offer this profile for both Podcasts and Series" },
  'podcast': { label: "Podcast", help: "Offer this profile only for Podcasts" },
  'series': { label: "Series", help: "Offer this profile only for Series" },
});

export type LocalMediaProfileType = 'show' | 'movie'
export type ShowLocalMediaProfileScope = (typeof ShowLocalMediaProfileScopeReg)["values"][number]
export type ShowLocalMediaProfileContext = 'podcast' | 'series'

export function isShowLocalMediaProfileAvailableFor(
    profile: LocalMediaProfileRead,
    showType: string | null | undefined,
): boolean {
    if (profile.type !== 'show') return false
    if (showType !== 'podcast' && showType !== 'series') return true
    const scope = profile.showScope ?? 'both'
    return scope === 'both' || scope === showType
}

/** Build a select registry for Local Media Profiles from an array (no memoization). */
export function buildLocalMediaProfileSelectRegistry(
    mediaProfiles: readonly LocalMediaProfileRead[] | undefined | null,
    type?: LocalMediaProfileType,
    showType?: ShowLocalMediaProfileContext,
): SelectRegistry{
    const spec: Record<string, { label: string }> = {}
    if (Array.isArray(mediaProfiles)) {
        for (const p of mediaProfiles) {
            if (type && p.type !== type) continue
            if (type === 'show' && showType && !isShowLocalMediaProfileAvailableFor(p, showType)) continue
            const id = (p as any).id
            const name = (p as any).name ?? String(id)
            if (typeof id === 'number') spec[String(id)] = {label: String(name)}
        }
    }
    return createSelectRegistry('LocalMediaProfile', spec as any)
}

/** React hook: memoized select registry for Local Media Profiles */
export function useLocalMediaProfileSelectRegistry(
    mediaProfiles: readonly LocalMediaProfileRead[] | undefined | null,
    type?: LocalMediaProfileType,
    showType?: ShowLocalMediaProfileContext,
): SelectRegistry{
    return useMemo(
        (): SelectRegistry => buildLocalMediaProfileSelectRegistry(mediaProfiles, type, showType),
        [mediaProfiles, type, showType],
    )
}
