# Credential checklist

Run these commands from the repository directory:

```bash
install -d -m 700 credentials
```

Create these five files using your editor or secret manager. Each file contains
only its credential, with no quotes, variable assignments, or surrounding spaces:

| File in `credentials/` | What goes inside |
| --- | --- |
| `source-access-key-id` | Sender's S3 access key ID |
| `source-secret-access-key` | Sender's S3 secret access key |
| `receiver-access-key-id` | Receiver's S3 access key ID |
| `receiver-secret-access-key` | Receiver's S3 secret access key |
| `destination-write-token` | Destination database write token |

The destination token file may instead contain the destination's admin-token JSON
if you are intentionally using an admin token. Prefer a scoped write token where
its permissions support the databases and schema operations your replication needs.
The token must belong to the **destination**, not the source.

```bash
chmod 600 credentials/*
export NAMESPACE=influxdb3-edr
./scripts/create-secrets.sh
```

The script generates `credentials/link-auth` only when needed. This is the shared
secret that lets the sender authenticate to the receiver; it is not a database
token. Do not replace it casually or regenerate it during a normal restart.

## Storage permissions

- **Sender:** read/list the source bucket and read/write/list its own state
  location. Do not grant deletion of source data for this default setup.
- **Receiver:** read/write/list its own state location; it does not need source
  bucket access. It writes database data through the destination's HTTP API.
- Create the state bucket before installation. Give each agent a distinct prefix,
  as shown in the examples. Never share those prefixes with another pipeline.
- Within each agent process, source and state share a provider/account/credential
  set. S3 source bucket prefixes are not supported.
- For the same storage account, the sender and receiver may use the same credential
  values, but permissions should still be limited to what each role needs.

The script preserves existing Secrets; editing a local credential file does not
rotate a Secret already in Kubernetes. Coordinate deliberate rotation with the
[official token guide](https://docs.influxdata.com/influxdb3/enterprise/edr/manage-tokens/).
Kubernetes Secret base64 encoding is not encryption: use your cluster's encryption
at rest and RBAC controls. Keep credentials, license files, image archives, and
private registry configuration out of Git.

The supplied helper covers long-lived S3 access keys. For temporary session
credentials, workload identity, Google Cloud Storage, or Azure, use the relevant
settings in your delivered chart and the
[official Kubernetes guide](https://docs.influxdata.com/influxdb3/enterprise/edr/install/kubernetes/).
