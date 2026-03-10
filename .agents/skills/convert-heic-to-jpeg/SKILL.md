---
name: convert-heic-to-jpeg
description: Convert HEIC or HEIF images to JPEG with `uv run` using inline script dependencies. Use this when new phone photos are added under `pictures/` and need to be converted before indexing or upload.
argument-hint: "[path] [--quality 90] [--overwrite]"
---

# Convert HEIC To JPEG

Use this skill when you need to convert `.heic` or `.heif` images into `.jpg` files for local development workflows.

The script for this skill lives at [./convert_heic_to_jpeg.py](./convert_heic_to_jpeg.py) and is designed to be run with `uv run`.

## What this skill does

- Converts a single HEIC or HEIF file to JPEG.
- Recursively scans a directory for HEIC or HEIF files.
- Writes JPEG files next to the source images by default.
- Can write output into a separate directory.
- Skips existing JPEG files unless `--overwrite` is passed.

## How to run it

Run the script with `uv run` so the inline PEP 723 dependencies are installed automatically:

```bash
uv run .agents/skills/convert-heic-to-jpeg/convert_heic_to_jpeg.py pictures
```

Convert one file:

```bash
uv run .agents/skills/convert-heic-to-jpeg/convert_heic_to_jpeg.py pictures/clothes/IMG_3233.HEIC
```

Convert into a separate output directory:

```bash
uv run .agents/skills/convert-heic-to-jpeg/convert_heic_to_jpeg.py pictures --output-dir converted-pictures
```

Overwrite existing JPEG files:

```bash
uv run .agents/skills/convert-heic-to-jpeg/convert_heic_to_jpeg.py pictures --overwrite
```

## Recommended Workflow

1. Point the script at `pictures/` or a subdirectory such as `pictures/clothes/`.
2. Review the summary output to confirm how many files were converted or skipped.
3. Re-run with `--overwrite` only if you intentionally want to replace existing JPEG outputs.

## Notes

- This skill is stored in `.agents/skills`, which VS Code documents as a default project skill location.
- The script depends on Pillow and `pillow-heif`, declared inline in the script so they can be resolved by `uv run`.
