# JACKPOINT
### *"The sky above the port was the color of television, tuned to a dead channel."*

---

```
 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 ░                                                   ░
 ░   J A C K P O I N T                               ░
 ░   Evil Portal Framework // WiFi Pineapple Pager   ░
 ░                                                   ░
 ░   "Plug in. Ghost out. Leave nothing."            ░
 ░                                                   ░
 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
```

---

## // WHAT IS A JACKPOINT

In the sprawl, a **jackpoint** is where you breach the net. A covert access node — invisible to the suits, lethal to their data.

This payload turns your WiFi Pineapple Pager into exactly that.

**JackPoint** spins up a rogue access point, clones the SSID of any real network in range, serves a convincing captive portal from a library of preloaded phishing pages, and logs every credential that walks through the door — all from a device that fits in your pocket and looks like a pager from 1994.

The mark connects. The mark types their password. You already have it.

---

## // COMPATIBILITY

JackPoint portals are **100% compatible with Flipper Zero Evil Portal HTML files.**

No conversion. No size limits. Drop any `.html` from the Flipper ecosystem directly into the `portals/` folder and it works. The Pager has no 20KB ceiling — serve anything.

Community portal libraries that work out of the box:
- [bigbrodude6119/flipper-zero-evil-portal](https://github.com/bigbrodude6119/flipper-zero-evil-portal)
- [FlippieHacks/FlipperZeroEuropeanPortals](https://github.com/FlippieHacks/FlipperZeroEuropeanPortals)
- [fxip/evilportal](https://github.com/fxip/evilportal)
- [Shlucus/FlipperZero-GooglePortal](https://github.com/Shlucus/FlipperZero-GooglePortal)

---

## // HARDWARE

```
Device  : Hak5 WiFi Pineapple Pager
Display : 480x222 RGB565
Radios  : Dual — wlan0 (AP) + wlan1mon (deauth/monitor)
Library : libpagerctl.so + pagerctl.py
```

Two radios. One serves the trap. One hunts the target.

---

## // FILE STRUCTURE

```
/root/payloads/user/attacks/jackpoint/
├── payload.sh              ← Launch script
├── jackpoint.py            ← Pagerctl UI + orchestration
├── portals/                ← Drop your HTML files here
│   ├── google.html
│   ├── facebook.html
│   ├── att_wifi.html
│   ├── hotel_wifi.html
│   └── ...                 ← Any .html appears in the menu
└── loot/
    └── credentials.log     ← Everything they give you
```

---

## // THE RUN

```
[ BOOT ]
  Scan nearby APs
  Select target SSID — or enter custom
  ↓
[ PORTAL SELECT ]
  Browse portal files with D-PAD
  Preview name on display
  A = Select
  ↓
[ GOING HOT ]
  wlan0  → Rogue AP spins up, cloned SSID
  wlan1  → Deauth flood hits real AP (optional)
  nginx  → Serves selected portal HTML
  All traffic → captive portal redirect
  ↓
[ LIVE FEED ]
  Credentials display on screen in real time
  Logged to loot/credentials.log
  ↓
[ EXFIL ]
  B = Tear it all down
  Services restored
  Pager returns to dashboard
```

---

## // CONTROLS

| Button | Action |
|--------|--------|
| D-PAD UP/DOWN | Navigate menus / scroll portal list |
| D-PAD LEFT/RIGHT | Toggle options (deauth on/off, etc.) |
| A (GREEN) | Select / Confirm / Launch |
| B (RED) | Back / Cancel / Emergency stop |

---

## // ADDING PORTALS

Any `.html` file dropped into `portals/` appears automatically in the portal picker. No configuration required.

**To use a Flipper Zero portal:**
1. Find the `index.html` from any Flipper evil portal repo
2. Rename it to something descriptive — `google_signin.html`, `corp_wifi.html`, etc.
3. Drop it in `portals/`
4. It appears in JackPoint's menu on next launch

**To build your own:**
The portal HTML just needs a `<form>` that POSTs credentials. JackPoint's web server catches any POST and logs the fields. Keep it self-contained — inline your CSS and JS, no external dependencies.

---

## // LOOT

Captured credentials are written to `loot/credentials.log`:

```
[2077-03-15 02:34:11] PORTAL: google_signin.html  SSID: GoogleGuest
  email     : t.anderson@metacortex.com
  password  : W@keUp_Neo1999
  useragent : Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)
  client_ip : 192.168.4.23

[2077-03-15 02:41:55] PORTAL: corp_wifi.html  SSID: ZionCorp-Guest
  username  : morpheus
  password  : RedPill0101
  useragent : Mozilla/5.0 (Linux; Android 14)
  client_ip : 192.168.4.31
```

---

## // INSTALLATION

```bash
# Clone or copy to Pager
scp -r jackpoint root@172.16.52.1:/root/payloads/user/attacks/

# Drop your portal files
scp my_portal.html root@172.16.52.1:/root/payloads/user/attacks/jackpoint/portals/

# Launch from Pager dashboard
# Attacks > JackPoint
```

---

## // DEPENDENCIES

- `hostapd` — AP management
- `dnsmasq` — DHCP + DNS spoofing  
- `nginx` — Portal serving
- `libpagerctl.so` — Display + input (via PAGERCTL utility)

All available on the Pager. Nothing to install.

---

## // DISCLAIMER

```
This tool is for authorized security testing and educational
purposes only. Use only on networks and systems you own or
have explicit written permission to test.

The operator assumes all responsibility.
The Pager asks no questions.
```

---

## // AUTHOR

```
wickedNull
"I put the message in the medium."
```

---

*"The Matrix is everywhere. It is all around us."*
*This payload is for the people who already knew that.*
