# First-Run Setup

On first launch, WireLoft walks through four stages: welcome, Daily Wire connection, security, and adding the first media item.

## 1. Connect your Daily Wire account

WireLoft uses Daily Wire's **device authorization flow**. You follow the sign-in instructions provided by Daily Wire and authorize WireLoft there; WireLoft does not ask for or store your Daily Wire password.

Connecting an account allows WireLoft to access content included with that membership. This is required for premium downloads and for RSS profiles that stream premium media directly from Daily Wire.

You can skip this step if you want, WireLoft will also work without a Daily Wire account attached for any content that is publicly accessible. If you can view it on The Daily Wire website without
a login, WireLoft can use it without Daily Wire authentication.

## 2. Protect the WireLoft UI

WireLoft's administrator login is separate from your Daily Wire account. Configure it on the container with:

```yaml
environment:
  WL_ADMIN_AUTH__PASSWORD: "choose-a-long-unique-password"
```

Restart WireLoft after changing the variable.

If no administrator password is configured, anyone who can reach the WireLoft web interface can control the application. Authentication is especially important when WireLoft is available through a reverse proxy.

See [[Security-and-Remote-Access]] for the distinction between UI authentication and private RSS-feed tokens.

## 3. Add your first show or movie

The final setup stage opens the normal WireLoft media workflow.

For a **show**, select it from Browse and use the Add Show wizard. The wizard can:

- add/index the show without downloading it;
- create a Local Media Profile describing the desired format and output path;
- create a Podcast or Series Download Profile;
- create an RSS Stream Profile.

For a **movie**, select it from Browse, create or select a Movie Local Media Profile, and add/download the movie from its page.

You may also skip adding media during onboarding and configure it later from the normal interface.

## Recommended first setup

For most installations:

1. Persist both `/config` and `/downloads`.
2. Set `TZ` to your local [IANA](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones#List) timezone.
3. Connect your Daily Wire account.
4. Set `WL_ADMIN_AUTH__PASSWORD` if WireLoft is accessible outside a completely trusted LAN.
5. Add one show without aggressive download rules first, then verify its metadata and available episode types.
6. Create the Local Media Profile(s) you actually want.
7. Add Download Profiles for automatic retention.
8. Add an RSS Stream Profile only after deciding whether the feed should use local downloads, Daily Wire streaming, or both.

This separation makes it easier to change storage or RSS behavior later without removing the show itself.