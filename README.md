# Home Assistant 50five custom integration

This custom integration allows you to interact with your 50five managed EV
charger. It allows starting/stopping charge session as well as exposes some
data about the charger (on-going sessions, status, ...) as sensors.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Crazy-Duck&repository=home-assistant-fiftyfive&category=integration)

Alternatively:

1. Install [HACS](https://hacs.xyz) if not already installed
1. Search for "50five" in HACS
1. Click **Download**
1. Restart Home Assistant
1. Add via Settings → Devices & Services

### Manual Installation

1. Copy the `custom_components/fiftyfive` folder to your `<config>/custom_components/` directory
1. Restart Home Assistant
1. Add via Settings → Devices & Services

## Configuration

### Adding your charger

1. Navigate to **Settings** → **Devices & Services**
1. Click **+ Add Integration**
1. Search for **50five**
1. Enter your 50five account credentials:
    - **Username**: Your 50five username (your e-mail address by default)
    - **Password**: Your account password
    - **Market**: The market in which your account was created
    - **Customer type**: Whether you're a native 50five customer or a former
                         Shell one

The integration discovers all chargers linked to your account and creates
devices and sensors for each discovered charger.

### Two-factor authentication (2FA)

The 50five / EVC-Net portal protects accounts with **e-mail based two-factor
authentication**. When it is enabled on your account the setup becomes a two
step process:

1. Enter your credentials (see above) and click **Submit**. 50five will e-mail
   a one-time verification code to the e-mail address of your account.
1. A second form appears asking for the **Verification code**. Open the e-mail
   from 50five, copy the code, paste it into the field and click **Submit**.

Once the code is accepted the integration stores the authenticated session so
that normal polling does **not** require a new code.

#### How long does the session last?

The 50five portal keeps a session valid for about **24 hours** after the 2FA
step (`PHPSESSID` cookie, `Max-Age=86400`). To make the session last as long as
possible the integration:

* **Reuses** the stored session cookies for all polling (no new code needed
  between polls).
* **Persists the freshest cookies** after every successful poll, so a Home
  Assistant restart within the 24h window keeps working without a new code
  (rather than falling back to the possibly-stale cookie captured at setup).

#### What happens when the session expires?

On every poll the integration verifies it can still fetch data from the portal.
When the session has expired the portal stops returning data, and the
integration:

1. Raises an authentication failure, which makes Home Assistant show a
   **"Reconfigure" / re-authentication** repair notification for the
   integration (the entities go *unavailable* rather than silently showing
   stale data).
2. Lets you re-authenticate: open the notification, confirm your (pre-filled)
   password and enter the **new verification code** that 50five e-mails you.
   Polling resumes automatically.

> [!NOTE]
> Because the verification code is delivered by e-mail it cannot be obtained
> unattended, so this ~24h re-authentication is expected and cannot be fully
> automated. Accounts without 2FA continue to work with a single step as
> before.

### Update notifications

The integration automatically checks for new releases on GitHub once every 24
hours (starting when the integration loads). When a newer version is available:

* A **notification appears in Home Assistant's notification center** with the
  installed and latest version numbers, and a link to the release notes.
* The `binary_sensor.<charger>_update_available` sensor turns **ON**.

The notification automatically dismisses itself once you update to the latest
version.

#### Troubleshooting update notifications

If you've updated the integration but the notification still shows an old
version, or no notification appears at all:

1. **Check the logs** for `50five update check` entries:
   - Go to **Settings** → **System** → **Logs**
   - Search for `50five`
   - Look for messages like:
     * `50five update check started (installed: X.X.X)`
     * `A new 50five release is available: X.X.X`
     * `Update notification created`

2. **Verify the installed version**:
   - The integration reads the version from its own `manifest.json`
   - If you installed manually, make sure you copied **all files** including
     the updated manifest
   - HACS users: the version should update automatically after clicking
     "Update" and restarting

3. **Trigger a manual check**:
   - Restart Home Assistant (the update check runs on startup)
   - Or wait up to 24 hours for the next automatic check

4. **Check GitHub API access**:
   - The integration queries
     `https://api.github.com/repos/pimhofstee/50five-HA-2fa/releases/latest`
   - If your Home Assistant instance has no internet access or GitHub is
     unreachable, the check will fail silently (logged at WARNING level)

### Actions

#### Available service actions

There are 7 service actions exposed through this integration which can be
launched via the developer tools, helpers, automations, ... They are:

* Start a charge session on a charger with a given card 
* Stop an active session on a charger
* Unlock the connector from a charger
* Block a charger
* Unblock a charger
* Soft reset a charger
* Hard reset a charger

#### Buttons / switches

It is a deliberate choice not to offer start/stop charging switches out of the
box in this integration. The reason being that users can have multiple cards,
chargers and channels associated with their accounts. Foreseeing switches for
all possible combinations out-of-the-box would lead to a whole bunch of 
switches littering your instance, with most of them likely to never be used.
The easiest solution therefore is to simply point people towards template
helpers, which allow you to create your own switches from the UI for the 
card/charger/channel combos you prefer. The process is pretty simple:

* Go to `Settings` > `Devices & services` > `Helpers`
* Click `+ Create helper`
* Select `Template`
* Select `Switch`
* Give it a name
* Click `+ Add action` for `Actions on turn on` and `Actions on turn off`
* Scroll down to `Other actions` and select 50five from the list
* Select the `Start a charge session`/`Stop a charge session` action on the 
  right
* Select the charger from the dropdown and add the card RFID below
* Click `Submit`

The switch will now show up in the `Overview` dashboard. Additionally you can
assign it an area in the house in its settings.

## Power usage history

The charging-power sensor is backfilled with Home Assistant long-term
statistics using the same data the 50five portal graphs (its dashboard
`current` service). On startup and hourly thereafter the integration imports
the portal's hourly power history so the sensor's *Statistics* graph shows the
recent past.

Note: the portal only exposes roughly the **last three days** of hourly power
data, so that is as far back as the history can be filled. Older history simply
isn't available from 50five.

## Update notifications

When a newer release of this integration is available on GitHub (`pimhofstee/50five-HA-2fa`), you'll get notified in **two ways**:

### 🔔 Automatic notification (no setup needed)
A notification appears automatically in your **Home Assistant notification center** with:
- Installed and latest version numbers
- Link to the release notes on GitHub

The notification **auto-dismisses** when you update to the latest version.

### 📊 Binary sensor (for custom automations)
The integration also provides a **binary sensor** (`binary_sensor.fiftyfive_update_available`) that turns **ON** when a newer release is available. The sensor's attributes include:
- `installed_version` — your current version
- `latest_version` — latest version on GitHub
- `release_url` — link to the release page

Use this sensor to build custom automations (send mobile notifications, flash lights, add to dashboards, etc.).

Both features check at **startup + once every 24 hours**. Update via HACS as usual.

**Example automations:**

**Send a persistent notification:**
```yaml
automation:
  - alias: "Notify when 50five update available"
    trigger:
      - platform: state
        entity_id: binary_sensor.fiftyfive_update_available
        to: "on"
    action:
      - service: persistent_notification.create
        data:
          title: "50five update available"
          message: >
            Installed: {{ state_attr('binary_sensor.fiftyfive_update_available', 'installed_version') }}
            Latest: {{ state_attr('binary_sensor.fiftyfive_update_available', 'latest_version') }}
            
            [View release]({{ state_attr('binary_sensor.fiftyfive_update_available', 'release_url') }})
```

**Send mobile notification:**
```yaml
automation:
  - alias: "Mobile notification for 50five update"
    trigger:
      - platform: state
        entity_id: binary_sensor.fiftyfive_update_available
        to: "on"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "50five update available"
          message: "Version {{ state_attr('binary_sensor.fiftyfive_update_available', 'latest_version') }} is now available!"
          data:
            url: "{{ state_attr('binary_sensor.fiftyfive_update_available', 'release_url') }}"
```

**Flash a dashboard light:**
```yaml
automation:
  - alias: "Flash light for 50five update"
    trigger:
      - platform: state
        entity_id: binary_sensor.fiftyfive_update_available
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.office
        data:
          rgb_color: [255, 165, 0]
          flash: short
```

**Add to dashboard:**
Simply add `binary_sensor.fiftyfive_update_available` to any Lovelace card. It will show ON/OFF status and the installed/latest version attributes.

## Word of caution

50five's API only updates transaction data every 15m, so take this into account
when using this integration. Charger status takes about 10-15s to change after
starting/stopping a session.

### Channel support

I do not have a charger with multiple channels, nor do I have any idea how the
api behaves in case there are multiple channels. If you have multiple channels
on your charger, please open an issue so we can figure out if anything breaks.
