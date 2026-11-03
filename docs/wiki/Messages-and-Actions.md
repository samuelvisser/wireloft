# Messages and actions

WireLoft can tell you when something happens, and do something about it: push a message to your phone, send it to
Discord, Telegram, email or any of the 100+ services Apprise supports, refresh your Jellyfin, Emby or Plex library,
call a webhook, or run your own script.

You set all of this up in **Settings › Messages and actions**.

## Out of the box

A new WireLoft only tells you about problems, as a push message to the devices where you turned push on:

- a download failed after its retries;
- the Daily Wire sign-in expired;
- the disk is almost full;
- a task keeps failing;
- a new WireLoft version is out (once per version).

A daily summary at 08:00 is already there but switched off, so it is one switch away. New downloads are not a default,
because they are the noisy ones: add a rule for them if you want them.

The same problem (the same Show, the same reason) is sent again only after a day.

## This device

Turn push on for the browser or phone you are using, send yourself a test, or turn it off again. The list below it
shows every device that gets push messages, and you can remove one you no longer use.

Push needs WireLoft over HTTPS. On an iPhone or iPad, first add WireLoft to the home screen from the share menu, then
turn push on from the installed app.

## Destinations and services

The next list holds everywhere WireLoft can send a message or that it can call:

- **Push to the installed app** is built in. Turn it on per device under **This device**.
- **Send a message** goes through [Apprise](https://appriseit.com/services/). Pick a service and fill in its fields,
  or paste an Apprise URL. The test button sends a test message.
- **Jellyfin, Emby and Plex** get a library refresh. Enter the address and the API key (for Plex, the Plex token).
  By default only the changed folder is refreshed, and refreshes are collected for about a minute, so 40 downloads in a
  row are one refresh. If the media server sees your files under another path (for example `/downloads` in WireLoft
  and `/media` in Jellyfin), fill in the path mapping.
- **Webhook** sends the details as JSON to an address. The form shows exactly what it sends. A failed call is tried
  again three times over a few minutes.
- **Script** runs an executable from the `scripts` folder next to your `config.yml` (`/config/scripts` in Docker).
  WireLoft never stores the script itself, stops it after its time limit, and writes its output to the log. The script
  receives `WIRELOFT_EVENT`, `WIRELOFT_TITLE`, `WIRELOFT_MESSAGE`, `WIRELOFT_SHOW`, `WIRELOFT_EPISODE`,
  `WIRELOFT_FILE_PATH` and `WIRELOFT_FOLDER` as environment variables. Its test runs it on the newest download.

Passwords, API keys and tokens are stored encrypted and never shown again; the list shows a safe version. Adding a
destination does not change any rule: you add it to the rules you want.

When a destination fails, its row says so with the error. A media server, webhook or script that keeps failing
counts as a problem, so the default "a task keeps failing" rule tells you.

## Rules

Each rule is a sentence: *When an episode is downloaded in any Show, refresh Jellyfin and send it to Discord.*

- **When**: an episode is downloaded, replaced by a better version, or deleted; a download fails; new episodes are found
  but not downloaded (for Shows that download nothing by themselves); the Daily Wire sign-in expires; a task keeps
  failing; the disk is almost full; an update is out; or, for a daily summary, anything happens.
- **In**: any Show, or only the ones you choose.
- **Then**: push it to your devices, and/or send it to destinations. Media servers, webhooks and scripts only run for
  downloads, replacements and deletions.
- **Send it**: right away, grouped per Show once an hour, or in a daily summary at a time you choose.

New downloads of one Show that arrive close together always go out as one message, so a backlog of 40 episodes is one
message, not 40.

Switch a rule off to keep it without using it. **Restore default rules** brings back any default rule you deleted,
without touching your own rules.

The **History** section shows what was sent lately, and why something failed.

## Installing WireLoft as an app

WireLoft can be installed like an app from your browser (for example **Add to Home Screen** on a phone, or the install
button in the address bar on a computer). The installed app opens without the browser around it, shows an offline page
when your server cannot be reached, and can receive push messages.
