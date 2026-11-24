#!/bin/bash
# Builds jt9.exe for RADIMCOM (lib\jt9) in MSYS2, "UCRT64" environment: a static exe, no DLLs needed.
# Run from the MSYS2 UCRT64 shell:   bash /c/RADIMCOM/installer/build_jt9.sh
# jt9 is the decoder of WSJT-X for the slow modes (JT65, Q65, JT9, JT4, FST4 ...); RADIMCOM uses it for JT65 and Q65.
# It is built without CMake and without Qt: the Fortran library of WSJT-X (wsjt_fort), its C/C++ helpers (wsjt_cxx)
# and jt9.f90 / jt9a.f90; the Qt shared memory (lib/shmem.cpp, used only by "jt9 -s" under WSJT-X) is replaced by a
# stub that always fails, since RADIMCOM runs jt9 on WAV files.
set -e
[ "$MSYSTEM" = "UCRT64" ] || { echo "run this in the MSYS2 UCRT64 shell (MSYSTEM=UCRT64, now: $MSYSTEM)"; exit 1; }
SRC=${SRC:-/c/Users/${USER:-$USERNAME}/src}
DEST=${DEST:-/c/RADIMCOM/lib/jt9}
TAG=wsjtx-2.7.0
mkdir -p "$SRC"; cd "$SRC"

pacman -S --needed --noconfirm git mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-gcc-fortran mingw-w64-ucrt-x86_64-fftw \
    mingw-w64-ucrt-x86_64-boost

if [ ! -d $TAG ]; then
  git clone -q --depth 1 --sparse -b $TAG https://git.code.sf.net/p/wsjt/wsjtx $TAG
fi
git -C $TAG sparse-checkout add lib

cd $TAG
# the file lists of CMakeLists.txt: "set (NAME" ... ")"
srcs() { awk -v n="$1" '$0 ~ "^ *set \\(" n "$" {f=1; next} f && /^ *\)/ {f=0} f' CMakeLists.txt \
         | sed 's/#.*//' | tr -d ' \r' | grep -v '^\$' | grep -v '^$' || true; }
FSRCS="$(srcs wsjt_FSRCS) lib/jt9.f90 lib/jt9a.f90"
CSRCS="$(srcs ka9q_CSRCS) $(srcs qra_CSRCS) $(srcs ldpc_CSRCS) $(srcs wsjt_CSRCS)"
CXXSRCS="lib/crc10.cpp lib/crc13.cpp lib/crc14.cpp"

B=$SRC/$TAG/build_jt9
rm -rf "$B" && mkdir -p "$B" && cd "$B"
cat > shmem_stub.c <<'EOF'
/* RADIMCOM: jt9 runs on WAV files only, the shared memory of WSJT-X (lib/shmem.cpp, Qt) is not used */
#include <stdbool.h>
#include <stddef.h>
bool shmem_create(int n) { (void)n; return false; }
void shmem_setkey(char *const k) { (void)k; }
bool shmem_attach(void) { return false; }
int shmem_size(void) { return 0; }
void *shmem_address(void) { return NULL; }
bool shmem_lock(void) { return false; }
bool shmem_unlock(void) { return false; }
bool shmem_detach(void) { return false; }
EOF

echo "== C / C++"
for f in $CSRCS; do gcc -O2 -w -DBIGSYM=1 -DWIN32 -I../lib -I../lib/ftrsd -I../lib/qra/q65 -c ../$f -o "$(echo $f | tr / _).o"; done
for f in $CXXSRCS; do g++ -O2 -w -DWIN32 -c ../$f -o "$(echo $f | tr / _).o"; done
gcc -O2 -c shmem_stub.c -o shmem_stub.o

echo "== Fortran ($(echo $FSRCS | wc -w) files; repeated passes until the modules are in order)"
FF="-O2 -funroll-all-loops -fno-f2c -fno-second-underscore -fallow-argument-mismatch -w -I../lib -I../lib/ft8 -I../lib/ft4 \
    -I../lib/fst4 -I../lib/77bit -I../lib/ft2 -I../lib/qra/q65 -I../lib/superfox"
todo="$FSRCS"
for pass in 1 2 3 4 5 6 7 8 9 10; do
  left=""
  for f in $todo; do
    o="$(echo $f | tr / _).o"
    # jplsubs.f has its own SUBROUTINE SPLIT, which gfortran >= 15 takes for the Fortran 2023 intrinsic SPLIT
    std=""; [ "$f" = lib/jplsubs.f ] && std="-std=f2018"
    gfortran $FF $std -c ../$f -o $o 2>/dev/null || left="$left $f"
  done
  echo "   pass $pass: $(echo $left | wc -w) left"
  [ -z "$left" ] && break
  [ "$left" = "$todo" ] && { for f in $left; do gfortran $FF -c ../$f -o x.o; done; exit 1; }
  todo="$left"
done

echo "== link"
# like CMake: the library sources go into a static library (it also holds test programs and alternative versions of
# some routines, the linker takes only what jt9 needs)
rm -f libwsjt.a x.o
ar rcs libwsjt.a $(ls *.o | grep -v -e '^lib_jt9\.f90\.o$' -e '^lib_jt9a\.f90\.o$' -e '^shmem_stub\.o$')
gfortran -o jt9.exe lib_jt9.f90.o lib_jt9a.f90.o shmem_stub.o libwsjt.a -static -lfftw3f_threads -lfftw3f -lstdc++ \
    -lgfortran -lquadmath -lm -lpthread

echo "== copy to $DEST"
mkdir -p "$DEST"
cp jt9.exe "$DEST/"
ls -l "$DEST"
"$DEST/jt9.exe" -h 2>&1 | head -3 || true
