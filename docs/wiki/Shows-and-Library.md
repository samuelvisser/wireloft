# Shows and Library

WireLoft separates discovering media, managing it, and downloading it. Adding a show or movie to your Library does not automatically download anything.

## Home

The Home page is the quickest way to see the state of WireLoft. It summarizes active and queued downloads, failed or problematic downloads, recent completions, Library size, and items that need attention.

Use Home when you want to know whether WireLoft is operating normally or something needs your attention.

## Browse

Browse shows Daily Wire content that can be added to WireLoft. Shows and movies are kept separate so it is easier to find the kind of media you want.

Adding an item from Browse creates a managed entry in your Library. For shows, WireLoft indexes seasons and episodes. For movies, WireLoft stores the information needed for the local movie page and downloads.

## Library

Library contains the shows and movies you have chosen to manage.

It has separate Shows and Movies views. Show filters are remembered in that browser, so returning to the Library restores the last show-type selection you used.

### Shows

A show page brings together its seasons and episodes, current publication state, local downloads, Download Profiles, RSS Stream Profiles, manual synchronization, and recent sync history.

A show can stay in the Library without any download or RSS profiles. This is useful when you only want WireLoft to index it for now.

### Podcast and Series shows

WireLoft distinguishes Podcast and Series shows because their automatic download rules are different.

- Podcast Download Profiles are usually based on a rolling date window, a number of recent episodes, or no limit.
- Series Download Profiles are based on selected seasons and can automatically include future seasons.

See [[Download-Profiles]].

## Seasons and episodes

Series can contain multiple seasons. The show page lets you switch between them rather than treating the entire show as one long list.

Episodes can also have different Daily Wire types, such as regular episodes and auxiliary items. Profiles can choose which types they apply to.

An episode can appear in WireLoft before final downloadable media exists. You may therefore see an episode that is scheduled, live, processing, still using a countdown version, final, or temporarily unavailable. WireLoft continues monitoring recent non-final episodes automatically.

## Sync now and sync history

WireLoft checks managed shows automatically, but a show's **Sync now** action checks that show immediately.

Use it when you know Daily Wire has published something and you do not want to wait for the next scheduled check.

The show also keeps recent synchronization results. This helps distinguish between WireLoft not having checked yet and a successful check that found nothing new.

## Local copies of episodes

An episode can have more than one local copy when different Local Media Profiles are used, for example an audio version and a 1080p video version.

The episode page shows its downloads, formats, file sizes, and download history. Queue-wide activity is available from the main **Downloads** page. See [[Downloads-and-File-Integrity]].

## Movies and extras

Movies are managed separately from shows and are downloaded manually rather than through show Download Profiles.

A movie page can include the main movie, descriptive and release metadata, available download formats, movie extras supplied by Daily Wire, and download progress/history.

Upcoming movies can be added to the Library before their final media is available. WireLoft keeps the local movie entry available and can refresh its Daily Wire metadata as the release approaches.

Movie output templates should distinguish the main movie from extras so different items cannot use the same filename. See [[Local-Media-Profiles#movies-and-extras]].

## Profiles and files are separate

A Local Media Profile describes the local file WireLoft should create. A Download Profile describes which show episodes should be downloaded automatically. An RSS Stream Profile describes a private feed. A download record represents actual file activity.

Changing or deleting a profile is therefore not the same as deleting a downloaded file. Before changing retention or removing profiles, review the affected show and its existing downloads so the result matches what you intend to keep.