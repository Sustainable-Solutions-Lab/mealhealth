# SPDX-FileCopyrightText: 2026 Koen van Greevenbroek
#
# SPDX-License-Identifier: CC-BY-4.0

"""Shared plot styling for the example notebooks.

Kept out of the notebooks themselves so every figure in the gallery reads as
one system, and so the notebooks stay about mealhealth rather than about
matplotlib.

The categorical order below is fixed and validated for colour-vision
deficiency; assign slots in order and never cycle them. Gains and losses use a
diverging blue/red pair, because the sign of a result is its most important
property.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

import matplotlib as mpl
import matplotlib.pyplot as plt

# Diverging pair: the polarity of a change in years of life.
GAIN = "#2a78d6"
LOSS = "#e34948"
NEUTRAL = "#b9b8b2"

# Fixed categorical order. Slot 1 first, no cycling.
SERIES: tuple[str, ...] = (
    "#2a78d6",  # blue
    "#008300",  # green
    "#e87ba4",  # magenta
    "#eda100",  # yellow
    "#1baf7a",  # aqua
    "#eb6834",  # orange
    "#4a3aa7",  # violet
    "#e34948",  # red
)

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"


def apply_style() -> None:
    """Apply the gallery's shared matplotlib settings."""

    mpl.rcParams.update(
        {
            "figure.figsize": (7.2, 4.0),
            "figure.dpi": 140,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.prop_cycle": mpl.cycler(color=list(SERIES)),
            "axes.edgecolor": "#d8d7d2",
            "axes.labelcolor": INK_MUTED,
            "axes.titlecolor": INK,
            "axes.titlesize": 11,
            "axes.titleweight": "semibold",
            "axes.titlelocation": "left",
            "axes.titlepad": 10,
            "axes.labelsize": 9.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": "#eceae5",
            "grid.linewidth": 0.8,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "legend.frameon": False,
            "legend.fontsize": 9,
            "lines.linewidth": 2.0,
            "lines.markersize": 5,
            "font.size": 10,
        }
    )


def sign_colors(values: Iterable[float]) -> list[str]:
    """Blue where a value is a gain, red where it is a loss."""

    return [GAIN if value >= 0 else LOSS for value in values]


def label_bars(
    ax: plt.Axes,
    bars: Sequence[mpl.patches.Rectangle],
    values: Sequence[float],
    fmt: str = "{:+.2f}",
    *,
    horizontal: bool = True,
) -> None:
    """Label each bar at its data end, outside the mark.

    Direct labels are the relief that lets the palette carry identity without
    relying on colour alone.
    """

    for bar, value in zip(bars, values, strict=True):
        text = fmt.format(value)
        if horizontal:
            offset = 4 if value >= 0 else -4
            ax.annotate(
                text,
                (bar.get_width(), bar.get_y() + bar.get_height() / 2),
                xytext=(offset, 0),
                textcoords="offset points",
                ha="left" if value >= 0 else "right",
                va="center",
                fontsize=9,
                color=INK_MUTED,
            )
        else:
            offset = 4 if value >= 0 else -4
            ax.annotate(
                text,
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                xytext=(0, offset),
                textcoords="offset points",
                ha="center",
                va="bottom" if value >= 0 else "top",
                fontsize=9,
                color=INK_MUTED,
            )


def zero_line(ax: plt.Axes, *, vertical: bool = True) -> None:
    """Draw the zero baseline that separates gains from losses."""

    if vertical:
        ax.axvline(0, color="#a9a8a2", linewidth=1.0, zorder=2)
    else:
        ax.axhline(0, color="#a9a8a2", linewidth=1.0, zorder=2)


def despine_ticks(ax: plt.Axes) -> None:
    """Recede the tick marks; the labels carry the information."""

    ax.tick_params(length=0)
