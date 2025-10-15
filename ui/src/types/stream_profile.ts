import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p':   { label: "Video", help: "Stream video" },
  'format_audio_only':   { label: "Audio Only", help: "Steam audio only" },
});