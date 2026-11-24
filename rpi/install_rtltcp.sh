#!/bin/bash
# RADIMCOM remote dongle server: installs rtl_tcp for every RTL-SDR dongle on a clean Raspberry Pi OS
# (Bookworm / Trixie, 32 or 64 bit; any Debian based Linux should work).
#
#   scp -r rpi pi@<pi>:          (this folder: install_rtltcp.sh + rtltcp_manager.py)
#   ssh pi@<pi> "sudo bash rpi/install_rtltcp.sh"
#
# What it does:
#   1. builds the rtl-sdr-blog driver (rtl_tcp, rtl_test, rtl_eeprom; works with V3, V4 and the generic
#      dongles) into its own folder /opt/rtlsdr-blog: a librtlsdr already on the system (Debian package or
#      an own build used by rtl_433, SoapySDR, wmbusmeters ...) stays untouched and is not used by us
#   2. blacklists the DVB-T kernel driver that grabs the dongles
#   3. installs the service rtltcp-manager: one rtl_tcp per dongle by serial, fixed port per serial
#      (first 1234, then 1235 ...), dongles plugged in later start by themselves,
#      list for RADIMCOM: http://<pi>:1233/dongles.json
# Running it again updates everything and keeps /etc/rtltcp (settings and the port map).
#
# rtl_tcp has no password: anyone on the network can use the dongles. Keep the Pi in your LAN only.
set -euo pipefail

RTLSDR_REPO="https://github.com/rtlsdrblog/rtl-sdr-blog.git"
RTLSDR_REF="${RTLSDR_REF:-master}"
SRC_DIR="/usr/local/src/rtl-sdr-blog"
PREFIX="/opt/rtlsdr-blog"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo bash $0"; exit 1; }
[ -f "$HERE/rtltcp_manager.py" ] || { echo "rtltcp_manager.py must be next to $0"; exit 1; }

step() { echo; echo "=== $* ==="; }

step "1/5 packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git cmake build-essential pkg-config libusb-1.0-0-dev python3 usbutils wireless-tools iproute2

step "2/5 rtl-sdr-blog driver ($RTLSDR_REF)"
if [ -d "$SRC_DIR/.git" ]; then
    git -C "$SRC_DIR" fetch --depth 1 origin "$RTLSDR_REF"
    git -C "$SRC_DIR" checkout -f FETCH_HEAD
else
    rm -rf "$SRC_DIR"
    git clone --depth 1 --branch "$RTLSDR_REF" "$RTLSDR_REPO" "$SRC_DIR"
fi
rm -rf "$SRC_DIR/build"
mkdir -p "$SRC_DIR/build"
cd "$SRC_DIR/build"
# own prefix + RPATH: our rtl_tcp always loads our librtlsdr, nothing in /usr or /usr/local changes
cmake .. -DINSTALL_UDEV_RULES=ON -DDETACH_KERNEL_DRIVER=ON -DCMAKE_BUILD_TYPE=Release     -DCMAKE_INSTALL_PREFIX="$PREFIX" -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_INSTALL_RPATH="$PREFIX/lib"
make -j"$(nproc)"
make install
# tools in PATH (rtl_test, rtl_eeprom ...): links, so an own build in /usr/local/bin is never overwritten
for f in "$PREFIX"/bin/rtl_*; do
    t="/usr/local/bin/$(basename "$f")"
    if [ ! -e "$t" ] || [ -L "$t" ]; then ln -sf "$f" "$t"; else echo "kept $t (not ours)"; fi
done
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb || true
cd /

step "3/5 DVB-T kernel driver off"
cat > /etc/modprobe.d/blacklist-rtlsdr.conf <<'EOF'
# RTL-SDR dongles are used by rtl_tcp, not as DVB-T TV receivers
blacklist dvb_usb_rtl28xxu
blacklist rtl2832
blacklist rtl2832_sdr
blacklist rtl2830
blacklist r820t
EOF
for m in rtl2832_sdr dvb_usb_rtl28xxu rtl2832 rtl2830 r820t; do rmmod "$m" 2>/dev/null || true; done

step "4/5 rtltcp-manager"
id rtltcp >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin rtltcp
getent group plugdev >/dev/null || groupadd --system plugdev
usermod -aG plugdev rtltcp
getent group video >/dev/null && usermod -aG video rtltcp     # vcgencmd (power / throttling state)
# the program lives in /opt/rtltcp, owned by the service user: RADIMCOM can update it (SETTINGS > RTL_TCP SERVER)
mkdir -p /opt/rtltcp
install -m 755 -o rtltcp -g rtltcp "$HERE/rtltcp_manager.py" /opt/rtltcp/rtltcp_manager.py
chown rtltcp:rtltcp /opt/rtltcp
ln -sf /opt/rtltcp/rtltcp_manager.py /usr/local/bin/rtltcp-manager
mkdir -p /etc/rtltcp
if [ ! -f /etc/rtltcp/rtltcp.conf ]; then
    cat > /etc/rtltcp/rtltcp.conf <<'EOF'
# rtltcp-manager settings (sudo systemctl restart rtltcp-manager after a change)
BIND=0.0.0.0            # address rtl_tcp and the dongle list listen on
FIRST_PORT=1234         # port of the first dongle, the next ones get the next free port
HTTP_PORT=1233          # http://<pi>:1233/dongles.json
BUFFERS=500             # rtl_tcp -n: max. buffered blocks when the network is slow
SCAN_S=3                # how often to look for plugged / unplugged dongles
STALL_S=10              # a client that stops answering this long: its rtl_tcp restarts (0 = off)
EXTRA_ARGS=             # more rtl_tcp arguments for all dongles
IGNORE=                 # serials left to other programs (e.g. rtl_433, wmbusmeters), separated by spaces
POWER=1                 # RADIMCOM may reboot / shut down this computer (from the local network only); 0 = no
UPDATE=1                # RADIMCOM may install a newer rtltcp-manager (from the local network only); 0 = no
EOF
fi
grep -q '^UPDATE=' /etc/rtltcp/rtltcp.conf || echo 'UPDATE=1                # RADIMCOM may install a newer rtltcp-manager (LAN only); 0 = no' >> /etc/rtltcp/rtltcp.conf
grep -q '^POWER=' /etc/rtltcp/rtltcp.conf || echo 'POWER=1                 # RADIMCOM may reboot / shut down this computer (LAN only); 0 = no' >> /etc/rtltcp/rtltcp.conf
# reboot / poweroff from RADIMCOM (SETTINGS > RTL_TCP): the service user may run exactly these two commands
cat > /etc/sudoers.d/rtltcp <<'EOF'
rtltcp ALL=(root) NOPASSWD: /usr/bin/systemctl reboot, /usr/bin/systemctl poweroff
EOF
chmod 440 /etc/sudoers.d/rtltcp
visudo -cf /etc/sudoers.d/rtltcp >/dev/null || { echo "sudoers rule invalid, removed"; rm -f /etc/sudoers.d/rtltcp; }
touch /etc/rtltcp/ports.conf
chown -R rtltcp:rtltcp /etc/rtltcp

cat > /etc/systemd/system/rtltcp-manager.service <<'EOF'
[Unit]
Description=rtl_tcp for every RTL-SDR dongle (RADIMCOM remote dongles)
After=network-online.target
Wants=network-online.target

[Service]
User=rtltcp
Group=plugdev
ExecStart=/usr/bin/python3 /opt/rtltcp/rtltcp_manager.py
Restart=always
RestartSec=3
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable rtltcp-manager
systemctl restart rtltcp-manager

step "5/5 check"
sleep 6
# LAN addresses only (no docker bridges, no link-local)
IP="$(hostname -I | tr ' ' '\n' | grep -vE '^(172\.1[7-9]\.|169\.254\.|$)' | head -1)"
echo "Dongles on USB:"
lsusb | grep -iE 'rtl|0bda:283|realtek' || echo "  (none connected now; they start by themselves when plugged in)"
echo
echo "Served dongles (http://$IP:1233/dongles.json):"
python3 - "$IP" <<'EOF' || true
import json, sys, urllib.request
d = json.load(urllib.request.urlopen(f"http://127.0.0.1:1233/dongles.json", timeout=3))
for x in d["dongles"]:
    state = "running" if x.get("running") else x.get("error", "starting")
    print(f"  {x['serial'] or '?':16} {x.get('product',''):24} rtl_tcp {sys.argv[1]}:{x.get('port','-')}  {state}")
if not d["dongles"]:
    print("  none")
EOF
echo
echo "Done. Log: journalctl -u rtltcp-manager -f   Ports: /etc/rtltcp/ports.conf"
echo "Tools: $PREFIX/bin (rtl_test, rtl_eeprom ...); stop the service before using them on a served dongle"
if [ -s /sys/firmware/devicetree/base/model ] && grep -q "Raspberry" /sys/firmware/devicetree/base/model 2>/dev/null; then
    echo "Tip: several dongles need a good 5 V supply (or a powered USB hub); check: vcgencmd get_throttled"
fi
