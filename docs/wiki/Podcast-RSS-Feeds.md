# Podcast RSS Feeds

WireLoft can expose a managed show as a private podcast or video RSS feed. The feed can use downloaded files, stream from Daily Wire, or combine both approaches.

> [!CAUTION]
> **Treat the complete RSS feed URL like a password or API key.** It contains a secret token that gives access to the feed without requiring the WireLoft administrator login. Anyone who obtains the URL can use the feed access you configured.

If a URL leaks, regenerate it from the Stream Profile. The old token stops working immediately for new requests.

## Before creating a feed

You need:

1. the show in your WireLoft Library;
2. a Daily Wire account connected if the feed needs member-exclusive Daily Wire media;
3. suitable local downloads if you want the feed to use downloaded files;
4. a WireLoft hostname that the podcast client can reach.

A LAN-only feed can use a local hostname or IP. For a phone away from home, use your own HTTPS reverse proxy, VPN, or another secure route back to WireLoft.

## Choose where media comes from

An RSS Stream Profile has two independent media sources.

### Use Downloads

WireLoft serves suitable completed files already stored in your local download library.

This is the best option when you want predictable local playback and do not want the podcast client to fetch that episode from Daily Wire again.

### Use DailyWire stream

WireLoft obtains the episode media from Daily Wire when the podcast client requests it.

This makes it possible to expose episodes you have not kept locally, including a much larger back catalog.

### Use both

When both options are enabled, WireLoft prefers a suitable local download and uses Daily Wire when no acceptable local file exists.

This is a useful default for many users: keep recent episodes downloaded for fast access while still allowing older episodes to remain available through the feed.

## Enable or disable a feed

**Enable streaming** controls whether the Stream Profile is active. Disabling it keeps the profile settings but makes that feed unavailable until you enable it again.

## Preferred format

Choose the audio or video format you want the feed to prefer.

When **Use Downloads** is enabled, WireLoft looks for completed local files that match the requested media type.

### Require exact match

- Enabled: only a local file with the exact preferred format is accepted.
- Disabled: WireLoft can use another suitable resolution of the same media type when the exact video quality is unavailable.

WireLoft never treats audio as a substitute for a local video file or vice versa.

If no acceptable local file exists and Daily Wire streaming is enabled, the feed can fall back to Daily Wire.

## Episode types

Choose which Daily Wire episode types should appear in the feed. A normal podcast setup commonly includes **Episode** and **Auxiliary**.

Items outside the selected types are left out of the feed.

## Limit the feed size

**Maximum episodes in RSS feed** controls how many of the newest eligible episodes are listed.

- `0` — expose the complete eligible history.
- Any positive value — expose only that many newest eligible episodes.

This only limits the RSS listing. It does not delete episodes or downloaded files from WireLoft.

A smaller value can help podcast apps that struggle with very large feeds.

## Daily Wire video delivery

If a video feed uses Daily Wire streaming, WireLoft offers three delivery choices.

### Podcasting 2.0 direct stream with audio fallback

This is the fastest true-streaming option. Podcast apps with good Podcasting 2.0 HLS support can begin playing the Daily Wire video quickly.

Because support differs between apps, an incompatible client may use the audio fallback instead of video.

Choose this when immediate streaming is more important than compatibility with every video podcast client.

### Serve as locally cached MP4

WireLoft prepares a conventional MP4 and serves that to the podcast client.

This has the broadest compatibility with normal video podcast apps and does not intentionally replace the requested video with audio. The trade-off is that the first request can take noticeably longer because the complete MP4 must be prepared before it can be served.

### Direct stream with cached MP4 fallback

This combines both approaches. Compatible clients can use the direct HLS stream, while clients that need a conventional enclosure can use the MP4 fallback.

Preparing the MP4 may still take time the first time it is needed.

### Local downloads take priority

These video-delivery choices only matter when WireLoft needs the Daily Wire fallback. If a suitable downloaded file is available, WireLoft serves that local file directly.

A useful video setup is to keep a small number of recent episodes downloaded while allowing older episodes to use Daily Wire.

## Copy and edit the feed URL

After a Stream Profile is created, WireLoft shows its private RSS URL with **Copy** and **Regenerate** actions.

The URL looks similar to:

```text
https://wireloft.example.com/feeds/rss/<secret-token>/<show-slug>.xml
```

The hostname is editable. This is useful when WireLoft sees an internal hostname but your podcast app needs a different LAN or public hostname.

Keep the token and feed path intact unless you deliberately regenerate the token.

## Add the feed to a podcast app

Most podcast apps have an option such as **Add by URL**, **Private feed**, or **Subscribe by RSS URL**.

1. Copy the complete WireLoft RSS URL.
2. Paste it into the podcast app.
3. Save or follow the feed.
4. Refresh the app if it does not fetch immediately.
5. Test an episode and confirm the expected audio/video behavior.

The podcast app does not need the WireLoft administrator password. The secret URL is the feed credential.

## Reverse proxies and remote access

A remote podcast client must be able to reach both the feed and the media URLs it contains.

When using a reverse proxy:

- forward the entire `/feeds/rss/` path tree, not only the `.xml` feed;
- use HTTPS whenever the feed travels over an untrusted network;
- do not require the normal WireLoft web-login flow for RSS paths unless your podcast client explicitly supports the extra authentication method.

See [[Security-and-Remote-Access]].

## Premium content

WireLoft requests Daily Wire media using the account connected to your WireLoft instance. That account must already have access to member-exclusive content.

The RSS token does not create a Daily Wire entitlement. It delegates access to the feed capability your WireLoft instance already has, which is why the URL must be kept private.

## Regenerate a leaked URL

If a feed URL is exposed:

1. Open the Stream Profile.
2. Click **Regenerate** beside the feed URL.
3. Replace the old URL in your podcast clients.
4. Remove the old URL from anywhere it was shared or stored publicly.

Previously downloaded media on another device cannot be recalled, but new requests using the old token are rejected.

## Troubleshooting

### The podcast app cannot add the feed

Try opening the same RSS URL from a device using the same network path. If it cannot reach WireLoft, check the hostname, DNS, firewall, VPN, reverse proxy, and HTTPS certificate.

### It works at home but not away from home

The feed probably uses a LAN-only hostname or your remote-access path is not forwarding `/feeds/rss/`. Edit the Stream Profile URL to use the reachable hostname.

### Video plays as audio

If you selected **Podcasting 2.0 direct stream with audio fallback**, the app may not support the HLS video method properly. Try **Serve as locally cached MP4** for broader compatibility or **Direct stream with cached MP4 fallback**.

### MP4 video takes a long time to begin

That is expected the first time WireLoft must prepare an MP4. Keep recent video episodes downloaded locally if you want immediate playback for new episodes.

### Some episodes are missing

Check:

- selected episode types;
- preferred format;
- **Require exact match**;
- **Use Downloads** / **Use DailyWire stream**;
- **Maximum episodes in RSS feed**.

A downloads-only feed cannot serve an episode without a suitable completed local file.

### An old URL still appears to work after regeneration

The podcast client may be showing cached feed data or media it previously downloaded. New requests to WireLoft using the old token are invalid.