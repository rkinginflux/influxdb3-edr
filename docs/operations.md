# Operations

## Verify data arrival

A Ready Pod is not enough. This test writes one uniquely identified point to the
source and compares its tags, field value, and timestamp through both query APIs.
It creates/reuses `edr_smoke` on both databases and leaves its test data in place.

Save source and destination **admin tokens** in local files named
`credentials/source-admin-token` and `credentials/destination-admin-token`.
These test credentials need database creation and query permissions as well as
source write permission; the receiver's write-only token may not be sufficient.
Raw tokens and offline admin-token JSON are accepted. Then edit the four endpoint
URLs below and run:

```bash
chmod 600 credentials/*
python3 scripts/smoke-test.py \
  --source-write-url https://source-write.example.com \
  --source-query-url https://source-query.example.com \
  --destination-write-url https://destination-write.example.com \
  --destination-query-url https://destination-query.example.com \
  --source-token-file credentials/source-admin-token \
  --destination-token-file credentials/destination-admin-token
```

Use base URLs only, not `/api/v3/...` paths. If one server endpoint handles both
writes and queries, use that same URL for both corresponding options. For local
HTTP port-forwards, use `http://localhost:PORT` instead. Python 3 is the only
additional runtime requirement. Tokens are read from files and are not printed;
authenticated requests do not follow redirects. Expected output starts with
`PASS: unique test point matches source and destination`. It waits up to two
minutes and exits nonzero if equality is not established.

If it does not arrive, inspect sender/receiver logs and the sender UI. Check
storage compatibility, source bucket permissions, receiver reachability, the
shared link token, and the destination write token. A query-only destination
node cannot accept writes. Ensure the test point was written after the live-only
sender started. Compare actual server versions, not just Helm chart appVersion.

## Compatibility and topology

The quick start installs both agents in **one namespace on the current Kubernetes
context**. The sender reaches the receiver at the namespace-local Service
`http://edrr-edr:9090`. Database endpoints and storage must be reachable from
those Pods; a workstation-only localhost URL will not work inside a Pod.

For these ordered-send defaults (`idempotentWrites: false`, one send at a time),
use a **single-ingester source**. The documented strict-order mode refuses a
multi-ingester source. Do not simply enable idempotent writes to suppress that
check: first review the workload's overwrite semantics and the
[official multi-ingester requirements](https://docs.influxdata.com/influxdb3/enterprise/edr/reference/config-file/#multi-ingest-node-support).

For separate-cluster agents, deploy each role in its own context, provision its
Secrets there, and replace the local receiver URL with a privately reachable,
authenticated/TLS-protected endpoint. That is outside this one-context helper.
EDR also supports Google Cloud Storage and Azure, but these helpers target S3.
Check the [compatibility matrix](https://docs.influxdata.com/influxdb3/enterprise/edr/reference/compatibility/)
against your actual server and delivered EDR versions. InfluxDB 3 Core is not a
supported substitute.

## Upgrades and restarts

Keep your original state bucket and prefixes. Use your delivered chart's matching
release notes; upgrade the reader (EDR) before a source upgrade that changes
storage formats. Do not use a new state prefix as a way to clear an error.

```bash
helm upgrade edrr "$EDR_CHART" -n "$NAMESPACE" -f receiver-values.yaml --wait --timeout=5m
helm upgrade edrs "$EDR_CHART" -n "$NAMESPACE" -f sender-values.yaml --wait --timeout=5m
```

Run one replica per agent. Do not delete the state bucket, reset cursors, or scale
out an agent as a routine restart. EDR state needs no PVC; the source and destination
still require durable database storage. Replication is not a full backup.

Review source WAL retention against the longest expected interruption. For
supported upgraded-engine servers, the setting is `--wal-snapshots-to-keep`
(or `INFLUXDB3_WAL_SNAPSHOTS_TO_KEEP`); choose a measured value rather than assuming
a fixed number of snapshots guarantees a fixed outage duration. Use the matching
Enterprise chart/version's configuration interface and normal change controls.

## Private registry access

Make the delivered image available to **every eligible worker**. A local Docker
image is not automatically in Kubernetes workers' container runtime.

The delivered EDR chart may not offer an `imagePullSecrets` value. To avoid relying
on an unsupported setting, configure registry access using your cluster's normal
mechanism. In a dedicated EDR namespace, one option is an existing registry Secret
referenced by its default ServiceAccount:

```bash
kubectl -n "$NAMESPACE" patch serviceaccount default --type=merge \
  -p '{"imagePullSecrets":[{"name":"edr-registry"}]}'
```

Create `edr-registry` securely first, using your registry administrator's guidance.
This example replaces the default ServiceAccount's imagePullSecrets list: preserve
any existing entries when adapting it. It affects newly created Pods using that
ServiceAccount. Do not paste registry passwords into the public values files or
publish the proprietary EDR image to a public registry.

## Permanent UI access

The optional [UI Services](../manifests/ui-services.yaml) retain these mappings:

| Service | Published port | Agent port |
| --- | --- | --- |
| `edrs-edr-ui` | 9091 | 9091 |
| `edrr-edr-ui` | 9092 | 9091 |

They are deliberately separate from the chart's internal replication Services.
Confirm their selectors match the actual Pods generated by your delivered chart.
Edit `metadata.namespace` in both documents if not using `influxdb3-edr`.

**Do not apply them until private exposure is configured.** The manifest uses
`type: LoadBalancer`; it requires a working load-balancer implementation and may
otherwise stay Pending. Configure your provider's internal-only annotations and
network restrictions, or use a private authenticated ingress instead. The agents'
UIs and observability APIs are unauthenticated HTTP; these Services add neither
TLS nor access control. They are not safe public-internet endpoints.

Once reviewed for your environment:

```bash
kubectl -n "$NAMESPACE" apply --dry-run=server -f manifests/ui-services.yaml
kubectl -n "$NAMESPACE" apply -f manifests/ui-services.yaml
kubectl -n "$NAMESPACE" get svc edrs-edr-ui edrr-edr-ui
```

Open `http://<sender-service-address>:9091/ui` and
`http://<receiver-service-address>:9092/ui`. The addresses may differ. Verify actual
HTTP access from your intended client, not only the EXTERNAL-IP column.

## Need the database servers too?

The main quick start assumes both licensed Enterprise instances already exist.
[examples/enterprise-values.yaml](../examples/enterprise-values.yaml) is an
optional starting point for the public `influxdata/influxdb3-enterprise` chart
0.18.0, pinned to the 3.12.2 server line—not a claim that these are the latest
versions. Follow the [official installation guide](https://docs.influxdata.com/influxdb3/enterprise/install/).

Create one values file per independent instance and set a distinct cluster ID,
data bucket, and admin-token Secret. Supply a license valid for the installation;
these examples do not issue, copy, or grant license entitlement.

Required Secret keys for that Enterprise chart:

- License Secret: `license-file`.
- Storage Secret: `access-key-id`, `secret-access-key`.
- Offline admin-token Secret: `admin-token.json`, generated with the matching
  Enterprise CLI's `create token --admin --offline --output-file` command.

This optional file runs one ingester (receives writes), one querier (answers
queries), and one compactor (organizes stored data). Adjust resources and
placement for your workload. Use an S3 endpoint trusted by your nodes; set the
chart's custom-endpoint/TLS options as needed. No particular storage vendor,
node naming, or network topology is required by this repository.
