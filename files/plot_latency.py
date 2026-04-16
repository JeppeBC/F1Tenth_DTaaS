"""
plot_latency.py
---------------
Quick analysis of latency CSV files produced by latency_logger.py.

Usage:
    python3 plot_latency.py /tmp/latency/latency_<timestamp>.csv

Produces:
  - Time-series plot of one-way latency
  - CDF (for reporting in a research paper)
  - Summary stats printed to stdout
"""

import sys
import pathlib
import statistics

def main():
    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("Install dependencies: pip install pandas matplotlib numpy")
        sys.exit(1)

    if len(sys.argv) < 2:
        # Find the most recent CSV in default location
        candidates = sorted(pathlib.Path("/tmp/latency").glob("latency_*.csv"))
        if not candidates:
            print("Usage: python3 plot_latency.py <csv_path>")
            sys.exit(1)
        csv_path = candidates[-1]
        print(f"Using most recent log: {csv_path}")
    else:
        csv_path = pathlib.Path(sys.argv[1])

    df = pd.read_csv(csv_path)
    lat = df["one_way_ms"].dropna()

    # ---- Summary stats ------------------------------------------------
    print(f"\n=== Latency Summary ({csv_path.name}) ===")
    print(f"  Samples : {len(lat)}")
    print(f"  Mean    : {lat.mean():.2f} ms")
    print(f"  Median  : {lat.median():.2f} ms")
    print(f"  Std dev : {lat.std():.2f} ms")
    print(f"  p95     : {lat.quantile(0.95):.2f} ms")
    print(f"  p99     : {lat.quantile(0.99):.2f} ms")
    print(f"  Max     : {lat.max():.2f} ms")
    print(f"  Min     : {lat.min():.2f} ms")

    # ---- Plots --------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle(f"DT→PT Command Latency  ({csv_path.name})", fontsize=11)

    # Time series
    ax1.plot(lat.values, linewidth=0.8, color="#185FA5", alpha=0.8)
    ax1.axhline(lat.mean(), color="#D85A30", linewidth=1.2, linestyle="--",
                label=f"mean {lat.mean():.1f} ms")
    ax1.axhline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                linestyle=":", label=f"p99 {lat.quantile(0.99):.1f} ms")
    ax1.set_xlabel("Command sequence #")
    ax1.set_ylabel("One-way latency (ms)")
    ax1.set_title("Latency over time")
    ax1.legend(fontsize=9)
    ax1.grid(alpha=0.2)

    # CDF
    sorted_lat = np.sort(lat.values)
    cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)
    ax2.plot(sorted_lat, cdf * 100, linewidth=1.5, color="#185FA5")
    ax2.axvline(lat.quantile(0.95), color="#D85A30", linewidth=1,
                linestyle="--", label=f"p95={lat.quantile(0.95):.1f}ms")
    ax2.axvline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                linestyle=":", label=f"p99={lat.quantile(0.99):.1f}ms")
    ax2.set_xlabel("Latency (ms)")
    ax2.set_ylabel("Cumulative %")
    ax2.set_title("CDF")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.2)

    out_path = csv_path.with_suffix(".png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved to {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
