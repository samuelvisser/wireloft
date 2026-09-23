import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p': {label: "Video", help: "Stream video"},
  'format_audio_only': {label: "Audio Only", help: "Stream audio only"},
});

export const RssVideoOutputModeReg = createSelectRegistry("RssVideoOutputMode", {
  'audio_hls': {
    label: "Audio with HLS video",
    help: "Normal M4A podcast enclosure with an adaptive HLS video alternate enclosure",
  },
  'audio_mp4': {
    label: "Audio with MP4 video",
    help: "Normal M4A podcast enclosure with an MP4 video alternate enclosure",
  },
  'mp4': {
    label: "MP4 video only",
    help: "Normal MP4 enclosure without a Podcasting 2.0 alternate enclosure",
  },
  'mp4_hls': {
    label: "MP4 video with HLS alternate",
    help: "Normal MP4 enclosure plus an adaptive HLS alternate enclosure",
  },
});

export const RssHlsOutputModes = new Set(['audio_hls', 'mp4_hls'])
export const RssMp4OutputModes = new Set(['audio_mp4', 'mp4', 'mp4_hls'])
