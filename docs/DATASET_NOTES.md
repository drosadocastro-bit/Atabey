# Dataset Notes

Live Kaggle metadata was checked on 2026-06-30.

- Competition slug: `biohub-cell-tracking-during-development`
- Title: Biohub - Cell Tracking During Development
- Brief description: detect and track zebrafish cells through 3D space and time
- Required submission filename: `submission.csv`
- Row id column name: `id`
- Notebook submissions only: yes
- Runtime limits: 720 minutes for CPU and GPU notebooks
- Deadline: 2026-09-29 23:59 UTC

Observed file listing includes:

- `sample_submission.csv`
- sharded test Zarr paths such as `test/44b6_0113de3b.zarr/0/c/0/0/0/0`

Confirmed local probe on 2026-06-30:

- `sample_submission.csv` is present locally and uses columns `id,dataset,row_type,node_id,t,z,y,x,source_id,target_id`.
- node rows use integer voxel centroids and `-1` placeholders for edge fields.
- edge rows use `source_id` and `target_id` references and `-1` placeholders for node fields.
- visible train arrays are Zarr v3 at `sample.zarr/0` with shape `(100, 64, 256, 256)`, dtype `uint16`, and chunks `(1, 64, 256, 256)`.
- visible GEFF labels are sparse graphs with node ids, `t,z,y,x` props, edge ids, and `estimated_number_of_nodes` metadata.

Baseline constraints:

- videos must be streamed one timepoint at a time
- internal graph representation should remain separate from Kaggle's output schema
- voxel-to-physical conversion should be explicit wherever distance is computed
- sparse ground truth is calibration context, not exhaustive truth
