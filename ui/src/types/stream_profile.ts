import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p': {label: "Video", help: "Stream video"},
  'format_audio_only': {label: "Audio Only", help: "Stream audio only"},
});

export const RssVideoOutputModeReg = createSelectRegistry("RssVideoOutputMode", {
  'audio_hls': {
    label: "HLS video stream with audio fallback (recommended)",
    help: "Stream video directly using a stream- friendly protocol serving multiple quality levels depending on the connection speed. Provides an audio fallback for compatibility.",
  },
  'audio_mp4': {
    label: "Serve as mp4 with audio fallback (full compatibility)",
    help: "Stream as mp4 downloaded by WireLoft. Requires the mp4 to be downloaded by WireLoft before it can start streaming. Provides an audio fallback for compatibility.",
  },
  'mp4': {
    label: "Serve mp4 video only",
    help: "Normal mp4 enclosure without audio fallback. Not recommended if 'Use DailyWire stream' is enabled.",
  },
  'mp4_hls': {
    label: "HLS video stream with mp4 fallback",
    help: "Streams video using HLS, and provides mp4 as the fallback. This ensures the podcasting app will always play video if it supports video at all. Might be unexpectedly slow however because mp4 videos still need to be pre- downloaded by WireLoft.",
  },
});

export const RssHlsOutputModes = new Set(['audio_hls', 'mp4_hls'])
export const RssMp4OutputModes = new Set(['audio_mp4', 'mp4', 'mp4_hls'])
