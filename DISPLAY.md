# E-paper display

Put the dashboard on a battery e-paper screen: grades, missing work and what's coming up, on a
shelf or a fridge, without opening a browser. The display fetches from your dashboard over your
home network, redraws only when something changed, and sleeps in between, so a charge lasts a
long time.

![The display's overview: a white header with the student's name, the page and when the dashboard last updated, grades down the left with a D flagged in a black box with an exclamation mark, a large count of missing assignments in a black box on the right, and upcoming work under it](docs/screenshots/display-overview.png)

*Made-up example data, drawn by the same code the display runs.*

## Hardware

The firmware supports the **Seeed Studio reTerminal E1001**: a 7.5" black-and-white e-paper
screen (800×480) with an ESP32-S3, three buttons and a 2000 mAh battery, charged over USB-C.
[Buy it on Amazon](https://link.amazon/B0e0qUzeC).

Other ESPHome e-paper displays can be added; see [Adding another display](#adding-another-display).

## How it works

1. The display wakes, reads its battery and connects to Wi-Fi.
2. It fetches `/api/display` from your dashboard: one small response with everything it shows.
   Wi-Fi goes off again straight away.
3. If nothing on screen would change, it doesn't redraw. A redraw is the most expensive part of
   a wake, and it makes the screen flash.
4. It sleeps until just after your dashboard's next scheduled update (`SKYWARD_SYNC_CRON`), so it
   never wakes when there can't be anything new: no wakes overnight with the default schedule.
   Change the schedule and the display follows.

A wake takes about 8 seconds, most of it the screen's own refresh (about 4.3 s) and joining
Wi-Fi. The display never talks to Skyward, only to your dashboard, and your dashboard never
fetches anything because of it.

It talks to the dashboard directly rather than through Home Assistant. Home Assistant's ESPHome
connection has to notice the device woke up and push every value to it, which keeps it awake
several times longer on each wake, and every wake is battery.

## Setup

You need [ESPHome](https://esphome.io) **2026.9.0 or later**: the ESPHome add-on in Home
Assistant, or the `esphome` command line.

1. **Back up the stock firmware first** if you might want it back. With the display on USB:

   ```sh
   esptool --port /dev/ttyUSB0 --baud 921600 read-flash 0 0x2000000 reterminal-e1001-stock.bin
   ```

2. Copy [`display/esphome/reterminal-e1001.example.yaml`](display/esphome/reterminal-e1001.example.yaml)
   into your ESPHome folder as `skyward-display.yaml`. Set `dashboard_url` to your dashboard as
   the display will reach it, such as `http://192.168.1.20:8080` (use the host's address, not
   `localhost`). The `ref:` line pins a release; change it to upgrade.
3. Add these to your ESPHome `secrets.yaml`:

   ```yaml
   wifi_ssid: "your network"
   wifi_password: "your Wi-Fi password"
   ota_password: "a password for over-the-air updates"
   ```

4. Flash it over USB the first time: `esphome run skyward-display.yaml`, or *Install → Plug into
   this computer* in the ESPHome add-on. Later updates can go over Wi-Fi in maintenance mode.

The display needs 2.4 GHz Wi-Fi and to reach the dashboard's port. If your devices are on a
separate network (an IoT VLAN, say), allow the display to reach the dashboard host on that port.
It uses plain HTTP on your network; a reverse proxy that asks for a login won't work for it.

## Using it

| Button | Does |
|---|---|
| Right white | Next page |
| Left white | Previous page |
| Green | Next student (when there's more than one) |
| Green, held for 2 s while it wakes | Maintenance mode |

A press wakes the display and goes straight to what you asked for. It stays awake for 30 seconds
after your last press, with the LED on the back lit, then goes back to the overview and sleeps.

The pages, for each student:

- **Overview**: every class's grade for the current grading period, missing work and what's
  coming up. Classes at C- or below have their grade in a black box with a "!". The number of
  missing assignments is in large type in a black box, so you can read it from across a room;
  with nothing missing it says "All caught up".
- **Missing**: all missing work this grading period.
- **Coming up**: upcoming work, soonest first.

The header says when the dashboard last updated from Skyward and the battery level. It says so
if the last update failed, if Skyward rejected the sign-in, or if the data is over a day old.

Other screens you may see:

- **Can't reach the dashboard**: three tries in a row failed. The display keeps its last good
  screen until then, and keeps trying every 30 minutes.
- **Charge me** in the header: under 15%. It wakes half as often to stretch the charge.
- **Battery empty**: under 5%. It stops using Wi-Fi and sleeps until you charge it.
- **Maintenance mode**: awake for 5 minutes with its address on screen, for updates over Wi-Fi
  and for logs (`esphome logs skyward-display.yaml`).

To show one student only, for a display in a child's room, set `student: "0"` (or `"1"`, ...) in
your file. The green button then does nothing.

## Battery life

What decides it is how often the display wakes and how much each wake does:

- **Fewer updates, fewer wakes.** The default schedule updates every 3 hours from 6am to 9pm,
  which is 6 wakes a day. A less frequent `SKYWARD_SYNC_CRON` means fewer.
- **Unchanged data costs little.** A wake that finds nothing new skips the screen refresh.
- **A fixed address helps.** Joining Wi-Fi takes about 4 seconds with DHCP; a `manual_ip` (see the
  example file) makes it quicker on every wake.
- **Button presses** are wakes too.

We haven't measured a full charge yet. The battery level in the header lets you watch it.

## Troubleshooting

- **"Can't reach the dashboard"**: check `dashboard_url` from another device on the same network
  (open `<dashboard_url>/api/display`), that the dashboard is running, and any firewall between
  them. Then press a button to try again.
- **A faint ghost of the previous screen**: normal after many redraws on e-paper; the next full
  refresh clears it.
- **A button doesn't wake it**: hold it a moment. A wake takes a few seconds before the screen
  changes.
- **Logs**: wake it with the green button and keep holding it for 2 seconds (maintenance mode),
  then run `esphome logs skyward-display.yaml`. Or connect USB.

## Adding another display

The firmware is in [`display/esphome/`](display/esphome/), in three parts:

- `devices/<board>.yaml`: the hardware only. It must provide the ids listed at the top of
  [`devices/reterminal-e1001.yaml`](display/esphome/devices/reterminal-e1001.yaml): the display
  `epd`, `deep_sleep_ctl`, the `page_button`, `prev_button` and `student_button` binary sensors,
  the `wake_button` global, the `battery_voltage` sensor, the `status_led` output, and the
  `read_battery` and `quiet_hardware` scripts.
- `common/skyward.yaml`: fetching, the redraw decision, buttons and sleep. Shared by every display.
- `layouts/<size>.yaml`: the drawing, as one ESPHome display lambda. Any 800×480 display can use
  `landscape-800x480.yaml`; another size needs its own layout.

Start a new board with `tests/sleep-test.yaml`, which checks the sleep, wake buttons and panel
refresh without Wi-Fi. `scripts/display_preview.py` renders a layout on your computer as PNGs;
see [DEVELOPING.md](DEVELOPING.md#e-paper-display).

The layout draws with an ESPHome display lambda rather than LVGL. On this panel LVGL added about
0.7 s to every wake (it renders in colour, then converts), for the same picture.

### The `/api/display` contract

Version 1, requested as `/api/display?v=1`. Fields may be added in later releases, never renamed
or removed; a breaking change would be a new version, served alongside this one.

| Field | |
|---|---|
| `v` | `1` |
| `hash` | changes only when something shown changes; compare it to skip a redraw |
| `sleep_seconds` | until just after the next scheduled update, between 15 minutes and 12 hours |
| `updated` | the date of the last successful update, such as `Mon Sep 28` |
| `stale` | the last successful update is over a day old |
| `sync_error` | a short message if the last update failed, else `null` |
| `students[]` | `name` (first name), `grading_period`, `grades[]`, `missing`, `upcoming` |
| `grades[]` | `course`, `letter`, `percent` (text, such as `96.5%`), `struggling` (C- or below), `missing` |
| `missing`, `upcoming` | `count`, `items[]` (capped), `more` (how many weren't sent); `upcoming` also has `due_this_week` |
| `items[]` | `course`, `title`, `due` (`Tomorrow`, `3 days ago`, ...), `date` (`Tue Sep 29`) |

All text is printable ASCII: accents are dropped and curly quotes straightened, so a display's
fonts only need that range.

## Privacy

The display shows a child's grades wherever you put it. Like the dashboard itself, the endpoint
has no login: keep both on your home network. Nothing leaves your network.
