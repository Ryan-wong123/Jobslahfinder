#!/usr/bin/env sh
# Download the MaxMind GeoLite2-City database (license forbids committing/redistributing it).
# Requires a free MaxMind licence key: https://www.maxmind.com/en/geolite2/signup
# The database is optional: without it the risk engine skips impossible-travel scoring.
set -eu
: "${MAXMIND_LICENSE_KEY:?Set MAXMIND_LICENSE_KEY in your shell (do not commit it)}"
DEST="${GEOIP_DIR:-infra/geoip}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST"
curl -fsSL "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz" -o "$TMP/geo.tar.gz"
tar -xzf "$TMP/geo.tar.gz" -C "$TMP"
find "$TMP" -name 'GeoLite2-City.mmdb' -exec cp {} "$DEST/GeoLite2-City.mmdb" \;
chmod 644 "$DEST/GeoLite2-City.mmdb"
echo "Installed $DEST/GeoLite2-City.mmdb"
