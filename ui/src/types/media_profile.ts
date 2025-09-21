import {createSelectRegistry} from "../utils/selectRegistry";


export const PreferredFormatReg = createSelectRegistry("PreferredFormat", {
  '4k':   { label: "4k",   help: "Download a 4k video" },
  '1080p':   { label: "1080p",   help: "Download an 1080p video" },
  '720p':   { label: "720p",   help: "Download an 720p video" },
  'audioOnly':   { label: "Audio Only",   help: "Download audio only" },
});