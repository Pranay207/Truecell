"""Transform OCR evidence back into the original rendered page coordinates."""

from __future__ import annotations

import numpy as np


def transformed_box(
    box: tuple | list, matrix: np.ndarray, sx: float = 1, sy: float = 1
) -> list[float]:
    """Map four rectangle corners through an affine/projective transformation."""
    x0, y0, x1, y1 = box
    points = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], float).T
    mapped = matrix @ points
    mapped = mapped[:2] / mapped[2:]
    return [
        round(float(mapped[0].min() * sx), 3),
        round(float(mapped[1].min() * sy), 3),
        round(float(mapped[0].max() * sx), 3),
        round(float(mapped[1].max() * sy), 3),
    ]


def rotation_to_original(degrees: int, width: int, height: int) -> np.ndarray:
    """Inverse coordinate map for PIL's counterclockwise right-angle rotations."""
    return np.array(
        {
            0: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            90: [[0, -1, width], [1, 0, 0], [0, 0, 1]],
            180: [[-1, 0, width], [0, -1, height], [0, 0, 1]],
            270: [[0, 1, 0], [-1, 0, height], [0, 0, 1]],
        }[degrees % 360],
        float,
    )
