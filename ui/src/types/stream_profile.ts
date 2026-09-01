import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p': {label: "Video", help: "Stream video"},
  'format_audio_only': {label: "Audio Only", help: "Stream audio only"},
});

export const RssDwVideoMethodReg = createSelectRegistry("RssDwVideoMethod", {
  'podcasting_2_0': {
    label: "Podcasting 2.0 direct stream with audio fallback (recommended)",
    help: "Stream Daily Wire video directly through Podcasting 2.0",
  },
  'cached_mp4': {
    label: "Serve as locally cached mp4 (full compatibility)",
    help: "Prepare and serve a conventional MP4 video file",
  },
});
