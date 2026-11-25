# InfluxDB 3 EDR on Kubernetes

**Edge Data Replication (EDR)** copies data between InfluxDB 3 Enterprise instances:

```text
Source database → Sender agent → Receiver agent → Destination database
```

This community guide installs both agents in one Kubernetes namespace on your
current context. It does not install or upgrade the database servers.

## Have these ready

- `kubectl`, Helm, Bash, Git, and OpenSSL; select the correct Kubernetes context.
- Two licensed **InfluxDB 3 Enterprise** instances. For these ordered-send defaults,
  the source needs **one ingester** and the upgraded storage engine (PachaTree).
  Check [version and multi-ingester requirements](docs/operations.md#compatibility-and-topology).
- An EDR image in a **private registry** and its matching Helm archive, supplied by
  [InfluxData](https://www.influxdata.com/contact-sales/). Neither is included here.
- The source's S3-compatible data bucket, a separate bucket for saved replication
  progress, and [storage/write credentials](docs/credentials.md).

## 1. Copy and edit the configuration

```bash
git clone https://github.com/rkinginflux/influxdb3-edr.git
cd influxdb3-edr
cp examples/sender-values.yaml sender-values.yaml
cp examples/receiver-values.yaml receiver-values.yaml
```

Replace every `REPLACE_WITH_...` value in both files: image, tag, buckets, region,
source release name, and destination write URL. Check [private registry access](docs/operations.md#private-registry-access).

## 2. Add credentials

Put the five files listed in [the credential checklist](docs/credentials.md) into
`credentials/`, then run:

```bash
export NAMESPACE=influxdb3-edr
./scripts/create-secrets.sh
```

The helper creates the namespace and missing Secrets. It preserves existing
credentials and generates the agents' shared link token only when needed.

## 3. Install

```bash
export EDR_CHART=/path/to/edr-helm-v1.0.0.tgz
./scripts/install.sh
```

This installs the receiver (`edrr`), then sender (`edrs`), with readiness waits.
**Only new data is copied by these defaults; historical backfill is not enabled.**

## 4. Check replication

```bash
kubectl -n "$NAMESPACE" get pods
kubectl -n "$NAMESPACE" logs deployment/edrs-edr --tail=30
kubectl -n "$NAMESPACE" logs deployment/edrr-edr --tail=30
```

Look for compatible source storage and no repeated errors. A Ready Pod is not proof
of delivery: run the [copy-paste data test](docs/operations.md#verify-data-arrival).
For the UIs, run each command in a separate terminal with `NAMESPACE` set:

```bash
kubectl -n "$NAMESPACE" port-forward svc/edrs-edr 9091:9091
```

```bash
kubectl -n "$NAMESPACE" port-forward svc/edrr-edr 9092:9091
```

Open http://localhost:9091/ui (sender) and http://localhost:9092/ui (receiver).
These UIs are unauthenticated: keep them local unless protected by authentication
and TLS. Optional [permanent UI Services](manifests/ui-services.yaml) need private-network configuration.

Keep **one replica per agent** and preserve state bucket/prefixes across restarts.
EDR is asynchronous replication, not a full backup or automatic failover.

More: [operations and server setup](docs/operations.md), [validation scope](docs/validation.md),
[official guide](https://docs.influxdata.com/influxdb3/enterprise/edr/install/kubernetes/).
Original docs/helpers are MIT-licensed; InfluxDB and EDR retain their own terms.
