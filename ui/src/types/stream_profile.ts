import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p': {label: "Video", help: "Stream video"},
  'format_audio_only': {label: "Audio Only", help: "Stream audio only"},
});

export const RssDwVideoMethodReg = createSelectRegistry("RssDwVideoMethod", {
  'stream_hls_download_m4a': {
    label: "Podcasting 2.0 direct stream with audio fallback (recommended)",
    help: "Stream Daily Wire video directly through Podcasting 2.0",
  },
  'stream_download_mp4': {
    label: "Serve as locally cached mp4 (full compatibility)",
    help: "Prepare and serve a conventional MP4 video file",
  },
  'stream_hls_download_mp4': {
    label: "Direct stream with cached mp4 fallback",
    help: "Stream immediately with Podcasting 2.0 and use cached MP4 for downloads and fallback",
  },
});
