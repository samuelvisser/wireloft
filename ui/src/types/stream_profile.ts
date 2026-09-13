import {createSelectRegistry} from "../utils/selectRegistry";

export const MediaTypeReg = createSelectRegistry("PreferredFormat", {
  'format_1080p': {label: "Video", help: "Stream video"},
  'format_audio_only': {label: "Audio Only", help: "Stream audio only"},
});

export const RssDwVideoMethodReg = createSelectRegistry("RssDwVideoMethod", {
  'stream_hls_download_m4a': {
    label: "Control: embedded signed DW HLS + audio fallback",
    help: "Known Pocket Casts-compatible video path, but the feed must resolve a signed Daily Wire URL for every remote episode",
  },
  'stream_download_mp4': {
    label: "Control: stable prepared MP4 (known compatible)",
    help: "Stable WireLoft MP4 URL; prepares the complete file before serving it",
  },
  'stream_hls_download_mp4': {
    label: "Control: embedded DW HLS + cached MP4 fallback",
    help: "Known embedded HLS path plus a conventional cached MP4 enclosure",
  },
  'experiment_hls_redirect_302': {
    label: "Experiment: stable video.m3u8 -> fresh DW (302)",
    help: "RSS contains a stable WireLoft .m3u8 URL; WireLoft resolves a fresh Daily Wire URL only when playback starts and returns HTTP 302",
  },
  'experiment_hls_redirect_307': {
    label: "Experiment: stable video-307.m3u8 -> fresh DW (307)",
    help: "Same as the 302 experiment but uses HTTP 307 Temporary Redirect",
  },
  'experiment_hls_redirect_308': {
    label: "Experiment: stable video-308.m3u8 -> fresh DW (308)",
    help: "Same redirect experiment using HTTP 308 Permanent Redirect",
  },
  'experiment_hls_proxy_video_x': {
    label: "Experiment: transparent video-proxy.m3u8 (x-mpegURL)",
    help: "WireLoft returns the Daily Wire manifest bytes without rewriting them and advertises application/x-mpegURL",
  },
  'experiment_hls_proxy_master_x': {
    label: "Experiment: transparent master.m3u8 (x-mpegURL)",
    help: "Same transparent proxy response, changing only the podcast-facing filename to master.m3u8",
  },
  'experiment_hls_proxy_index_x': {
    label: "Experiment: transparent index.m3u8 (x-mpegURL)",
    help: "Same transparent proxy response, changing only the podcast-facing filename to index.m3u8",
  },
  'experiment_hls_proxy_video_apple': {
    label: "Experiment: transparent video-proxy-apple.m3u8 (Apple MIME)",
    help: "Same transparent manifest proxy advertised as application/vnd.apple.mpegurl",
  },
  'experiment_hls_proxy_video_generic': {
    label: "Experiment: transparent video-proxy-generic.m3u8 (generic MIME)",
    help: "Same transparent manifest proxy advertised as application/mpegurl",
  },
  'experiment_hls_prepared_ts': {
    label: "Experiment: prepared local HLS at prepared/video.m3u8",
    help: "WireLoft prepares a conventional VOD HLS package with MPEG-TS segments and serves it through stable .m3u8/.ts URLs",
  },
});
