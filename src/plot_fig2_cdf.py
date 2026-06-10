import csv
import math
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ── Configuration ─────────────────────────────────────────────────────────────

PATHS = {
    "lb1": "latency_1779869670.csv",   # KB loopback, 50 warmup
    "lb2": "latency_1779871425.csv",   # KB loopback, 50 warmup
    "lb3": "latency_1779872987.csv",   # KB loopback, 0  warmup
    "wA":  "latency_1779873922.csv",   # WiFi run A,  0  warmup
    "wB":  "latency_1779874261.csv",   # WiFi run B,  0  warmup
}
WARMUP = {"lb1": 50, "lb2": 50, "lb3": 0, "wA": 0, "wB": 0}

X_MAX   = 2.5    # ms — crop x-axis here
OUT_PDF = "fig2_latency_cdf.pdf"
OUT_PNG = "fig2_latency_cdf.png"

# IEEE column width ≈ 3.5 in; full-page width ≈ 7.16 in
FIG_W, FIG_H = 3.5, 2.6   # inches — single-column IEEE

# ── Load data ─────────────────────────────────────────────────────────────────

def load(path, warmup=0):
    with open(path) as f:
        rows = list(csv.DictReader(f))[warmup:]
    return np.array([float(r["one_way_ms"]) for r in rows])

lb = np.concatenate([load(PATHS[k], WARMUP[k]) for k in ("lb1", "lb2", "lb3")])
wA = load(PATHS["wA"], WARMUP["wA"])
wB = load(PATHS["wB"], WARMUP["wB"])

def cdf(data):
    s = np.sort(data)
    p = np.arange(1, len(s) + 1) / len(s) * 100
    return s, p

lb_x, lb_p = cdf(lb)
wA_x, wA_p = cdf(wA)
wB_x, wB_p = cdf(wB)

lb_mean  = lb.mean()
wA_mean  = wA.mean()
wB_mean  = wB.mean()
wifi_mean = np.concatenate([wA, wB]).mean()

# ── Plot ──────────────────────────────────────────────────────────────────────

plt.rcParams.update({
    "font.family":      "serif",
    "font.size":        8,
    "axes.labelsize":   8,
    "axes.titlesize":   8,
    "xtick.labelsize":  7,
    "ytick.labelsize":  7,
    "legend.fontsize":  7,
    "lines.linewidth":  1.2,
    "axes.linewidth":   0.6,
    "xtick.major.width":0.6,
    "ytick.major.width":0.6,
    "grid.linewidth":   0.4,
    "pdf.fonttype":     42,   # embed fonts as TrueType
    "ps.fonttype":      42,
})

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

# ── Three CDF curves ──────────────────────────────────────────────────────────
ax.plot(lb_x, lb_p,
        color="#2166ac", lw=1.4, ls="-",
        label=f"Loopback baseline  ($n$={len(lb):,}, $\\mu$={lb_mean:.2f} ms)")

ax.plot(wA_x, wA_p,
        color="#d6604d", lw=1.4, ls="-",
        label=f"WiFi run A  ($n$={len(wA):,}, $\\mu$={wA_mean:.2f} ms)")

ax.plot(wB_x, wB_p,
        color="#f4a582", lw=1.4, ls="--",
        label=f"WiFi run B  ($n$={len(wB):,}, $\\mu$={wB_mean:.2f} ms)")

# ── Vertical mean markers ─────────────────────────────────────────────────────
ax.axvline(lb_mean,   color="#2166ac", lw=0.8, ls=":", alpha=0.85)
ax.axvline(wifi_mean, color="#d6604d", lw=0.8, ls=":", alpha=0.85)

# Small annotations for the mean lines
ax.text(lb_mean + 0.03, 18, f"{lb_mean:.2f} ms",
        color="#2166ac", fontsize=6.5, va="bottom")
ax.text(wifi_mean + 0.03, 18, f"{wifi_mean:.2f} ms",
        color="#d6604d", fontsize=6.5, va="bottom")

# ── Network contribution arrow ────────────────────────────────────────────────
y_arrow = 30
ax.annotate("",
    xy=(wifi_mean, y_arrow), xytext=(lb_mean, y_arrow),
    arrowprops=dict(arrowstyle="<->", color="#555555", lw=0.8))
ax.text((lb_mean + wifi_mean) / 2, y_arrow + 2,
        f"+{wifi_mean - lb_mean:.2f} ms\n(network)",
        ha="center", va="bottom", fontsize=6, color="#555555")

# ── Axes ──────────────────────────────────────────────────────────────────────
ax.set_xlim(0.0, X_MAX)
ax.set_ylim(0, 101)
ax.set_xlabel("One-way latency (ms)")
ax.set_ylabel("Cumulative (%)")
ax.xaxis.set_major_locator(ticker.MultipleLocator(0.5))
ax.xaxis.set_minor_locator(ticker.MultipleLocator(0.25))
ax.yaxis.set_major_locator(ticker.MultipleLocator(25))
ax.grid(True, which="major", alpha=0.35)
ax.grid(True, which="minor", alpha=0.15)

ax.legend(loc="lower right", framealpha=0.9, edgecolor="#cccccc")

fig.tight_layout(pad=0.4)

# ── Save ──────────────────────────────────────────────────────────────────────
fig.savefig(OUT_PDF, dpi=300, bbox_inches="tight")
fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
print(f"Saved: {OUT_PDF}")
print(f"Saved: {OUT_PNG}")

# ── Print summary stats for reference ─────────────────────────────────────────
print("\n--- Stats summary ---")
for name, data in [("Loopback (pooled)", lb), ("WiFi A", wA), ("WiFi B", wB)]:
    s = np.sort(data)
    print(f"{name:<22} n={len(s):>5}  mean={s.mean():.3f}  "
          f"p95={s[int(0.95*len(s))]:.3f}  p99={s[int(0.99*len(s))]:.3f}  "
          f"max={s[-1]:.3f} ms")
print(f"\nNetwork contribution (WiFi pool mean − loopback mean): "
      f"{wifi_mean - lb_mean:.3f} ms one-way")
print(f"As % of 50 ms control cycle: {(wifi_mean - lb_mean)/50*100:.1f}%")
