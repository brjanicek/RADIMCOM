#!/bin/bash
# Builds wsprd.exe for RADIMCOM (lib\wspr) in MSYS2, "UCRT64" environment: a static exe, no DLLs needed.
# Run from the MSYS2 UCRT64 shell:   bash /c/RADIMCOM/installer/build_wspr.sh
# wsprd is the WSPR decoder of WSJT-X (lib/wsprd, C + two Fortran files); only that folder is checked out.
set -e
[ "$MSYSTEM" = "UCRT64" ] || { echo "run this in the MSYS2 UCRT64 shell (MSYSTEM=UCRT64, now: $MSYSTEM)"; exit 1; }
SRC=${SRC:-/c/Users/$USER/src}
DEST=${DEST:-/c/RADIMCOM/lib/wspr}
TAG=wsjtx-2.7.0
mkdir -p "$SRC" && cd "$SRC"

pacman -S --needed --noconfirm git mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-gcc-fortran mingw-w64-ucrt-x86_64-fftw

if [ ! -d $TAG ]; then
  git clone -q --depth 1 --sparse -b $TAG https://git.code.sf.net/p/wsjt/wsjtx $TAG
  git -C $TAG sparse-checkout set lib/wsprd       # also brings the files of lib/ itself (indexx.f90)
fi

echo "== wsprd ($TAG)"
cd $TAG/lib/wsprd
rm -f *.o
CF="-Wall -Wno-missing-braces -Wno-unused-result -O3 -ffast-math"
for f in wsprd wsprsim_utils wsprd_utils tab fano jelinek nhash; do gcc $CF -c $f.c; done
gfortran -O2 -c ../indexx.f90 -o indexx.o
gfortran -O2 -c osdwspr.f90
gcc -o wsprd.exe wsprd.o wsprsim_utils.o wsprd_utils.o tab.o fano.o jelinek.o nhash.o indexx.o osdwspr.o \
    -static -lfftw3f -lgfortran -lquadmath -lm

echo "== copy to $DEST"
mkdir -p "$DEST"
cp wsprd.exe "$DEST/"
ls -l "$DEST"
"$DEST/wsprd.exe" 2>&1 | head -2 || true
