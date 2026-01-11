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

## Word of caution

50five's API only updates transaction data every 15m, so take this into account
when using this integration. Charger status takes about 10-15s to change after
starting/stopping a session.
