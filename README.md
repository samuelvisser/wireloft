<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="docs/assets/logos/logo-wide-wireloft-white.png"
    >
    <source
      media="(prefers-color-scheme: light)"
      srcset="docs/assets/logos/logo-wide-wireloft-black.png"
    >
    <img
      src="docs/assets/logos/logo-wide-wireloft-black.png"
      alt="WireLoft Logo"
      width="450"
    >
  </picture>
</p>

<h2 align="center">Higly polished self-hosted Local Media Manager and RSS generator for The Daily Wire</h2>


<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="docs/assets/screenshots/1.2.2-library-dark.png"
    >
    <source
      media="(prefers-color-scheme: light)"
      srcset="docs/assets/screenshots/1.2.2-library-light.png"
    >
    <img
      src="docs/assets/screenshots/1.2.2-library-light.png"
      alt="WireLoft Home Screen"
      width="700"
    >
  </picture>
</p>

<p align="center">
  <picture>
    <source
      media="(prefers-color-scheme: dark)"
      srcset="docs/assets/screenshots/1.2.2-collection-movie-episode-dark.png"
    >
    <source
      media="(prefers-color-scheme: light)"
      srcset="docs/assets/screenshots/1.2.2-collection-movie-episode-light.png"
    >
    <img
      src="docs/assets/screenshots/1.2.2-collection-movie-episode-light.png"
      alt="WireLoft Home Screen"
      width="700"
    >
  </picture>
</p>

## What it does

WireLoft is an easy-to-use, highly polished self-hosted app for managing (premium) media from The Daily Wire. 

It is built for self-hosting nerds who want to enjoy premium shows from The Daily Wire without being limited to its website or app. WireLoft allows you to download individual show episodes to your server, or stream audio and video episodes straight to your RSS podcast client without having to download anything server-side first.

WireLoft is highly customizable to fit your exact needs. You can automatically download audio for every item in a show while downloading video only for full episodes, do it the other way around, or configure something entirely different. You can simply index a show, stream its contents directly from The Daily Wire's servers to your favorite podcast app, download every episode, or download only the subset you are interested in. Whatever you want.

WireLoft works with movies hosted by The Daily Wire as well. Download any movie you have access to and enjoy it through your local media server, such as Jellyfin or Plex, or simply watch it locally.

This project was inspired by [Pinchflat](https://github.com/kieraneglin/pinchflat), an awesome project that allows you to automatically download videos from YouTube channels and playlists. WireLoft takes that concept to The Daily Wire and expands on it greatly. In addition to automatically managing shows, WireLoft supports individual episodes and movies, making it a true one-stop shop for all things The Daily Wire.

WireLoft is not meant to be used for consuming the content itself; it downloads, organizes, or streams it for you. For downloaded content, use a self-hosted media server such as Plex or Jellyfin for video, or Audiobookshelf for podcasts and audio. For RSS, use the WireLoft- generated RSS stream in you favorite podcast app and consume the content there.  
Despite everything it offers, WireLoft is designed to remain easy to install and use: launch the Docker container, open the Web UI, and everything will explain itself. My philosophy with this software is to
allow basically any configuration you can think of, but help you through advisory messages where needed how your setup could improve, usually even with a button to apply it automatically. This keeps you
in control while not throwing you in the dark.


## Features

- Fully featured, easy-to-use Web UI for navigation and configuration.
- Download series, podcasts, movies, and premium content using your The Daily Wire subscription.
- Create multiple media profiles for the same show — for example, automatically maintain separate video and audio downloads.
- Organize your library exactly how you want with configurable naming, directory structures, and powerful Jinja templates.
- Automatically embed metadata and artwork, generate NFO files, and download show assets for media servers such as Jellyfin and Plex.
- Intelligently handles live episodes, avoiding countdown footage and waiting for the proper published version when appropriate.
- Create private audio or video RSS feeds for your shows and use them in your favorite podcast app.
- Stream live episodes through RSS, with stable episode URLs that can seamlessly transition to locally downloaded media once available.
- Automatically discover, download, refresh, and clean up media in the background.
- Configure automatic retention rules to remove older content from your server.


## Install WireLoft as an app

WireLoft is installable as a Progressive Web App (PWA). Open your WireLoft
instance in a supported browser, then choose **Install app** (Chrome/Edge on
desktop or Android), or **Share → Add to Home Screen** (Safari on iPhone/iPad).
The installed app opens in its own window, using the WireLoft icon.

For installation, use **HTTPS** (or `localhost` when developing). A plain
`http://` connection to a remote server or LAN IP is not sufficient for
service worker registration in most browsers. Reverse-proxy setups should
preserve HTTPS when exposing WireLoft remotely.

Only versioned frontend assets are cached. The app shell is fetched fresh on
every online navigation, and API data, authentication, feeds, runtime config,
and media downloads are **never** cached by the service worker. Offline, the
installed app displays a reconnect screen; media management requires a
connection to your WireLoft server.

### Push notifications

In **Settings → General → Push notifications**, choose **Enable push notifications**
and grant the browser permission. Select which events should generate OS alerts:
finished downloads, failures, scheduled tasks, and other operations. These
preferences and permissions are configured **separately for each device**.

When the WireLoft tab is visible and focused, its existing operation toasts
are shown instead. If no foreground tab acknowledges an operation, the backend
delivers an OS-level notification after a short grace period, even when the
installed PWA is closed. Clicking a notification opens the relevant WireLoft
page. Settings also contains a recent-operation history so missed results are
still accessible.

iOS/iPadOS requires installing WireLoft to the Home Screen and using HTTPS.
On other platforms use a supported browser and HTTPS (or `localhost` for
development). Web Push delivery uses Apprise's VAPID plugin. The backend needs outbound HTTPS
access to the browser vendor's push service. No third-party account or paid notification service is required.
Push delivery is best-effort; blocked permissions or unreachable push services
can prevent OS-level delivery.

## Running with Docker

The best way to run WireLoft is using its Docker container. Everything is managed for you automatically within the container.


### Quick start: use the published image

Run the following to get started immediately:

```bash
mkdir wireloft && cd wireloft
curl -O https://raw.githubusercontent.com/samuelvisser/wireloft/develop/.docker/docker-compose.yml
docker compose up -d
```

Then open http://localhost:5273.

See **Volumes** and **Useful environment variables** below for persistence and configuration options. Edit the Compose file in place if you want to change anything beyond the defaults.


### Or create the Compose file yourself

```yaml
services:
  wireloft:
    image: ghcr.io/samuelvisser/wireloft:latest
    restart: unless-stopped
    ports:
      - "5273:80"
    volumes:
      - ./config:/config
      - ./downloads:/downloads
    environment:
      # Set the timezone to your local timezone
      - TZ=UTC
```


### Setup

#### Volumes

* `/config` -- App configuration (`config.yml`), the SQLite database, session secret key, and your Daily Wire login token. Persist this directory so your settings, shows, and login survive container restarts and upgrades.
* `/downloads` -- Downloaded episodes and movies.

#### Useful environment variables

* `TZ` -- Container timezone. Defaults to `UTC`.
* `WL_ADMIN_AUTH__PASSWORD` -- Set this to require a password to access the Web UI. Leave it unset for open access on your local network. Always set this when exposing WireLoft through a reverse proxy.
* `API_URL` -- Override the API base URL given to the Web UI. This defaults to the relative `/api`, which works out of the box regardless of which host port you map.

Literally every setting WireLoft provides can be managed by environment variables, too. However, I generally do not advise
using environment variables for anything but the above examples. Any setting configured by environment variable cannot be changed in the WireLoft UI.

See the [Settings documentation](https://github.com/samuelvisser/wireloft/wiki/Settings) for all available settings, including their `config.yml` keys, environment variables, defaults, and explanations.


## Special thanks

While WireLoft is built entirely from the ground up with original code, the open-source [DailyWirePodcastProxy](https://github.com/fpnewton/DailyWirePodcastProxy) project has helped tremendously in figuring out how The Daily Wire API works. 
DailyWirePodcastProxy allows you to access premium versions of Daily Wire shows directly from your podcast app. Definitely check it out if you're interested!


## Disclaimer
This project is not affiliated with or endorsed by The Daily Wire. Only connect a Daily Wire account you are authorized to access,
and comply with all applicable terms and laws.