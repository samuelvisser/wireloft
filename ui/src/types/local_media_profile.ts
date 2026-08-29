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

export type LocalMediaProfileType = 'show' | 'movie'

/** Build a select registry for Local Media Profiles from an array (no memoization). */
export function buildLocalMediaProfileSelectRegistry(
    mediaProfiles: readonly LocalMediaProfileRead[] | undefined | null,
    type?: LocalMediaProfileType,
): SelectRegistry{
    const spec: Record<string, { label: string }> = {}
    if (Array.isArray(mediaProfiles)) {
        for (const p of mediaProfiles) {
            if (type && p.type !== type) continue
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
): SelectRegistry{
    return useMemo(
        (): SelectRegistry => buildLocalMediaProfileSelectRegistry(mediaProfiles, type),
        [mediaProfiles, type],
    )
}
