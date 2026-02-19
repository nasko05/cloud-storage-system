# Backend Benchmarks

Local benchmark harness for high-cardinality backend paths.

## Benchmarks included

- `folder_children_listing`: paginated `/v2/folders/{folderId}/children` mapping path under large item counts.
- `archive_zip_build`: archive worker zip build throughput simulation with streamed S3 object bodies.

## Commands

Run fast smoke profile (CI-safe):

```bash
python3 backend/benchmarks/run_benchmarks.py --smoke
```

Run full local profile:

```bash
python3 backend/benchmarks/run_benchmarks.py
```

Run with max-duration guard:

```bash
python3 backend/benchmarks/run_benchmarks.py --smoke --assert-max-seconds 10
```
