#!/bin/sh
# Installs the optional OpenResume layer of the ATS check: OpenResume's PDF parser at a pinned commit, plus pdfjs-dist, tsx and
# @reduxjs/toolkit from a lockfile. Needs node (>= 20), npm and git. Run: sh tools/openresume/install.sh [DIR]
# DIR defaults to $ATS_CHECK_OPENRESUME, else $ATS_CHECK_CACHE/openresume, else ~/.cache/ats-check/openresume (the folder the check looks in).
# `--print-dir` prints the absolute folder and exits. The folder holds code that is run, so it is created private (0700).
# Nothing from OpenResume (AGPL-3.0) is stored in this repository: it is fetched here, on the user's machine.
set -eu
umask 077
SHA=4f8255a2c763479837f69f1dccf2a3338730cd79      # keep equal to PINNED_SHA in ats_check/openresume.py (a test compares them)
REPO=https://github.com/xitanggg/open-resume.git
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

PRINT=0
if [ "${1:-}" = "--print-dir" ]; then PRINT=1; shift; fi
DIR=${1:-${ATS_CHECK_OPENRESUME:-${ATS_CHECK_CACHE:-$HOME/.cache/ats-check}/openresume}}
case $DIR in
  off|OFF|Off|0|false|no) echo "openresume install: '$DIR' means the layer is switched off, not a folder" >&2; exit 2 ;;
  "~") DIR=$HOME ;;
  "~/"*) DIR=$HOME/${DIR#"~/"} ;;
esac
case $DIR in /*) ;; *) DIR=$PWD/$DIR ;; esac
if [ "$PRINT" = 1 ]; then printf '%s\n' "$DIR"; exit 0; fi

for t in node npm git; do command -v "$t" >/dev/null 2>&1 || { echo "openresume install: '$t' not found on PATH" >&2; exit 1; }; done
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || { echo "openresume install: node >= 20 required" >&2; exit 1; }
: "${DIR:?}"
mkdir -p "$DIR"
chmod 700 "$DIR"
cp "$SRC/package.json" "$SRC/package-lock.json" "$SRC/run.ts" "$DIR/"
(cd "$DIR" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error)

# reuse the checkout only if it is the pinned commit, has its files and no local change (the runner executes it)
clean() {
  [ "$(git -C "$DIR/open-resume" rev-parse HEAD 2>/dev/null || true)" = "$SHA" ] && [ -f "$DIR/open-resume/package.json" ] &&
    [ -z "$(git -C "$DIR/open-resume" status --porcelain --untracked-files=all 2>/dev/null || echo dirty)" ]
}
if ! clean; then
  rm -rf "$DIR/open-resume"
  git init -q "$DIR/open-resume"
  # only what the parser needs: its lib folder, tsconfig.json (path aliases), package.json (makes node treat its files as CommonJS, as in its own repo) and the licence
  git -C "$DIR/open-resume" config core.sparseCheckout true
  printf '%s\n' /src/app/lib/ /tsconfig.json /package.json /LICENSE > "$DIR/open-resume/.git/info/sparse-checkout"
  git -C "$DIR/open-resume" fetch -q --depth 1 --filter=blob:none "$REPO" "$SHA"
  git -C "$DIR/open-resume" checkout -q FETCH_HEAD
  clean || { echo "openresume install: the checkout is not clean at $SHA" >&2; exit 1; }
fi
echo "OpenResume $SHA installed in $DIR"
