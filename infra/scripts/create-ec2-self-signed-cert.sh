#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  printf '%s\n' "Usage: $0 <ec2-public-ip>" >&2
  exit 1
fi

EC2_PUBLIC_IP="$1"
case "$EC2_PUBLIC_IP" in
  *[!0-9.]* | .* | *. | *..*)
    printf '%s\n' "EC2 public IP must be an IPv4 address such as 203.0.113.10." >&2
    exit 1
    ;;
esac

CERT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../nginx/certs" && pwd)"
KEY_PATH="$CERT_DIR/localhost.key"
CERT_PATH="$CERT_DIR/localhost.crt"
OPENSSL_CONFIG_PATH="$CERT_DIR/ec2-openssl.cnf"

mkdir -p "$CERT_DIR"
umask 077

cat > "$OPENSSL_CONFIG_PATH" <<EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
x509_extensions = v3_req
distinguished_name = dn

[dn]
CN = ${EC2_PUBLIC_IP}

[v3_req]
subjectAltName = @alt_names
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
IP.1 = ${EC2_PUBLIC_IP}
DNS.1 = localhost
IP.2 = 127.0.0.1
EOF

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$KEY_PATH" \
  -out "$CERT_PATH" \
  -config "$OPENSSL_CONFIG_PATH"

chmod 600 "$KEY_PATH" "$CERT_PATH" "$OPENSSL_CONFIG_PATH"
printf '%s\n' "Created self-signed certificate for ${EC2_PUBLIC_IP}:"
printf '%s\n' "  $CERT_PATH"
printf '%s\n' "  $KEY_PATH"
