"""
plot_trajectory.py
------------------
Plots DT vs PT trajectory and computes reality gap metrics.

Usage:
    python3 plot_trajectory.py trajectory_slow.csv [trajectory_medium.csv ...]
    python3 plot_trajectory.py /tmp/trajectory/ --labels "Slow" "Medium" "Fast"
    python3 plot_trajectory.py --no-show

Key design choices:
  - Both trajectories zeroed to (0,0) at their own start so coordinate
    frames don't matter — only divergence from start is measured.
  - Merge uses PT as reference (50 Hz) to avoid oscillation from DT's
    higher rate (250 Hz).
"""

import sys
import pathlib
import argparse
import math


COLOURS = {"DT": "#185FA5", "PT": "#D85A30"}
RUN_COLOURS = ["#185FA5", "#D85A30", "#2A9D3F", "#8B3FA8", "#C8A000"]


def load(csv_path):
    import pandas as pd
    df = pd.read_csv(csv_path)
    dt = df[df["source"] == "DT"].copy().reset_index(drop=True)
    pt = df[df["source"] == "PT"].copy().reset_index(drop=True)
    return dt, pt


def zero_origin(df):
    """Subtract starting position so trajectory begins at (0,0)."""
    df = df.copy()
    df["x"] = df["x"] - df["x"].iloc[0]
    df["y"] = df["y"] - df["y"].iloc[0]
    return df


def align_and_error(dt, pt):
    """
    Zero both trajectories, then merge on nearest timestamp using PT as
    reference (avoids oscillation from DT's higher publish rate).
    Returns DataFrame with: timestamp_ns, dt_x, dt_y, pt_x, pt_y,
                            error_m, time_s
    """
    import pandas as pd
    import numpy as np

    dt = zero_origin(dt.sort_values("timestamp_ns").reset_index(drop=True))
    pt = zero_origin(pt.sort_values("timestamp_ns").reset_index(drop=True))

    # Use PT as left frame — one comparison point per PT sample (~50 Hz)
    merged = pd.merge_asof(
        pt[["timestamp_ns", "x", "y", "speed_mps"]].rename(
            columns={"x": "pt_x", "y": "pt_y", "speed_mps": "pt_speed"}),
        dt[["timestamp_ns", "x", "y", "speed_mps"]].rename(
            columns={"x": "dt_x", "y": "dt_y", "speed_mps": "dt_speed"}),
        on="timestamp_ns",
        direction="nearest",
        tolerance=100_000_000,   # 100 ms tolerance
    ).dropna()

    merged["error_m"] = np.sqrt(
        (merged["dt_x"] - merged["pt_x"])**2 +
        (merged["dt_y"] - merged["pt_y"])**2
    )
    merged["time_s"] = (
        merged["timestamp_ns"] - merged["timestamp_ns"].iloc[0]
    ) / 1e9

    return merged


def print_stats(label, merged):
    err = merged["error_m"]
    import math as _math
    rmse = _math.sqrt((err**2).mean())
    print(f"\n=== {label} ===")
    print(f"  Matched samples : {len(merged)}")
    print(f"  Mean error      : {err.mean():.4f} m")
    print(f"  Median error    : {err.median():.4f} m")
    print(f"  Std dev         : {err.std():.4f} m")
    print(f"  RMSE            : {rmse:.4f} m")
    print(f"  Max error       : {err.max():.4f} m")
    print(f"  p95 error       : {err.quantile(0.95):.4f} m")
    print(f"  p99 error       : {err.quantile(0.99):.4f} m")


def plot_single(csv_path, dt, pt, merged, no_show):
    import matplotlib.pyplot as plt
    import numpy as np

    # Zeroed trajectories for the trajectory panel
    dt_z = zero_origin(dt.sort_values("timestamp_ns").reset_index(drop=True))
    pt_z = zero_origin(pt.sort_values("timestamp_ns").reset_index(drop=True))

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fig.suptitle(f"DT vs PT Trajectory — {csv_path.stem}", fontsize=12)

    # --- Trajectory panel (zeroed, both start at 0,0) ---
    ax = axes[0]
    dt_x, dt_y = dt_z["x"].to_numpy(), dt_z["y"].to_numpy()
    pt_x, pt_y = pt_z["x"].to_numpy(), pt_z["y"].to_numpy()

    ax.plot(dt_x, dt_y, color=COLOURS["DT"], linewidth=1.5,
            label="DT (sim)", alpha=0.85)
    ax.plot(pt_x, pt_y, color=COLOURS["PT"], linewidth=1.5,
            linestyle="--", label="PT (car)", alpha=0.85)
    ax.scatter([0], [0], color=COLOURS["DT"], s=80, zorder=5,
               marker="o", label="Start")
    ax.scatter([dt_x[-1]], [dt_y[-1]], color=COLOURS["DT"], s=80,
               zorder=5, marker="X", label="DT end")
    ax.scatter([pt_x[-1]], [pt_y[-1]], color=COLOURS["PT"], s=80,
               zorder=5, marker="X", label="PT end")
    ax.set_xlabel("x (m) — zeroed")
    ax.set_ylabel("y (m) — zeroed")
    ax.set_title("Trajectory (both zeroed to start)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)
    x_range = max(dt_x.max() - dt_x.min(), pt_x.max() - pt_x.min(), 0.1)
    y_range = max(abs(dt_y).max(), abs(pt_y).max(), 0.1)
    if y_range > 0.1 * x_range:
        ax.set_aspect("equal")

    # --- Error over time ---
    ax = axes[1]
    t  = merged["time_s"].to_numpy()
    er = merged["error_m"].to_numpy()
    ax.plot(t, er, color="#185FA5", linewidth=0.8, alpha=0.8)
    ax.axhline(merged["error_m"].mean(), color="#D85A30", linewidth=1.5,
               linestyle="--",
               label=f"mean {merged['error_m'].mean():.3f} m")
    ax.axhline(merged["error_m"].quantile(0.95), color="#993C1D",
               linewidth=1, linestyle=":",
               label=f"p95 {merged['error_m'].quantile(0.95):.3f} m")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Positional error (m)")
    ax.set_title("DT–PT Positional Error over Time")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.2)

    # --- Error CDF ---
    ax = axes[2]
    sorted_err = np.sort(merged["error_m"].to_numpy())
    cdf = np.arange(1, len(sorted_err) + 1) / len(sorted_err)
    ax.plot(sorted_err, cdf * 100, color="#185FA5", linewidth=1.5)
    ax.axvline(merged["error_m"].quantile(0.95), color="#D85A30",
               linestyle="--", linewidth=1,
               label=f"p95={merged['error_m'].quantile(0.95):.3f}m")
    ax.axvline(merged["error_m"].quantile(0.99), color="#993C1D",
               linestyle=":", linewidth=1,
               label=f"p99={merged['error_m'].quantile(0.99):.3f}m")
    ax.set_xlabel("Positional error (m)")
    ax.set_ylabel("Cumulative %")
    ax.set_title("Error CDF")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.2)

    out = csv_path.with_suffix(".png")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print(f"Plot saved to {out}")
    if not no_show:
        plt.show()
    plt.close()


def plot_comparison(csv_paths, all_merged, labels, no_show):
    import matplotlib.pyplot as plt
    import numpy as np

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("DT–PT Reality Gap — Positional Error Comparison", fontsize=12)

    for i, (label, merged) in enumerate(zip(labels, all_merged)):
        col  = RUN_COLOURS[i % len(RUN_COLOURS)]
        err  = merged["error_m"]
        mean = err.mean()

        sorted_err = np.sort(err.to_numpy())
        cdf = np.arange(1, len(sorted_err) + 1) / len(sorted_err)
        ax1.plot(sorted_err, cdf * 100, color=col, linewidth=1.5,
                 label=f"{label}  (μ={mean:.3f}m)")

        ax2.plot(merged["time_s"].to_numpy(), err.to_numpy(),
                 color=col, linewidth=0.8, alpha=0.7,
                 label=f"{label}  (μ={mean:.3f}m)")

    ax1.set_xlabel("Positional error (m)")
    ax1.set_ylabel("Cumulative %")
    ax1.set_title("Error CDF — all runs")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.2)

    ax2.set_xlabel("Time (s)")
    ax2.set_ylabel("Positional error (m)")
    ax2.set_title("Error over time — all runs")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.2)

    out = csv_paths[0].parent / "trajectory_comparison.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print(f"Comparison plot saved to {out}")
    if not no_show:
        plt.show()
    plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="*")
    parser.add_argument("--labels", nargs="*", default=None)
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args()

    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("Install: pip install pandas matplotlib numpy")
        sys.exit(1)

    if not args.csv:
        candidates = sorted(
            pathlib.Path("/tmp/trajectory").glob("trajectory_*.csv")
        )
        if not candidates:
            print("No CSV found in /tmp/trajectory/")
            sys.exit(1)
        csv_paths = candidates
        print(f"Found {len(csv_paths)} trajectory file(s)")
    else:
        csv_paths = [pathlib.Path(p) for p in args.csv]

    labels = args.labels or [
        p.stem.replace("trajectory_", "") for p in csv_paths
    ]
    if len(labels) != len(csv_paths):
        print("--labels count must match CSV count")
        sys.exit(1)

    all_merged = []
    for csv_path, label in zip(csv_paths, labels):
        dt, pt = load(csv_path)
        if len(dt) == 0:
            print(f"WARNING: no DT data in {csv_path.name}")
            continue
        if len(pt) == 0:
            print(f"WARNING: no PT data in {csv_path.name}")
            continue
        merged = align_and_error(dt, pt)
        print_stats(label, merged)
        plot_single(csv_path, dt, pt, merged, args.no_show)
        all_merged.append(merged)

    if len(all_merged) > 1:
        plot_comparison(csv_paths, all_merged, labels, args.no_show)


if __name__ == "__main__":
    main()