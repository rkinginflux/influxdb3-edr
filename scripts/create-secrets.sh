#!/usr/bin/env bash
# Creates missing Secrets only; rotation is an intentional, separate operation.
set -euo pipefail
cd "$(dirname "$0")/.."
NS="${NAMESPACE:-influxdb3-edr}"
CREDENTIALS_DIR="${CREDENTIALS_DIR:-credentials}"
command -v kubectl >/dev/null
command -v openssl >/dev/null
kubectl config current-context

# Check every input before making changes. Do not put secret values in arguments.
for file in source-access-key-id source-secret-access-key receiver-access-key-id receiver-secret-access-key destination-write-token; do
  if [[ ! -s "$CREDENTIALS_DIR/$file" ]]; then
    printf 'Missing or empty file: %s/%s\nSee docs/credentials.md.\n' "$CREDENTIALS_DIR" "$file" >&2
    exit 1
  fi
done
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

create_if_missing() {
  local name="$1"
  local existing
  shift
  existing="$(kubectl -n "$NS" get secret "$name" --ignore-not-found -o name)"
  if [[ -n "$existing" ]]; then
    printf 'Preserving existing Secret: %s\n' "$name"
    return
  fi
  kubectl -n "$NS" create secret generic "$name" "$@" >/dev/null
  kubectl -n "$NS" get secret "$name" -o name
}
create_if_missing edr-source-storage \
  --from-file="access-key-id=$CREDENTIALS_DIR/source-access-key-id" \
  --from-file="secret-access-key=$CREDENTIALS_DIR/source-secret-access-key"
create_if_missing edr-receiver-storage \
  --from-file="access-key-id=$CREDENTIALS_DIR/receiver-access-key-id" \
  --from-file="secret-access-key=$CREDENTIALS_DIR/receiver-secret-access-key"
create_if_missing edr-destination-write \
  --from-file="destination-write=$CREDENTIALS_DIR/destination-write-token"

existing_link="$(kubectl -n "$NS" get secret edr-link --ignore-not-found -o name)"
if [[ -n "$existing_link" ]]; then
  printf 'Preserving existing Secret: edr-link\n'
else
  if [[ ! -s "$CREDENTIALS_DIR/link-auth" ]]; then
    command -v openssl >/dev/null
    (umask 077; openssl rand -hex 32 > "$CREDENTIALS_DIR/link-auth"; chmod 600 "$CREDENTIALS_DIR/link-auth")
  fi
  create_if_missing edr-link --from-file="link-auth=$CREDENTIALS_DIR/link-auth"
fi
printf 'Credential Secrets are ready in namespace %s. Values were not printed.\n' "$NS"
