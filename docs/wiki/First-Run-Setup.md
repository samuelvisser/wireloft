# First-Run Setup

On first launch, WireLoft guides you through connecting The Daily Wire, reviewing security, and adding your first media. You can skip optional steps and finish them later from the normal interface.

## 1. Connect The Daily Wire

WireLoft uses The Daily Wire's device authorization flow. Follow the instructions shown by WireLoft and authorize the connection on Daily Wire's own site.

WireLoft does **not** ask for your Daily Wire password.

Connecting an account is required for member-exclusive content. You can skip this step if you only want to use content that Daily Wire makes publicly available without signing in.

You can reconnect or change the Daily Wire session later from **Settings → DailyWire**.

## 2. Decide how WireLoft should be protected

WireLoft's administrator login is separate from your Daily Wire account.

If your installation is only reachable on a trusted private network, the administrator login is optional. If WireLoft is reachable through a reverse proxy or from an untrusted network, configure a long unique password with:

```yaml
environment:
  - WL_ADMIN_AUTH__PASSWORD=choose-a-long-unique-password
```

Restart the container after changing it.

Private RSS feeds do not use this administrator login. Each feed has its own secret URL. See [[Security-and-Remote-Access]].

## 3. Confirm your download storage

If you are using the supplied Docker Compose layout, open **Settings → Downloads** and confirm **Download root** is `/downloads`. That points WireLoft at the persistent `./downloads:/downloads` media mount from the Compose file.

If you choose **Save to temporary folder first**, also review the **Temporary download folder** and make sure that location has enough free space for the media you download.

## 4. Add your first show or movie

Open **Browse** to see Daily Wire content that can be added to your Library.

### Shows

When you add a show, the wizard can set up any combination of:

- the show itself, with no automatic downloads;
- a **Local Media Profile** describing the file format, download behavior, and output path;
- a **Download Profile** for automatic podcast or series downloads;
- an **RSS Stream Profile** for a private podcast/video feed.

You do not have to configure everything at once. A good first step is to add the show, confirm its seasons and episodes look correct, and then add the download/RSS behavior you want.

### Movies

Movies use Movie Local Media Profiles and are downloaded manually from their movie page. When Daily Wire provides extras such as trailers or featurettes, those can be downloaded from the same page using the movie profile.

Upcoming movies can remain in your Library before the actual media is available.

## A simple first configuration

For most installations:

1. Make sure `/config` and `/downloads` are persistent.
2. For the supplied Docker layout, set **Download root** to `/downloads`.
3. Set `TZ` to your local timezone.
4. Connect your Daily Wire account if you use member content.
5. Protect the WireLoft UI if it is not confined to a trusted network.
6. Add one show from Browse.
7. Create a Local Media Profile with the format and folder structure you want.
8. Add a Download Profile if you want automatic downloads.
9. Add an RSS Stream Profile only if you want to use WireLoft as a private podcast/video feed.

From there, **Home** shows the current health of the instance, **Library** contains your managed media, and **Downloads** shows actual file activity.

For the profile concepts in more detail, see [[Local-Media-Profiles]], [[Download-Profiles]], and [[Podcast-RSS-Feeds]].