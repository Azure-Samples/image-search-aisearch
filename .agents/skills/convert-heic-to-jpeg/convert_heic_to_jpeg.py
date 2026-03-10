# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pillow>=11.0.0",
#   "pillow-heif>=0.22.0",
# ]
# ///

"""Convert HEIC and HEIF images to JPEG format."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
import pillow_heif

# Register HEIF support with Pillow before opening files.
pillow_heif.register_heif_opener()

SUPPORTED_EXTENSIONS = {".heic", ".heif"}


@dataclass(frozen=True)
class ConversionResult:
    """Capture the outcome for a single source image."""

    source_path: Path
    output_path: Path
    status: str


def is_heif_file(path: Path) -> bool:
    """Return whether the path has a supported HEIF extension."""
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def build_output_path(
    source_path: Path, input_root: Path, output_dir: Path | None
) -> Path:
    """Build the destination JPEG path for a source HEIF image."""
    if output_dir is None:
        return source_path.with_suffix(".jpg")

    if input_root.is_file():
        return output_dir / f"{source_path.stem}.jpg"

    relative_path = source_path.relative_to(input_root).with_suffix(".jpg")
    return output_dir / relative_path


def save_as_jpeg(source_path: Path, output_path: Path, quality: int) -> None:
    """Open a HEIF image and save it as JPEG."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source_path) as image:
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image.save(output_path, "JPEG", quality=quality)


def convert_heic_to_jpeg(
    source_path: Path,
    input_root: Path,
    output_dir: Path | None = None,
    quality: int = 90,
    overwrite: bool = False,
) -> ConversionResult:
    """Convert one HEIF image to JPEG."""
    output_path = build_output_path(source_path, input_root, output_dir)

    if output_path.exists() and not overwrite:
        return ConversionResult(
            source_path=source_path, output_path=output_path, status="skipped"
        )

    save_as_jpeg(source_path, output_path, quality)
    return ConversionResult(
        source_path=source_path, output_path=output_path, status="converted"
    )


def gather_source_files(input_path: Path) -> list[Path]:
    """Return all HEIF images under the given file or directory."""
    if input_path.is_file():
        if not is_heif_file(input_path):
            raise ValueError(f"Unsupported input file: {input_path}")
        return [input_path]

    return sorted(
        path for path in input_path.rglob("*") if path.is_file() and is_heif_file(path)
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Convert HEIC or HEIF images to JPEG")
    parser.add_argument("input", type=Path, help="Input HEIC/HEIF file or directory")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory for JPEG files",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=90,
        help="JPEG quality from 1 to 100 (default: 90)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing JPEG files instead of skipping them",
    )
    return parser.parse_args()


def main() -> int:
    """Run the CLI conversion workflow."""
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input path does not exist: {args.input}")

    if not 1 <= args.quality <= 100:
        raise ValueError("Quality must be between 1 and 100")

    source_files = gather_source_files(args.input)
    if not source_files:
        print("No HEIC or HEIF files found.")
        return 0

    converted_count = 0
    skipped_count = 0

    for source_path in source_files:
        result = convert_heic_to_jpeg(
            source_path=source_path,
            input_root=args.input,
            output_dir=args.output_dir,
            quality=args.quality,
            overwrite=args.overwrite,
        )
        print(f"{result.status:9} {result.source_path} -> {result.output_path}")
        if result.status == "converted":
            converted_count += 1
        else:
            skipped_count += 1

    print(
        f"Summary: converted={converted_count} skipped={skipped_count} total={len(source_files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
