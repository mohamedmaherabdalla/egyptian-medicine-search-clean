# Roboflow Prescription Sources

This directory owns the manifest for nine public Roboflow projects supplied on
2026-07-25. The Roboflow search URL was used for discovery and is not a
downloadable dataset.

## Size Decision

The projects contain about 2,889 source images. The published Pharmacy version
contains 120 files after augmentation, bringing the expected export total to
about 2,959 files. A conservative estimate of 2 MB per file is 5.92 GB before
ZIP compression. The collection is below the requested 10 GB limit, but the
downloader still checks the real server-reported ZIP sizes before transferring
the archives.

The repository already occupies about 20 GB locally. Exports are therefore
written under `raw/`, which Git ignores.

## What The Data Is For

1. Segment handwritten regions from a full prescription.
2. Detect medicine, dosage, frequency, quantity, header, footer, and stamp
   regions.
3. Crop medicine regions and run OCR models on those crops.
4. Compare OCR output with a verified medicine label to generate realistic
   corruption pairs for the search benchmark.
5. Optionally evaluate prescription tampering separately from OCR and medicine
   search.

These datasets do not directly validate Egyptian medicine search. Before they
enter that benchmark, labels must map to the Egyptian catalog, exact image
duplicates must be removed before splitting, augmented copies must stay with
their source image, and uncertain labels must be manually audited.

## Download

Roboflow requires an API key even for scripted export of public Universe
datasets. Keep the key outside the repository:

```bash
export ROBOFLOW_API_KEY='your-private-key'
python3 benchmark_03_ocr/download_roboflow_sources.py --estimate
python3 benchmark_03_ocr/download_roboflow_sources.py --download
```

The first command creates the exports on Roboflow if necessary and reports the
combined ZIP size. The second command refuses to download when the measured
total exceeds 10 GB unless `--allow-over-limit` is supplied.

After download, `download_report.csv` records archive size, SHA-256, extracted
path, and status for every project.
