#!/bin/sh
# Installs the optional OpenResume layer of the ATS check: OpenResume's PDF parser at a pinned commit, plus pdfjs-dist and tsx.
# Needs node (>= 20), npm and git. Run: sh tools/openresume/install.sh [DIR]
# DIR defaults to $ATS_CHECK_OPENRESUME, else ~/.cache/ats-check/openresume (the folder the check looks in).
# Nothing from OpenResume (AGPL-3.0) is stored in this repository: it is fetched here, on the user's machine.
set -eu
SHA=4f8255a2c763479837f69f1dccf2a3338730cd79
REPO=https://github.com/xitanggg/open-resume.git
SRC=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DIR=${1:-${ATS_CHECK_OPENRESUME:-$HOME/.cache/ats-check/openresume}}

for t in node npm git; do command -v "$t" >/dev/null 2>&1 || { echo "openresume install: '$t' not found on PATH" >&2; exit 1; }; done
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ] || { echo "openresume install: node >= 20 required" >&2; exit 1; }
: "${DIR:?}"
mkdir -p "$DIR"
cp "$SRC/package.json" "$SRC/package-lock.json" "$SRC/run.ts" "$DIR/"
(cd "$DIR" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error)

if [ "$(git -C "$DIR/open-resume" rev-parse HEAD 2>/dev/null || true)" != "$SHA" ] || [ ! -f "$DIR/open-resume/package.json" ]; then
  rm -rf "$DIR/open-resume"
  git init -q "$DIR/open-resume"
  # only what the parser needs: its lib folder, tsconfig.json (path aliases), package.json (makes node treat its files as CommonJS, as in its own repo) and the licence
  git -C "$DIR/open-resume" config core.sparseCheckout true
  printf '%s\n' /src/app/lib/ /tsconfig.json /package.json /LICENSE > "$DIR/open-resume/.git/info/sparse-checkout"
  git -C "$DIR/open-resume" fetch -q --depth 1 --filter=blob:none "$REPO" "$SHA"
  git -C "$DIR/open-resume" checkout -q FETCH_HEAD
  [ "$(git -C "$DIR/open-resume" rev-parse HEAD)" = "$SHA" ] || { echo "openresume install: fetched commit is not $SHA" >&2; exit 1; }
fi
printf '%s\n' "$SHA" > "$DIR/INSTALLED"
echo "OpenResume $SHA installed in $DIR"
