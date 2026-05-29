# """
# plot_latency.py
# ---------------
# Analysis of latency CSV files from latency_logger.py.

# Usage:
#     python3 plot_latency.py [csv_path] [--warmup N] [--no-show]

#     --warmup N   discard first N samples (default 200, removes startup spike)
#     --no-show    save plot without displaying (useful for headless runs)

# Produces:
#   - Time-series plot of one-way latency (steady-state only)
#   - CDF for paper reporting
#   - Summary stats to stdout
# """

import sys
import pathlib
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default=None)
    parser.add_argument("--warmup", type=int, default=200,
                        help="Discard first N samples (startup transient)")
    parser.add_argument("--no-show", action="store_true")
    parser.add_argument("--no-cdf", action="store_true", help="Skip CDF plot")
    parser.add_argument("--no-lot", action="store_true", help="Skip time-series plot")
    args = parser.parse_args()

    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("Install: pip install pandas matplotlib numpy")
        sys.exit(1)

    if args.csv is None:
        candidates = sorted(pathlib.Path("/tmp/latency").glob("latency_*.csv"))
        if not candidates:
            print("No CSV found in /tmp/latency/")
            sys.exit(1)
        csv_path = candidates[-1]
        print(f"Using most recent log: {csv_path}")
    else:
        csv_path = pathlib.Path(args.csv)

    df = pd.read_csv(csv_path)
    lat_all = df["one_way_ms"].dropna()

    # Discard startup transient
    warmup = min(args.warmup, len(lat_all) // 2)
    lat = lat_all.iloc[warmup:]

    print(f"\n=== Latency Summary: {csv_path.name} ===")
    print(f"  Total samples : {len(lat_all)}")
    print(f"  Warmup discard: {warmup}")
    print(f"  Analysed      : {len(lat)}")
    print(f"  ----------------------------------------")
    print(f"  Mean    : {lat.mean():.3f} ms")
    print(f"  Median  : {lat.median():.3f} ms")
    print(f"  Std dev : {lat.std():.3f} ms")
    print(f"  Min     : {lat.min():.3f} ms")
    print(f"  p50     : {lat.quantile(0.50):.3f} ms")
    print(f"  p95     : {lat.quantile(0.95):.3f} ms")
    print(f"  p99     : {lat.quantile(0.99):.3f} ms")
    print(f"  Max     : {lat.max():.3f} ms")

    if args.no_cdf:
        fig, ax1 = plt.subplots(1, 1, figsize=(7, 4))
    elif args.no_lot:
        fig, ax2 = plt.subplots(1, 1, figsize=(7, 4))
    else:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    fig.suptitle(
        f"DT→PT Command Latency  ({csv_path.name})\n"
        f"steady-state after discarding {warmup} warmup samples",
        fontsize=10
    )

    if not args.no_lot:
        # Time series — show sequence number relative to warmup start
        ax1.plot(range(len(lat)), lat.values, linewidth=0.6,
                color="#185FA5", alpha=0.7)
        ax1.axhline(lat.mean(), color="#D85A30", linewidth=1.2,
                    linestyle="--", label=f"mean {lat.mean():.2f} ms")
        ax1.axhline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                    linestyle=":", label=f"p99 {lat.quantile(0.99):.2f} ms")
        ax1.set_xlabel("Sequence # (post-warmup)")
        ax1.set_ylabel("One-way latency (ms)")
        ax1.set_title("Latency over time (steady-state)")
        ax1.legend(fontsize=9)
        ax1.grid(alpha=0.2)

    if not args.no_cdf:
        # CDF
        sorted_lat = np.sort(lat.values)
        cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)
        ax2.plot(sorted_lat, cdf * 100, linewidth=1.5, color="#185FA5")
        ax2.axvline(lat.quantile(0.95), color="#D85A30", linewidth=1,
                    linestyle="--", label=f"p95={lat.quantile(0.95):.2f}ms")
        ax2.axvline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                    linestyle=":", label=f"p99={lat.quantile(0.99):.2f}ms")
        ax2.set_xlabel("Latency (ms)")
        ax2.set_ylabel("Cumulative %")
        ax2.set_title("CDF")
        ax2.legend(fontsize=9)
        ax2.grid(alpha=0.2)

    suffix = "_no_cdf" if args.no_cdf else ""
    suffix += "_no_lot" if args.no_lot else ""
    out_path = csv_path.with_stem(csv_path.stem + suffix).with_suffix(".png")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    print(f"\nPlot saved to {out_path}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()
