import {createSelectRegistry} from "../utils/selectRegistry";


export const PreferredFormatReg = createSelectRegistry("PreferredFormat", {
  'format_4k':   { label: "4k",   help: "Download a 4k video" },
  'format_1080p':   { label: "1080p",   help: "Download an 1080p video" },
  'format_720p':   { label: "720p",   help: "Download an 720p video" },
  'format_audio_only':   { label: "Audio Only",   help: "Download audio only" },
});