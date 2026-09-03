# Daily Wire Integration

WireLoft uses Daily Wire services for catalog discovery, show/episode metadata, account authorization, and media URLs. The integration is designed so WireLoft can manage both free and member-exclusive content without collecting your Daily Wire password.

## Account connection

WireLoft uses Daily Wire's device authorization/OAuth flow.

During onboarding or from the Daily Wire authentication area:

1. WireLoft starts a device authorization request.
2. You follow the Daily Wire-provided instructions to authorize the device/session.
3. Daily Wire confirms authorization to WireLoft.
4. WireLoft stores the resulting authentication state under its persistent `/config` data.

Your Daily Wire password is entered only into Daily Wire's own authorization experience, not into WireLoft.

## Membership access

WireLoft does not grant access to content your account cannot use. When a managed show is member-exclusive, direct stream/media lookups require the connected Daily Wire account to have the appropriate access.

This applies to:

- premium episode downloads;
- premium movie downloads;
- RSS feeds using **Use DailyWire stream** as a source.

A private WireLoft RSS token is not a substitute for Daily Wire membership. It authorizes use of the configured WireLoft feed after WireLoft itself has the necessary upstream access.

## Catalog and library

The **Browse** view represents content discoverable from Daily Wire. Adding an item creates WireLoft's own managed representation in the **Library**.

WireLoft can then keep a show's episodes/seasons synchronized independently of whether any files are downloaded.

## Episode discovery

The normal discovery schedule is every 30 minutes. It looks for newly known episodes on managed shows.

Known episodes that are still live/not final are monitored separately every minute by default. This separation is important: WireLoft does not need to requery every historical episode at one-minute intervals merely because one current episode is live.

See [[Automation-and-Background-Tasks]].

## Post-publication metadata changes

Daily Wire can change titles, thumbnails, or other metadata after an episode first appears. WireLoft schedules targeted refreshes for recently published episodes instead of continuously rechecking the full library.

Default refresh offsets are:

```text
5m,15m,30m,1h,3h,6h,24h
```

See `newEpisodeSchedule.metadataRefreshIntervals` in [[Settings]].

## Live/countdown media

Podcast episodes can move through a live/countdown version before their final media settles. WireLoft uses configurable publication thresholds to distinguish these stages.

Podcast Download Profiles can choose whether to:

- wait for the final version;
- download the countdown version early;
- download early and later replace it with the final version.

See [[Download-Profiles]].

## Direct RSS streaming

An RSS Stream Profile with **Use DailyWire stream** does not permanently embed one upstream Daily Wire media URL in the feed. When a media request needs the Daily Wire fallback, WireLoft obtains current episode details/media from Daily Wire and returns the appropriate stream/redirect or prepares an MP4 according to the selected video method.

This matters because upstream media URLs can be temporary. Podcast clients use WireLoft's stable tokenized enclosure URLs while WireLoft resolves the current Daily Wire media behind them.

See [[Podcast-RSS-Feeds]].

## Request pacing

WireLoft includes Daily Wire request-throttling settings:

- `dwTimeout.minFastRequestMs = 100`
- `dwTimeout.maxFastRequests = 350`
- `dwTimeout.minSlowRequestMs = 120`

These are advanced integration settings. Keep them at their defaults unless you are deliberately diagnosing a known issue; making requests more aggressive can increase upstream throttling risk.

## Production endpoints

The default integration endpoints are:

```yaml
dwApi:
  middlewareApi: https://middleware-prod.dailywire.com/middleware
  streamApi: https://stream.media.dailywire.com

dwOauth:
  issuer: https://authorize.dailywire.com
  audience: https://api.dailywire.com/
  clientId: FCgw3nA6cxkcXLVseAQvCSVBrymwvfpE
  scope: openid profile offline_access
```

They are configurable for development/advanced purposes, but ordinary installations should leave them unchanged.

## TMDB is separate

TMDB enrichment is not part of Daily Wire authentication. It is an optional third-party metadata source used for movie information such as release dates. Configure it under `movieMetadata` in [[Settings]].

## Authentication troubleshooting

If premium content suddenly fails:

1. Check the Daily Wire authentication status in WireLoft.
2. Confirm the Daily Wire membership itself still has access to the content.
3. Reauthorize the Daily Wire connection if required.
4. Restore default API/OAuth endpoints if you customized them.
5. Check WireLoft logs for upstream authentication or middleware errors.

For RSS-specific failures, also verify that the WireLoft feed token/profile remains valid; Daily Wire authentication and WireLoft RSS token authentication are two separate layers.