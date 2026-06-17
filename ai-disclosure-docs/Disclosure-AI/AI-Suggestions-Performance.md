## Context

- **Problem:** Cold-start latency of spawning a new Python process per request is ~6-9s (depends on db size) (model loading ~3s + inference ~2-5s).
- **Architecture:** Single-tenant - each customer has its own app instance and DB. Multiple customer instances coexist on the same host (10+).
- **UI behaviour:** Positions and report suggestions are requested simultaneously - any solution must handle parallel requests without serialisation between them.
- **Baseline (process-spawn):** Python 3.0s + spawn overhead 3.0s = **~6.1s PHP total** (varies 6-9s depending on candidate count).

---

## ONNX Concurrency Background

This context applies to all daemon approaches.

ONNX Runtime is internally multi-threaded: a single `session.run()` call parallelises across CPU cores via its own thread pool (`intra_op_num_threads` defaults to core count). Adding Python-level threading without capping this means N simultaneous requests each launch their own ONNX thread pool, all competing for the same CPU cores - causing context switching and cache thrashing.

### Why naive threading fails

When two Python threads each call `session.run()` simultaneously on an 8-core machine:

- Thread 1 starts inference - ONNX spawns 8 threads, claims all 8 cores
- Thread 2 starts inference simultaneously - ONNX spawns another 8 threads, also trying to claim all 8 cores
- 16 threads now compete for 8 cores

The OS scheduler constantly switches between them, which causes two problems:

1. **Context switching overhead** - every switch costs time; switching 16 threads across 8 cores is expensive
2. **Cache thrashing** - Thread 1's model weight data gets loaded into CPU cache, then evicted when Thread 2's threads run. When Thread 1 resumes, it reloads from RAM. Both threads spend most of their time waiting for memory rather than computing

Result: each request takes ~6.1s instead of ~2.1s - nearly 3x slower individually. Threading added overhead without adding any real parallelism - the CPU was already fully utilised by the first request alone.

**Benchmark - naive threading failure:**

| | User 1 wait | User 2 wait | Total wall clock | Total CPU time |
|---|---|---|---|---|
| Sequential (single-threaded) | 2.1s | 4.2s | 4.2s | 4.2s |
| Concurrent (naive threading) | 6.1s | 6.1s | 6.1s | 12.2s |

Sequential is better for both users and uses 3x less CPU time. Naive threading is strictly worse in every metric.

### Fix - `intra_op_num_threads=2` + semaphore

Cap each inference to exactly 2 cores. On an 8-core host, two concurrent inferences use 2+2=4 cores with no overlap - contention is eliminated. A semaphore bounded to `cpu_count // 2` prevents over-subscription at higher concurrency (a 5th concurrent request waits at the semaphore only - its DB fetch has already completed in parallel). Benchmarks confirm per-request times under concurrency are indistinguishable from single-user baseline.

---

## Option 1 - Per-Customer HTTP Daemon (TCP)

### How it works

A persistent Python process runs per customer instance, listening on a dedicated TCP port (e.g. 5001 for positions, 5002 for reports). Models load once at startup. PHP calls the daemon over HTTP, falling back to process-spawn if unreachable.

### Pros

| | |
|---|---|
| **Eliminates cold-start** | Models load once; PHP-measured latency drops from ~6-9s to ~2.1s |
| **Simple PHP integration** | no new dependencies |
| **Graceful fallback** | Unreachable daemon - silent fallback to process-spawn |
| **Per-customer isolation** | A crashed daemon affects only its customer |
| **Parallel positions + reports** | Second daemon on port 5002 allows parallel requests without serialisation |

### Cons

| | |
|---|---|
| **RAM scales with customer count** | ~300-600 MB per daemon. 10+ customers per host = **3-6 GB+ permanently reserved** for an infrequently-used feature |
| **No model sharing** | All customer daemons load identical model weights independently |
| **Port management per customer** | Each customer needs a unique port (or two). Requires defined port range and network/security team approval |
| **DevOps effort** | New provisioning step per customer per host - start daemon, configure port in `.env.local`, ensure survival across reboots |
| **Concurrent users of same customer serialise** | Single-threaded: N simultaneous users wait ~N x 2.1s |
| **Crash = silent degradation** | Daemon crash silently falls back to 6-9s with no alerting |

### Benchmarks

Single user, TCP loopback (`http://127.0.0.1:5001`), single-threaded daemon:

| | 30 candidates | 60 candidates |
|---|---|---|
| **Positions** | | |
| fetch embeddings | 0.631s | 0.701s |
| cross-encoder predict | 1.039s | 2.501s |
| Python total | 1.775s | 3.276s |
| **PHP wall time** | **1.790s** | **3.291s** |
| **Analytics (reports)** | | |
| fetch embeddings | 0.653s | 0.598s |
| cross-encoder predict | 2.160s | 4.130s |
| Python total | 2.893s | 4.841s |
| **PHP wall time** | **2.903s** | **4.852s** |

Transport overhead is negligible (~15ms) - TCP loopback is not the bottleneck. Candidate count is the main lever: halving from 60 - 30 roughly halves cross-encoder time.

---

## Option 2 - Per-Host HTTP Daemon (TCP)

### How it works

One Python process on a fixed port (e.g. 5001) serves all customer instances on the host. Models are loaded once for the entire host. PHP passes the customer context in the request payload - e.g. the vhost path, and Python reads DB credentials from it at request time.

### Pros

| | |
|---|---|
| **Model weights loaded once per host** | ~300-600 MB total regardless of customer count - vs N x 300-600 MB for per-customer daemons |
| **Single port per host** | One port instead of one per customer |
| **Less DevOps overhead** | One daemon to start, supervise, and monitor per host |
| **Uniform PHP configuration** | All customer instances point to the same URL (`http://127.0.0.1:5001`) |

### Cons

| | |
|---|---|
| **Requires python refactor** | Current design assumes a single DB identity per process. Shared mode requires per-request DB connections or a credential registry |
| **Single point of failure for all tenants** | A crash falls back to process-spawn for every customer on the host simultaneously |
| **All tenants share one serial queue** | Single-threaded: a burst from one customer delays all others on the host |
| **Still requires port approval and supervision** | Same network/security concerns as per-customer; no improvement on supervision |

### Benchmarks

Same hardware as Option 1 (TCP loopback, single-threaded daemon). Results are identical to Option 1 - transport overhead is negligible; per-request inference time is the same.

---

## Option 3 - Per-Customer systemd Socket Activation

### How it works

A Unix socket file per customer (e.g. `/run/sofi/{customer}/suggest.sock`) replaces the TCP port. systemd starts the Python daemon on-demand when PHP first connects. After a configurable idle timeout (e.g. matching the app's auto-logout period), the daemon exits and frees memory. The next request after idle is a cold start.

Two socket pairs per customer (positions + reports) allow parallel UI requests without serialisation between them.

### Pros

| | |
|---|---|
| **No TCP ports** | Unix socket is a file - no port range, no firewall rules, no network/security team approval |
| **On-demand startup** | systemd activates the daemon only when needed - no permanently running processes |
| **Memory freed when idle** | Daemon exits after idle timeout - only active customers consume RAM |
| **Idle timeout aligns with auto-logout** | Natural lifecycle: daemon stays warm while user is active |
| **systemd supervision** | Restart on crash |
| **Per-customer isolation** | Crash affects only that customer |
| **Unix socket faster than TCP loopback** | Lower per-request latency |

### Cons

| | |
|---|---|
| **Cold start on first request (and after idle)** | Model loading ~3s - not eliminated, deferred to first use |
| **Concurrent users of same customer serialise** | Single-threaded: warm daemon serves ~N x 2.1s; cold daemon adds ~3s on top |
| **Two socket pairs per customer doubles unit count** | 10 customers = 40 systemd unit files (2 socket + 2 service per customer) |
| **Two warm daemons doubles memory per customer** | Positions + reports daemons load model weights independently - ~600 MB-1.2 GB per active customer |
| **RAM still scales with customer count** | Per-customer daemons: idle customers free memory, but active customers still multiply it |
| **Idle timeout logic in daemon** | Daemon must track last request time and self-terminate - additional implementation work |
| **Ansible provisioning required** | Templated `.socket` + `.service` units per customer - more than process-spawn |

### Benchmarks

Per-request inference times are identical to the TCP daemon - Unix socket saves ~15ms transport overhead (negligible). The key timing difference is the first-request cold start:

| Scenario | Positions wall time | Analytics wall time |
|---|---|---|
| Warm daemon (single user) | ~1.8-3.3s | ~2.9-4.9s |
| Cold start (first request) | +~3s model load | +~3s model load |
| 2 concurrent users, single-threaded | User 2 waits ~1.5-2s extra | User 2 waits ~2.1s extra |

---

## Option 4 - Shared systemd Socket Activation (Recommended)

### How it works

One Unix socket at a fixed host-level path (e.g. `/var/run/disclosure_ai_position.sock`, `/var/run/disclosure_ai_report.sock`) serves all customer instances on the host. Models load once for the entire host. systemd activates on first connection, supervises the daemon, and cleans up after idle timeout.

PHP passes the customer's context in the request payload. Python reads it to obtain DB credentials for that customer, validates the path against a strict allowlist pattern, then executes the query.

The daemon uses `ThreadingMixIn` with `intra_op_num_threads=2` and a semaphore bounded to `cpu_count // 2` - see ONNX Concurrency Background above.

```python
opts = ort.SessionOptions()
opts.intra_op_num_threads = 2
opts.inter_op_num_threads = 1
session = ort.InferenceSession("model.onnx", sess_options=opts)

SUGGEST_MAX_WORKERS = os.cpu_count() // 2  # tunable via env var
semaphore = threading.Semaphore(SUGGEST_MAX_WORKERS)
```

Every request is accepted immediately into its own thread. The thread runs JSON parse, DB fetch, and cosine pre-filter freely in parallel. **Only the ONNX inference step acquires the semaphore** - so queued requests have already completed the expensive DB work before waiting.

### Pros

| | |
|---|---|
| **Model weights loaded once per host** | ~300-600 MB total regardless of customer count - best memory profile of all options |
| **1 systemd unit pair per host** | One `.socket` + `.service` for all customers - minimal Ansible provisioning |
| **On-demand startup** | systemd activates on first use; memory freed after idle timeout |
| **systemd supervision** | Auto-restart on crash |
| **No TCP ports** | Unix socket - no port approval |
| **Concurrent requests don't serialise** | ThreadingMixIn + thread cap: two simultaneous users see near-identical latency |
| **Positions and reports always parallel** | Separate sockets for each type - UI's parallel requests never block each other |

### Cons

| | |
|---|---|
| **Cold start is shared** | First request (or post-idle restart) pays ~3s model load - this affects the first user of any customer after idle |
| **Blast radius is per-host** | A daemon crash loses AI suggestions for all customers on the host until systemd restarts (~3s recovery) - though fallback to process-spawn remains |
| **Idle timeout is a single shared value** | One timeout for all customers |
| **Requests beyond SUGGEST_MAX_WORKERS queue on semaphore** | On very high concurrency, requests beyond the cap wait - but only at the ONNX step, after DB fetch completes |

### Benchmarks

All timings from Unix socket with `intra_op_num_threads=2`, semaphore at `cpu_count // 2`.

#### Single user - baseline

| | 30 candidates | 60 candidates |
|---|---|---|
| **Positions** | | |
| fetch embeddings | 0.631s | 0.944s |
| cross-encoder predict | 1.039s | 1.558s |
| Python total | 1.775s | 2.601s |
| **PHP wall time** | **1.790s** | **2.616s** |
| **Analytics (reports)** | | |
| fetch embeddings | 0.653s | 0.773s |
| cross-encoder predict | 2.160s | 4.548s |
| Python total | 2.893s | 5.417s |
| **PHP wall time** | **2.903s** | **5.428s** |

User-visible latency for a single user - **2.6-5.4s** - positions and reports load in parallel via separate sockets, so the slower of the two sets the wall clock.

#### Two simultaneous users - single-threaded vs multi-threaded

| | Single-threaded | Multi-threaded | Saving |
|---|---|---|---|
| Positions - User 1 | 2.547s | 2.453s | - |
| Positions - User 2 | 3.455s *(+1.5s queue wait)* | 2.594s | **~0.9s** |
| Analytics - User 1 | 3.267s | 5.022s | - |
| Analytics - User 2 | 5.714s *(+2.1s queue wait)* | 4.587s | **~1.1s** |


#### At scale - semaphore behaviour (8-core host)

| Concurrent requests | Active ONNX threads | CPU cores used | Queue wait |
|---|---|---|---|
| 1-4 | 2 each | 2-8 | 0 |
| 5+ | 8 (capped) | 8 (full) | Wait at semaphore only - DB fetch already done |

---

## Comparison Summary

| | Option 1 - Per-customer TCP | Option 2 - Per-host TCP | Option 3 - Per-customer socket | Option 4 - Shared socket |
|---|---|---|---|---|
| **RAM (10 customers)** | ~3-6 GB | ~300-600 MB | ~0 MB idle / scales active | ~300-600 MB total |
| **Ports required** | Yes (2 per customer) | Yes (1-2) | No | No |
| **Cold start** | No (always warm) | No (always warm) | Yes (first + post-idle) | Yes (first + post-idle) |
| **Concurrent users** | Serialise | Serialise (all tenants) | Serialise | Parallel (thread cap) |
| **Positions + reports parallel** | Yes (2 ports) | Serialise | Yes (2 sockets) | Yes (2 sockets) |
| **DevOps effort** | High (per customer) | Medium | Medium (per customer) | Low (per host) |
| **Blast radius on crash** | Per customer | Per host | Per customer | Per host |
---

## Next Possible Improvements

These are independent of the daemon architecture choice and can be applied on top of any option above.

### 1. Reduce candidate count

**Current:** 60 candidates passed to the cross-encoder.
**Idea:** Lower the cosine pre-filter limit (e.g. 30 candidates).

Cross-encoder inference scales directly with candidate count - halving from 60 - 30 roughly halves its time:

| | 60 candidates | 30 candidates | Saving |
|---|---|---|---|
| Positions cross-encoder | ~1.6s | ~1.0s | **~0.6s** |
| Analytics cross-encoder | ~4.5s | ~2.2s | **~2.3s** |
| **Positions PHP total** | **~2.6s** | **~1.8s** | **~0.8s** |
| **Analytics PHP total** | **~5.4s** | **~2.9s** | **~2.5s** |

This is the single highest-leverage lever available - especially for analytics, where it cuts over 2 seconds.

**Tradeoff:** Fewer candidates means the bi-encoder's cosine pre-filter does more of the ranking work. If the bi-encoder misses a good match outside the top 30, the cross-encoder never sees it. The practical impact on suggestion quality depends on how well the bi-encoder embeddings separate relevant from irrelevant candidates for this dataset.

---

### 2. Cache or optimise the fetch embeddings query

**Current:** The DB fetch of candidate embeddings takes ~0.6-0.9s per request. This runs on every suggestion call, even when the underlying position/report data has not changed.

**Options:**

#### a. Cache

Cache the query result in memory. On subsequent requests with the same key, skip the DB round-trip entirely.

**Saving:** eliminates ~0.6-0.9s on cache hit

#### b. Query optimisation

The fetch embeddings query joins positions/reports with their embedding vectors:
- Use indexes so the filter is covered
- Revisit the query (any possible optimisations)

**Potential saving:** 0.1-0.3s, depending on table size.
