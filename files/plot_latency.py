# """
# plot_latency.py
# ---------------
# Analysis of latency CSV files from latency_logger.py.

# Usage:
#     # Single file
#     python3 plot_latency.py latency_123.csv --warmup 50

#     # Multiple files — overlaid CDFs + combined summary
#     python3 plot_latency.py latency_1.csv latency_2.csv latency_3.csv --warmup 50

#     # Labels for legend (must match number of CSV files)
#     python3 plot_latency.py l1.csv l2.csv --labels "Loopback" "WiFi"

#     # Plot only CDF or only time-series (single file only)
#     python3 plot_latency.py latency_123.csv --no-lot
#     python3 plot_latency.py latency_123.csv --no-cdf

#     --warmup N   discard first N samples per file (default 200)
#     --no-show    save without displaying
#     --lot     skip CDF (single file only)
#     --cdf     skip time-series (single file only)
#     --labels     legend labels for multi-file mode
# """

import sys
import pathlib
import argparse


# Colour palette — distinct enough for up to 6 runs
COLOURS = ["#185FA5", "#D85A30", "#2A9D3F", "#8B3FA8", "#C8A000", "#A83F3F"]


def load(csv_path, warmup):
    import pandas as pd
    df = pd.read_csv(csv_path)
    lat_all = df["one_way_ms"].dropna()
    w = min(warmup, len(lat_all) // 2)
    lat = lat_all.iloc[w:]
    return lat_all, lat, w


def print_stats(name, lat_all, lat, warmup):
    print(f"\n=== {name} ===")
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="*", default=None,
                        help="One or more CSV files. Omit to use most recent in /tmp/latency/")
    parser.add_argument("--warmup", type=int, default=200,
                        help="Discard first N samples per file (default 200)")
    parser.add_argument("--no-show",  action="store_true")
    parser.add_argument("--lot",   action="store_true",
                        help="Skip CDF plot (single file only)")
    parser.add_argument("--cdf",   action="store_true",
                        help="Skip time-series plot (single file only)")
    parser.add_argument("--labels",   nargs="*", default=None,
                        help="Legend labels for multi-file mode (one per CSV)")
    args = parser.parse_args()

    try:
        import pandas as pd
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("Install: pip install pandas matplotlib numpy")
        sys.exit(1)

    # Resolve input files
    if not args.csv:
        candidates = sorted(pathlib.Path("/tmp/latency").glob("latency_*.csv"))
        if not candidates:
            print("No CSV found in /tmp/latency/")
            sys.exit(1)
        csv_paths = [candidates[-1]]
        print(f"Using most recent log: {csv_paths[0]}")
    else:
        csv_paths = [pathlib.Path(p) for p in args.csv]

    # Validate labels
    labels = args.labels or [p.stem for p in csv_paths]
    if len(labels) != len(csv_paths):
        print(f"Error: --labels count ({len(labels)}) must match CSV count ({len(csv_paths)})")
        sys.exit(1)

    multi = len(csv_paths) > 1

    # ----------------------------------------------------------------
    # MULTI-FILE MODE — overlaid CDFs only
    # ----------------------------------------------------------------
    if multi:
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.suptitle(
            f"DT→PT Command Latency — CDF comparison\n"
            f"(discarding first {args.warmup} warmup samples per run)",
            fontsize=10
        )

        for i, (csv_path, label) in enumerate(zip(csv_paths, labels)):
            lat_all, lat, warmup = load(csv_path, args.warmup)
            print_stats(label, lat_all, lat, warmup)

            colour = COLOURS[i % len(COLOURS)]
            sorted_lat = np.sort(lat.values)
            cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)

            ax.plot(sorted_lat, cdf * 100, linewidth=1.5,
                    color=colour, label=f"{label}  (μ={lat.mean():.2f}ms)")

            # Subtle p99 marker
            p99 = lat.quantile(0.99)
            ax.axvline(p99, color=colour, linewidth=0.8,
                       linestyle=":", alpha=0.6)

        ax.set_xlabel("Latency (ms)")
        ax.set_ylabel("Cumulative %")
        ax.set_title("CDF")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.2)

        # Save next to first CSV
        out_path = csv_paths[0].parent / "comparison_cdf.png"
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        print(f"\nPlot saved to {out_path}")

    # ----------------------------------------------------------------
    # SINGLE-FILE MODE — time-series + CDF (with optional flags)
    # ----------------------------------------------------------------
    else:
        csv_path = csv_paths[0]
        lat_all, lat, warmup = load(csv_path, args.warmup)
        print_stats(csv_path.name, lat_all, lat, warmup)

        if args.lot:
            fig, ax1 = plt.subplots(1, 1, figsize=(7, 4))
            ax2 = None
        elif args.cdf:
            fig, ax2 = plt.subplots(1, 1, figsize=(7, 4))
            ax1 = None
        else:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

        fig.suptitle(
            f"DT→PT Command Latency  ({csv_path.name})\n"
            f"steady-state after discarding {warmup} warmup samples",
            fontsize=10
        )

        if ax1 is not None:
            ax1.plot(range(len(lat)), lat.values, linewidth=0.6,
                     color=COLOURS[0], alpha=0.7)
            ax1.axhline(lat.mean(), color="#D85A30", linewidth=1.2,
                        linestyle="--", label=f"mean {lat.mean():.2f} ms")
            ax1.axhline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                        linestyle=":", label=f"p99 {lat.quantile(0.99):.2f} ms")
            ax1.set_xlabel("Sequence # (post-warmup)")
            ax1.set_ylabel("One-way latency (ms)")
            ax1.set_title("Latency over time (steady-state)")
            ax1.legend(fontsize=9)
            ax1.grid(alpha=0.2)

        if ax2 is not None:
            sorted_lat = np.sort(lat.values)
            cdf = np.arange(1, len(sorted_lat) + 1) / len(sorted_lat)
            ax2.plot(sorted_lat, cdf * 100, linewidth=1.5, color=COLOURS[0])
            ax2.axvline(lat.quantile(0.95), color="#D85A30", linewidth=1,
                        linestyle="--", label=f"p95={lat.quantile(0.95):.2f}ms")
            ax2.axvline(lat.quantile(0.99), color="#993C1D", linewidth=1,
                        linestyle=":", label=f"p99={lat.quantile(0.99):.2f}ms")
            ax2.set_xlabel("Latency (ms)")
            ax2.set_ylabel("Cumulative %")
            ax2.set_title("CDF")
            ax2.legend(fontsize=9)
            ax2.grid(alpha=0.2)

        suffix = ("_lot" if args.lot else "") + ("_cdf" if args.cdf else "")
        out_path = csv_path.with_stem(csv_path.stem + suffix).with_suffix(".png")
        plt.tight_layout()
        plt.savefig(out_path, dpi=150)
        print(f"\nPlot saved to {out_path}")

    if not args.no_show:
        plt.show()


if __name__ == "__main__":
    main()