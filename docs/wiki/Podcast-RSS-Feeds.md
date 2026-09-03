# Podcast RSS Feeds

WireLoft can expose a managed show as a private RSS 2.0 podcast/video feed. The feed can serve downloaded media, stream directly from Daily Wire when no suitable local file exists, or combine both approaches.

> [!CAUTION]
> **Treat the complete WireLoft RSS feed URL like a password or API key.** The URL contains a secret token that authorizes access to the feed and the media exposed through it. RSS endpoints intentionally remain reachable without the WireLoft administrator login so podcast clients can use them. Anyone who obtains the URL can use that access too, including for premium media available through your WireLoft/Daily Wire session.

Do not post the URL publicly, include it in screenshots, paste it into public issue reports, or share it with people who should not have access. If it leaks, regenerate the URL immediately from the Stream Profile; the old token is invalidated.

## Requirements

Before creating a feed:

1. Add the show to WireLoft.
2. If you want the feed to use local media, create suitable Download Profiles and let WireLoft download some episodes.
3. If you want direct Daily Wire streaming—especially premium content—connect a Daily Wire account that has access to the show.
4. Make sure the hostname you will put in the feed URL is reachable by the podcast client.

A feed used only inside your LAN can use a local hostname/IP. A phone that needs the feed away from home requires a network path back to WireLoft, such as your own HTTPS reverse proxy or VPN.

## Create an RSS Stream Profile

Open the show and create a Stream Profile, or use **Stream Profiles → Add Stream Profile**.

### 1. Choose streaming sources

WireLoft offers two independent sources.

#### Use Downloads

WireLoft can serve completed files already stored locally. This gives the podcast client a stable local enclosure and avoids fetching that media from Daily Wire again.

#### Use DailyWire stream

WireLoft can request a fresh media URL from Daily Wire when the podcast client asks for an episode.

When **both** options are enabled, WireLoft prefers a suitable completed local download. If none is available, it falls back to Daily Wire. This hybrid mode is useful when you keep only recent episodes locally but still want older episodes available through the feed.

If neither source is enabled, the feed has no media items to expose.

### 2. Enable streaming

**Enable streaming** controls whether the profile is active. A disabled profile keeps its configuration but its tokenized feed returns as unavailable.

### 3. Choose audio or video

Choose the preferred media format for the feed.

For downloaded media, WireLoft searches completed downloads that belong to the same audio/video class and attempts to match the requested format.

### 4. Exact format matching

When local downloads are enabled, **Require exact match** determines how strict WireLoft should be.

- With exact matching enabled, a local download is used only if its Local Media Profile has exactly the preferred format.
- With exact matching disabled, WireLoft can choose another suitable video resolution when an exact one does not exist.

For video, WireLoft first prefers the smallest available resolution that is at least the requested resolution; if none reaches it, it chooses from the available video candidates. Audio and video are never mixed as format fallbacks.

If no acceptable local file exists and Daily Wire streaming is enabled, Daily Wire becomes the fallback.

### 5. Choose episode types

Select which episode types the feed should expose. The normal default is **Episode** plus **Auxiliary**.

WireLoft filters each episode by the type prefix in its episode identifier. An episode outside the selected types is not exposed by the feed or its tokenized media URL.

### 6. Limit feed history

**Maximum episodes in RSS feed** controls how many of the newest eligible items appear.

- `0` — complete eligible history.
- Any positive number — only that many newest eligible episodes.

Items are sorted newest-first using publication date, then live date, then creation date as fallbacks. WireLoft excludes `No Show Today` placeholders.

A smaller limit can make very large feeds easier for podcast applications to process. It does not delete any WireLoft data.

## Daily Wire video delivery methods

When the profile streams Daily Wire video, WireLoft offers three delivery modes.

### Podcasting 2.0 direct stream with audio fallback — recommended

Internal value: `stream_hls_download_m4a`

WireLoft exposes the Daily Wire HLS video as a Podcasting 2.0 alternate enclosure. Compatible podcast clients can start streaming video immediately. The conventional RSS enclosure is audio so clients that do not understand the HLS alternate can still consume the episode.

This is the fastest true-streaming option, but Podcasting 2.0 HLS support differs between podcast applications. A client may decide to download/use the conventional audio enclosure instead of the video alternate.

### Serve as locally cached MP4 — full compatibility

Internal value: `stream_download_mp4`

WireLoft prepares a complete MP4 locally and serves it as a conventional `video/mp4` enclosure. This is easier for normal video podcast clients to understand and never intentionally substitutes audio for a Daily Wire video request.

The trade-off is startup delay: when no cached MP4 exists, WireLoft must prepare the entire file before it can serve it. Long episodes can therefore take noticeably longer to start or download.

### Direct stream with cached MP4 fallback

Internal value: `stream_hls_download_mp4`

This combines both approaches. Podcasting 2.0-compatible clients can use the HLS alternate immediately, while the normal enclosure is a cached MP4 for clients/download workflows that need conventional video.

If that MP4 is not already cached, preparing it can still take time.

### Downloaded video is unaffected by this choice

If WireLoft finds a suitable completed local download first, it serves that file directly. The Daily Wire video-method setting only matters for episodes that need the Daily Wire fallback.

### Recommended MP4 setup

If you use either cached-MP4 method frequently, consider a small video Download Profile that keeps only the latest **5** episodes. Recent episodes can then be served immediately from the normal download library, while older episodes remain available through on-demand Daily Wire preparation.

## Save and copy the feed URL

When a new RSS Stream Profile is created, WireLoft generates a secret token and builds a URL from the current request host:

```text
https://wireloft.example.com/feeds/rss/<secret-token>/<show-slug>.xml
```

For Daily Wire video profiles, the URL can also carry a `dwVideoMethod` query parameter. **Copy the complete URL exactly as shown**, including any query string.

After creation, the Stream Profile shows an editable **RSS feed URL** field and a Copy button.

### Why the URL is editable

The host seen by WireLoft is not always the host a podcast client should use. For example, WireLoft might generate an internal Docker/LAN hostname while your phone needs a public reverse-proxy hostname.

You can edit the URL to use the correct scheme/hostname. Keep the secret token and feed path intact. WireLoft automatically keeps the video-method query parameter consistent with the profile settings.

## Add the feed to a podcast app

The exact wording differs by client, but the workflow is normally:

1. Open the podcast application's option to **add a podcast by URL**, **follow private feed**, or **subscribe by RSS URL**.
2. Paste the complete WireLoft RSS URL.
3. Save/follow the feed.
4. Refresh the podcast app if it does not fetch immediately.
5. Open an episode and verify that the expected media type plays.

The podcast app does **not** need the WireLoft administrator password. The token in the RSS URL is the feed credential.

If a client offers separate username/password fields, leave them unused unless your own reverse proxy imposes an additional authentication layer that the client supports.

## Reverse proxies and remote access

For a remote client, both the XML feed and every media URL it contains must be reachable. Allow the tokenized path tree, not only the `.xml` file:

```text
/feeds/rss/<token>/<show>.xml
/feeds/rss/<token>/episodes/<episode>
/feeds/rss/<token>/episodes/<episode>/audio
/feeds/rss/<token>/episodes/<episode>/video.mp4
```

You normally should not put WireLoft's UI login in front of these endpoints. The feed token is deliberately the RSS authentication mechanism.

Use HTTPS whenever the feed leaves a trusted private network. HTTPS protects the secret URL from passive observation in transit.

## How WireLoft chooses an enclosure

For each eligible episode, the logic is approximately:

1. Reject episodes outside the profile's selected episode types.
2. Ignore `No Show Today` placeholders.
3. If **Use Downloads** is enabled, inspect completed/redownloaded local files.
4. Prefer an exact local format match.
5. If exact matching is not required, choose the best suitable local fallback of the same audio/video class.
6. If a local file was selected, serve it directly.
7. Otherwise, if **Use DailyWire stream** is enabled, expose a Daily Wire-backed enclosure using the chosen audio/video method.
8. Otherwise, omit the episode because no media source is available.

This means a hybrid feed can transparently transition from local recent episodes to Daily Wire-backed older episodes.

## Premium feeds and membership

WireLoft requests Daily Wire media using the account connected to WireLoft. For a member-exclusive show, the account must have the necessary access. The private WireLoft RSS token does not create a Daily Wire entitlement; it only authorizes the caller to use the feed capability already configured on your WireLoft instance.

This is also why the URL must be kept private: it effectively delegates your WireLoft instance's configured feed access to whoever has the token.

## Regenerate a leaked feed URL

If the URL is exposed:

1. Open the RSS Stream Profile.
2. Click **Regenerate** beside the feed URL.
3. Save/use the new URL in your own podcast clients.
4. Remove the old URL from places where it may have been stored or shared.

Regeneration creates a new secret token and immediately makes the previous token invalid.

Do not rely on changing only the visible hostname or show slug to revoke access. Rotate the token.

## Feed caching

WireLoft sends no-cache headers for RSS responses and temporary Daily Wire redirects. Podcast clients can still maintain their own local feed/media caches according to their application behavior, so a regenerated token prevents future WireLoft requests but cannot remotely erase media a client already downloaded.

## Troubleshooting RSS

### The podcast app cannot add the URL

Open the complete RSS URL from a device on the same network path as the podcast client. If it cannot reach WireLoft, fix DNS, reverse proxy, firewall, VPN, or hostname selection first.

### The feed opens locally but not on a phone away from home

The generated URL probably points to a LAN-only address, or `/feeds/rss/...` is not exposed through your remote-access path. Edit the Stream Profile URL to the reachable HTTPS hostname and confirm the proxy forwards the feed and media paths.

### Audio works but direct Daily Wire video does not

Your podcast app may not implement the Podcasting 2.0 HLS alternate-enclosure method in the way WireLoft expects. Try **Serve as locally cached MP4** for maximum conventional-video compatibility, or **Direct stream with cached MP4 fallback**.

### Cached MP4 takes a long time to begin

That is expected on the first request when WireLoft must prepare the complete MP4. Keep a small number of recent video episodes downloaded locally if you want immediate playback for new episodes.

### Some downloaded episodes are missing

Check the RSS profile's episode types, preferred format, **Require exact match**, and source selection. If Daily Wire fallback is disabled, an episode with no acceptable local file is omitted.

### Old episodes disappeared from the feed

Check **Maximum episodes in RSS feed**. A positive value limits the feed listing but does not delete the episodes from WireLoft.

### A leaked URL still works in one app after regeneration

The client may be showing cached feed data or a previously downloaded media file. New requests using the old token are invalidated at WireLoft.