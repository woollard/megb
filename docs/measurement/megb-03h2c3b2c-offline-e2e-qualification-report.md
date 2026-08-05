# MEGB-03H.2C.3B.2C Offline End-to-End Synthetic Distributed Qualification Report

- **Readiness:** `OFFLINE_DISTRIBUTED_PATH_READY_FOR_B3`
- **Scope:** offline, provider-neutral, in-process coordinator/worker path only -- no H.2C.3D, GCP, durable-process, cross-host, Docker/native-Linux-equivalence, calibration-provenance-completeness, or real-scientific-result-validity claim is made.
- **Schema version:** `megb-03h2c3b2c-offline-e2e-qualification-v1`
- **Report checksum:** `831271c90261517ec5b98598412f5a7218e53915333aea9ae31464f35a91bef9`
- **Frozen plan:** sha256 `53f2ff50b7079e871a6bf79595a577069b29be9e3ec1f3db345c7234955a1c61`, git blob `aec3e2f64e5a83086081f65cf6ff817a6e0176cc`
- **Frozen workload:** sha256 `f7566e10f3088d0d59b9f37e00e9fce486e7fa7fdb8f01fc9f77d6b3fb3ec390`
- **Fault-conformance report referenced:** checksum `3a0d6e71cf7162144f193b534b64eef6f604a5e3cd2276f70ef954e60b148b56`

## Path-coverage counts

- admitted: 7, completed: 6, failed: 1, retried: 1, cancelled: 1
- duplicate deliveries: 1, redeliveries: 1

## Budget reconciliation (integer cents)

- requested: 1100, finalized: 1000, released: 100

## Concurrency and equivalence

- measured peak concurrency (personal): 2
- measured peak concurrency (generic, non-personal): 4
- serial-vs-distributed equivalence: True
- generic concurrency-4 equivalence: True

## Audit and queue reconciliation

- audit delivered: 20, abandoned: 1, still pending: 0
- queue unacknowledged: 0
