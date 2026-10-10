#!/usr/bin/env bash
# Uploads the recorder's finished hours to the day's release (see recorder.yml).
#   loop          upload finished hours every 60 s
#   once          upload every finished hour now
#   file F DAY    upload one file to day DAY's release
# An hour is finished once its .jsonl.gz exists and its .jsonl is gone (RawWriter gzips, then removes).
set -u
OUT=${OUT:-rec}
RUN=${RUN:?}
mkdir -p "$OUT"
done_list="$OUT/.uploaded"
touch "$done_list"

ensure_release() {
  local tag="raw-gha-$1"
  gh release view "$tag" >/dev/null 2>&1 && return 0
  gh release create "$tag" --title "Raw recordings $1 (UTC)" --latest=false \
    --notes "Hourly raw files from the recorder Action (.github/workflows/recorder.yml). Fetch with handoff/experiments/fetch_gha_raw.py." \
    >/dev/null 2>&1 || gh release view "$tag" >/dev/null 2>&1
}

upload() {  # path day asset-name
  local path=$1 day=$2 name=$3 i
  ensure_release "$day" || return 1
  local tmp
  tmp=$(mktemp -d)
  cp "$path" "$tmp/$name"
  for i in 1 2 3 4; do
    if gh release upload "raw-gha-$day" "$tmp/$name" --clobber >/dev/null; then
      rm -rf "$tmp"
      echo "uploaded $name"
      return 0
    fi
    sleep $((2 ** i))
  done
  rm -rf "$tmp"
  echo "upload failed: $name" >&2
  return 1
}

sweep() {
  local f base hour
  for f in "$OUT"/*.jsonl.gz; do
    [ -e "$f" ] || continue
    base=$(basename "$f" .jsonl.gz)          # YYYYmmdd-HH
    [ -e "$OUT/$base.jsonl" ] && continue    # still being written or compressed
    grep -qx "$base" "$done_list" && continue
    upload "$f" "${base%%-*}" "$base.run$RUN.jsonl.gz" && echo "$base" >>"$done_list"
  done
}

case "${1:-once}" in
  loop) while true; do sweep; sleep 60; done ;;
  once) sweep ;;
  file) upload "$2" "$3" "$(basename "$2" | sed "s/^recorder-run$RUN/recorder.run$RUN/")" ;;
  *) echo "usage: $0 loop|once|file F DAY" >&2; exit 2 ;;
esac
