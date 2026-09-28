#!/bin/sh
set -eu
test "$(cat /etc/alpine-release)" = 3.24.1
test "$(apk --print-arch)" = x86_64
count=0
while IFS= read -r repo || [ -n "$repo" ]; do
    case "$repo" in
        ''|'#'*) continue ;;
        https://dl-cdn.alpinelinux.org/alpine/v3.24/main|https://dl-cdn.alpinelinux.org/alpine/v3.24/community) ;;
        *) printf '%s\n' 'unexpected repository; refusing substitution' >&2; exit 1 ;;
    esac
    count=$((count + 1))
done < /etc/apk/repositories
test "$count" -gt 0
for root in /opt/runtime /opt/inspect; do
    mkdir -p "$root/etc/apk/keys"
    cp /etc/apk/repositories "$root/etc/apk/repositories"
    cp /etc/apk/keys/*.pub "$root/etc/apk/keys/"
done
# Fresh binary/library extraction, not a bootable root. Never run hooks outside
# their root; never rewrite absolute symlinks, interpreters, or resource paths.
apk --root /opt/runtime --initdb --no-cache --no-scripts add 'nodejs>=22.13' gcompat libgcc libstdc++
apk --root /opt/inspect --initdb --no-cache --no-scripts add binutils
test -f /opt/runtime/lib/libgcompat.so.0
test -x /opt/runtime/usr/bin/node
test -x /opt/inspect/usr/bin/readelf
