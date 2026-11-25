# Validation and scope

This is a community-maintained guide, not an official InfluxData release.
It contains original documentation/helpers and portable configuration examples,
not EDR binaries, private source, delivered Helm charts, or license material.

The underlying deployment pattern has been exercised with real writes, exact
source/destination comparisons, and agent restarts. The generalized examples
were checked for YAML/shell correctness and rendered against locally available
charts. They have not been freshly installed end-to-end on every platform,
storage provider, or EDR release. In particular, chart rendering is not a claim
that every delivered GA/RC chart has identical behavior.

The test suite labels its kubectl/Helm command doubles explicitly. It checks
helper ordering, error handling, Secret preservation, and example consistency
without contacting Kubernetes. A passing double is not runtime integration proof.

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

The optional server values target the public Enterprise chart 0.18.0 and server
3.12.2. Select a supported EDR/server pairing from the official compatibility
matrix rather than assuming those are the latest or universally appropriate.
Use actual server `--version` output, not only Helm's appVersion.

The smoke test creates a small test database and leaves its points in place.
Run it only against endpoints you are authorized to modify. It is not a load,
backup/restore, retention, complete-history, or long-outage recovery test.
