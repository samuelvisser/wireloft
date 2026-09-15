# Daily Wire Integration

WireLoft connects to The Daily Wire for catalog information, show and episode metadata, account authorization, and media access. Most of this happens automatically; the main thing you need to decide is whether to connect a Daily Wire account.

## Connecting your account

WireLoft uses Daily Wire's device authorization flow. When you connect an account, WireLoft gives you instructions for authorizing the device through Daily Wire itself.

Your The Daily Wire password is never entered into WireLoft.

The connection is stored with WireLoft's persistent application data under `/config`, so it normally survives container recreation and upgrades.

## Public and member-exclusive content

WireLoft does not bypass The Daily Wire membership restrictions.

- Public content can be browsed and used without connecting an account when The Daily Wire exposes it publicly.
- Member-exclusive downloads require a connected account with access to that content.
- RSS profiles that fall back to The Daily Wire also require the connected account to have access to any member-exclusive media they serve.

The secret token in a WireLoft RSS URL only authorizes access to that WireLoft feed.

## Browse and Library

**Browse** shows content WireLoft can discover from The Daily Wire. Adding something creates a managed copy of its metadata in **Library**.

Once a show is in your Library, WireLoft will keep its seasons and episodes synchronized even if you never download a file. Downloads and RSS feeds are optional behavior layered on top of the Library.

## New episodes and changing metadata

WireLoft checks managed shows for new episodes every 30 minutes by default. Episodes that are scheduled, live, processing, or otherwise still settling are checked more frequently until their media becomes usable and final.

The Daily Wire can also change titles, thumbnails, episode numbers, or other metadata after publication. WireLoft performs several follow-up refreshes for recently published episodes so those changes can settle without repeatedly refreshing your entire historical library.

You can use **Sync now** on a show whenever you want to check that show immediately rather than wait for the next scheduled discovery pass.

To re-check every episode in a show that WireLoft knows about with the version The Daily Wire currently publishes, use **Refresh all metadata** on a show.
This is a heavy task with many API requests, so WireLoft automatically paces it to prevent hitting The Daily Wire's API rate limits.

See [[Automation-and-Background-Tasks]] for the default schedules.

## Live and newly published episodes

A Daily Wire episode may appear before its final media is ready. Depending on the show, WireLoft may see a scheduled or live item, a temporary countdown version, processing media, and eventually the final episode.

Podcast Download Profiles can choose whether to:

- wait for the final version;
- download an early countdown version;
- download early and replace it when the final version becomes available.

See [[Download-Profiles]].

## The Daily Wire streaming in RSS feeds

An RSS Stream Profile can use The Daily Wire as a media source instead of requiring every episode to be stored locally.

This is useful when you want a large feed without keeping the complete back catalog on disk. A common setup is to keep recent episodes downloaded locally and let older episodes fall back to Daily Wire.

WireLoft resolves current media when the podcast client requests it, so temporary upstream media URLs are handled by WireLoft rather than stored permanently in the podcast application.

See [[Podcast-RSS-Feeds]].

## Advanced integration settings

The **Settings → DailyWire** page contains advanced options for API endpoints, OAuth client details, and request pacing. These are copied from how the Apple TV connects to The Daily Wire.
Ordinary installations should leave these at their defaults.

Changing these values can prevent authorization or media access from working. If you changed them while troubleshooting, restore the defaults before assuming the Daily Wire account itself is broken.

See [[Settings#daily-wire-integration]].

## TMDB is separate

WireLoft can optionally use TMDB for movie metadata such as release-date information used for matching and file naming. TMDB is separate from your The Daily Wire account and has its own optional API token under **Settings → Advanced**.

TMDB integration was added when The Daily Wire did not use to provide reliable movie release date information. It provides this information reliably now,
making TMDB integration almost certainly obsolete. Im keeping it around for now, and WireLoft will automatically fall back to it if The Daily Wire ever stops
publishing release dates. But as that is unlikely to happen, TMDB integration will likely be removed in a later version of WireLoft unless I find another good
use-case for it.


## Authentication troubleshooting

If member-exclusive content stops working:

1. Open **Settings → DailyWire** and check whether WireLoft is still connected.
2. Confirm your Daily Wire membership can access the same content on Daily Wire itself.
3. Reauthorize the WireLoft connection if necessary.
4. If you changed advanced Daily Wire endpoints or OAuth settings, restore their defaults.
5. Check the WireLoft log or the affected download's log for the specific error.

WireLoft should deal with authentication errors automatically, without requiring the above steps. If you encounter any, please report them to me.

For RSS-only problems, also check the Stream Profile and its feed token. Daily Wire authentication and WireLoft RSS access are separate.