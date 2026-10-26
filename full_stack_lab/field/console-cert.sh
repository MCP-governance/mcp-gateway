#!/bin/sh
set -eu
umask 027
rm -f /tmp/ready
while :; do
  next="$(mktemp -d /out/cert.XXXXXX)"
  # The host daemon performs ACME; this container has no network or daemon identity.
  if ! tailscale --socket=/var/run/tailscale/tailscaled.sock cert \
    --cert-file "$next/cert.pem" --key-file "$next/key.pem" "$FIELD_CONSOLE_NAME"; then
    rm -rf "$next"
    exit 1
  fi
  test -s "$next/cert.pem" && test -s "$next/key.pem"
  chmod 750 "$next"
  chmod 640 "$next/cert.pem" "$next/key.pem"
  previous="$(readlink /out/current || true)"
  if [ -n "$previous" ] && cmp -s "$next/cert.pem" /out/current/cert.pem && cmp -s "$next/key.pem" /out/current/key.pem; then
    rm -rf "$next"
  else
    ln -sfn "${next##*/}" /out/current.new
    mv -Tf /out/current.new /out/current
    # Keep the previous pair until the next daily run, including across process restarts.
    for old in /out/cert.*; do
      [ "$old" = "$next" ] || [ "${old##*/}" = "$previous" ] || rm -rf "$old"
    done
  fi
  touch /tmp/ready
  sleep 86400
done
