#!/bin/bash
# Builds the radiosonde decoders of rs1729 (https://github.com/rs1729/RS, GPL-3.0) for RADIMCOM (lib\sonde).
# Needs MSYS2 with the UCRT64 gcc (pacman -S mingw-w64-ucrt-x86_64-gcc). Run from any shell:
#   bash /c/RADIMCOM/installer/build_sonde.sh
# The programs are linked statically (no DLLs). A small extra object (winpipe.c below) sets stdin to binary mode
# (the raw I/Q come through a pipe; in text mode Windows would cut them at the first 0x1A) and stdout unbuffered
# (each JSON line is read at once). The sources are not changed.
set -e
SRC=${SRC:-$HOME/src}
DEST=${DEST:-/c/RADIMCOM/lib/sonde}
REV=${REV:-}                                 # a commit of rs1729/RS, empty = the newest
export PATH=/c/msys64/ucrt64/bin:$PATH
command -v gcc >/dev/null || { echo "no gcc: install MSYS2 and mingw-w64-ucrt-x86_64-gcc"; exit 1; }
mkdir -p "$SRC" "$DEST"
cd "$SRC"
[ -d RS ] || git clone -q https://github.com/rs1729/RS.git
[ -z "$REV" ] || git -C RS checkout -q "$REV"
echo "rs1729/RS $(git -C RS log -1 --format='%h %cd' --date=short)"
M=$SRC/RS/demod/mod
B=$SRC/rs_build
mkdir -p "$B" && cd "$B"
cat > winpipe.c <<'EOF'
/* RADIMCOM: binary stdin (raw IQ from a pipe) and unbuffered stdout (JSON lines at once) on Windows */
#include <stdio.h>
#include <io.h>
#include <fcntl.h>
__attribute__((constructor)) static void radimcom_winpipe(void) {
    _setmode(_fileno(stdin), _O_BINARY);
    setvbuf(stdout, NULL, _IONBF, 0);
}
EOF
gcc -O3 -c winpipe.c -o winpipe.o
gcc -Ofast -c "$M/demod_mod.c" -o demod_mod.o
gcc -O3 -c "$M/bch_ecc_mod.c" -o bch_ecc_mod.o
# the decoders RADIMCOM runs (sonde_ext.DECODERS); rs92mod is left out: it needs GPS ephemeris for a position
for p in rs41mod:bch lms6Xmod:bch meisei100mod:bch cf06ht03mod:bch dfm09mod: m10m20mod: imet54mod: mp3h1mod: mts01mod:; do
  n=${p%%:*}; extra="demod_mod.o winpipe.o"; [ "${p#*:}" = bch ] && extra="$extra bch_ecc_mod.o"
  gcc -O3 -I"$M" "$M/$n.c" $extra -lm -static -o "$n.exe"
  cp "$n.exe" "$DEST/"
  echo "  $n.exe"
done
git -C "$SRC/RS" log -1 --format='rs1729/RS %H %cd' > "$DEST/VERSION.txt"
echo "done: $DEST"
