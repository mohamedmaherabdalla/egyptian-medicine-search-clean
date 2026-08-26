# OCR model artifact boundary

The repository versions the three `training_run.json` records because they
freeze the training configuration, seed, source hashes, row counts, epoch
history, validation outcomes, failure examples, base-model identity, and the
SHA-256 hash of each selected checkpoint.

It does not store the `models/cache/` directory or the multi-gigabyte
`model.safetensors` checkpoints in ordinary Git. Those files total roughly
15 GB and several individual blobs exceed GitHub's 100 MB hard limit. The cache
is redownloadable from the base-model identifiers in the run records; trained
weights require Git LFS or a dedicated model registry. Their omission does not
remove any OCR test rows, run summaries, predictions, search cases, or
evaluation outputs from this branch.
