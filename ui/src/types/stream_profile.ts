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
    help: "RSS contains a stable WireLoft .m3u8 URL; WireLoft resolves a fresh Daily Wire URL when that URL is requested and returns HTTP 302",
  },
  'experiment_hls_https_redirect_302': {
    label: "Experiment: force HTTPS WireLoft URL -> fresh DW (302)",
    help: "Forces the HLS alternate enclosure to use https:// even when the generated RSS URL uses http://, isolating whether Pocket Casts rejects cleartext HLS before following the redirect",
  },
  'experiment_hls_cached_redirect_302': {
    label: "Experiment: pre-warmed 302 (instant cache hit)",
    help: "Resolves the signed Daily Wire URL while the RSS feed is generated, then the stable .m3u8 endpoint can return HTTP 302 without a Daily Wire lookup. Use a very small feed while testing this method.",
  },
  'experiment_hls_head_200_get_302': {
    label: "Experiment: HEAD 200, GET fresh DW 302",
    help: "HEAD on the stable .m3u8 returns an immediate HLS-looking 200 response without contacting Daily Wire; GET resolves a fresh Daily Wire URL and redirects with HTTP 302",
  },
  'experiment_hls_redirect_302_headers': {
    label: "Experiment: 302 with explicit HLS headers",
    help: "Same fresh Daily Wire redirect as the basic 302 experiment, but the redirect response explicitly advertises application/x-mpegURL and filename video.m3u8",
  },
  'experiment_hls_prewarmed_raw': {
    label: "Experiment: pre-warmed raw DW manifest (instant 200)",
    help: "Fetches the Daily Wire master playlist while generating the RSS feed and later serves the untouched playlist bytes immediately from the stable WireLoft .m3u8 URL. Use a very small feed while testing.",
  },
  'experiment_hls_prewarmed_absolute': {
    label: "Experiment: pre-warmed manifest with absolute DW children",
    help: "Pre-warms the Daily Wire master playlist, rewrites relative child URIs to signed absolute Daily Wire URLs, and serves it immediately as HTTP 200. Use a very small feed while testing.",
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
