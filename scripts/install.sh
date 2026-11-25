#!/usr/bin/env bash
# Use only the EDR Helm archive supplied to you by InfluxData.
set -euo pipefail
cd "$(dirname "$0")/.."
NS="${NAMESPACE:-influxdb3-edr}"
: "${EDR_CHART:?Set EDR_CHART to your delivered EDR Helm archive}"
[[ -f "$EDR_CHART" ]] || { printf 'Chart archive not found: %s\n' "$EDR_CHART" >&2; exit 1; }
command -v helm >/dev/null
command -v kubectl >/dev/null
kubectl config current-context
kubectl get namespace "$NS" -o name
for values in sender-values.yaml receiver-values.yaml; do
  [[ -s "$values" ]] || { printf 'Missing %s; copy it from examples/.\n' "$values" >&2; exit 1; }
  if grep -Eq '^[^#]*REPLACE_WITH_' "$values"; then
    printf 'Replace all placeholder values in %s before installing.\n' "$values" >&2
    exit 1
  fi
done
for secret in edr-source-storage edr-receiver-storage edr-destination-write edr-link; do
  kubectl -n "$NS" get secret "$secret" -o name
done
# Catch chart/value errors for BOTH roles before changing either release.
helm template edrr "$EDR_CHART" -n "$NS" -f receiver-values.yaml >/dev/null
helm template edrs "$EDR_CHART" -n "$NS" -f sender-values.yaml >/dev/null
helm upgrade --install edrr "$EDR_CHART" -n "$NS" -f receiver-values.yaml --wait --timeout=5m
helm upgrade --install edrs "$EDR_CHART" -n "$NS" -f sender-values.yaml --wait --timeout=5m
kubectl -n "$NS" get pods
