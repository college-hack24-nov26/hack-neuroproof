"""Render real, orientation-aware MRI and segmentation slices as PNG."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Literal

import nibabel as nib
import numpy as np

Plane = Literal["axial", "sagittal", "coronal"]

AXES = {
    "sagittal": 0,
    "coronal": 1,
    "axial": 2,
}

# BraTS segmentation labels.
LABEL_COLORS = {
    1: (255, 100, 120),
    2: (34, 211, 238),
    4: (168, 85, 247),
}


def _chunk(kind: bytes, payload: bytes) -> bytes:
    content = kind + payload
    return (
        struct.pack(">I", len(payload))
        + content
        + struct.pack(">I", zlib.crc32(content) & 0xFFFFFFFF)
    )


def _encode_png(rgb: np.ndarray) -> bytes:
    """Encode one RGB image using Python's standard library."""
    height, width, channels = rgb.shape

    if channels != 3:
        raise ValueError("Expected an RGB image.")

    header = struct.pack(
        ">IIBBBBB",
        width,
        height,
        8,
        2,
        0,
        0,
        0,
    )

    scanlines = b"".join(
        b"\x00" + rgb[row].tobytes()
        for row in range(height)
    )

    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(scanlines, level=6))
        + _chunk(b"IEND", b"")
    )


def render_mri_slice(
    modality_path: Path,
    segmentation_path: Path,
    *,
    plane: Plane,
    position: float,
    overlay: bool,
) -> bytes:
    """Render an actual MRI slice and optional real segmentation overlay."""

    # Canonical RAS+ orientation avoids treating arbitrary stored axes
    # as anatomical directions.
    source = nib.as_closest_canonical(
        nib.load(str(modality_path))
    )
    segmentation = nib.as_closest_canonical(
        nib.load(str(segmentation_path))
    )

    if (
        len(source.shape) != 3
        or len(segmentation.shape) != 3
        or source.shape != segmentation.shape
        or not np.allclose(
            source.affine,
            segmentation.affine,
            atol=1e-3,
            rtol=0,
        )
    ):
        raise ValueError(
            "MRI and segmentation geometry do not match."
        )

    axis = AXES[plane]
    index = round(
        (source.shape[axis] - 1)
        * max(0.0, min(1.0, position))
    )

    # Read authentic NIfTI voxel intensities.
    volume = np.asarray(
        source.dataobj,
        dtype=np.float32,
    )

    image_slice = np.take(volume, index, axis=axis)
    image_slice = np.rot90(image_slice)

    finite = np.isfinite(image_slice)
    foreground = image_slice[
        finite & (image_slice != 0)
    ]

    if foreground.size:
        low, high = np.percentile(
            foreground,
            [1, 99],
        )
    else:
        low, high = 0.0, 1.0

    if high <= low:
        high = low + 1.0

    clean = np.where(finite, image_slice, low)

    grayscale = (
        np.clip(
            (clean - low) / (high - low),
            0.0,
            1.0,
        )
        * 255
    ).astype(np.uint8)

    rgb = np.repeat(
        grayscale[:, :, None],
        3,
        axis=2,
    )

    if overlay:
        mask_volume = np.asarray(
            segmentation.dataobj,
            dtype=np.int16,
        )

        mask_slice = np.rot90(
            np.take(mask_volume, index, axis=axis)
        )

        for label, color in LABEL_COLORS.items():
            region = mask_slice == label

            if np.any(region):
                base = rgb[region].astype(np.float32)
                tint = np.asarray(
                    color,
                    dtype=np.float32,
                )

                rgb[region] = (
                    0.45 * base + 0.55 * tint
                ).astype(np.uint8)

    return _encode_png(rgb)
