import {createSelectRegistry} from "../utils/selectRegistry";

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