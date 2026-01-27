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

The integration discovers all chargers linked to your account and creates
devices and sensors for each discovered charger.

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

It is a deliberate choice not to offer switches out of the box in this
integration. The reason being that users can have multiple cards, chargers and
channels associated with their accounts. Foreseeing switches for all possible
combinations out-of-the-box would lead to a whole bunch of switches littering
your instance, with most of them likely to never be used. The easiest solution
therefore is to simply point people towards template helpers, which allow you
to create your own switches from the UI for the card/charger/channel combos you
prefer. The process is pretty simple:

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

## Word of caution

50five's API only updates transaction data every 15m, so take this into account
when using this integration. Charger status takes about 10-15s to change after
starting/stopping a session.

### Channel support

I do not have a charger with multiple channels, nor do I have any idea how the
api behaves in case there are multiple channels. If you have multiple channels
on your charger, please open an issue so we can figure out if anything breaks.
