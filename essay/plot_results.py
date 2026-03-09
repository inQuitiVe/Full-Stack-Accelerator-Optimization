#!/usr/bin/env python3
"""
plot_results.py — 自 dse_merged_p1p2p3.json 產生論文圖表

Usage:
  python plot_results.py [--input PATH] [--output-dir DIR]

Output:
  - essay/figures/fig_5_1.png ~ fig_5_9.png
  - essay/tables/table_5_1*.md ~ table_5_5*.md (Markdown)
  - essay/tables/table_5_2_group_a.png, table_5_5_pareto.png (table images)
"""

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
matplotlib.use("Agg")

# 中文字體（若系統無則 fallback）
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial Unicode MS", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False

WORKSPACE = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = WORKSPACE / "workspace" / "dse_merged_p1p2p3.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "figures"
DEFAULT_TABLES = Path(__file__).resolve().parent / "tables"


def load_data(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["results"]


def _by_group(results: list, group: str) -> list:
    return [r for r in results if r.get("group") == group]


def _display_group(r) -> str:
    """Map original group (A,B,C,D,E,G,H) to regrouped (A, BC, DEGH)."""
    g = r.get("group", "?")
    if g == "A":
        return "A"
    if g in ("B", "C"):
        return "BC"
    if g in ("D", "E", "G", "H"):
        return "DEGH"
    return g


def _freq_mhz(r) -> float:
    return r["params"].get("frequency", 0) / 1e6


# ── Fig 5-1: Group A EDA 雷達圖 ─────────────────────────────────────────────
def plot_fig_5_1(results: list, out_dir: Path):
    group_a = _by_group(results, "A")
    if not group_a:
        return
    labels = ["Accuracy", "Energy\n(norm)", "Timing\n(norm)", "Area\n(norm)"]
    angles = [i * 360 / 4 for i in range(4)] + [0]
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(projection="polar"))
    accs = [r["accuracy"] for r in group_a]
    energies = [r["energy_uj"] for r in group_a]
    timings = [r["timing_us"] for r in group_a]
    areas = [r["area_mm2"] for r in group_a]
    e_norm = [(max(energies) - e) / (max(energies) - min(energies)) if max(energies) != min(energies) else 0.5 for e in energies]
    t_norm = [(max(timings) - t) / (max(timings) - min(timings)) if max(timings) != min(timings) else 0.5 for t in timings]
    a_norm = [(max(areas) - a) / (max(areas) - min(areas)) if max(areas) != min(areas) else 0.5 for a in areas]
    names = ["A1 low", "A2 high", "A3 cg+leak", "A4 area", "A5 timing"]
    for i, r in enumerate(group_a):
        vals = [accs[i], e_norm[i], t_norm[i], a_norm[i]]
        vals = vals + [vals[0]]
        ax.plot([a * 3.14159 / 180 for a in angles], vals, "o-", label=names[i], linewidth=2)
    ax.set_xticks([a * 3.14159 / 180 for a in angles[:-1]])
    ax.set_xticklabels(labels)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.0))
    ax.set_ylim(0, 1)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_1_eda_radar.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-2: Group BC 架構 vs Energy, Area ──────────────────────────────────
def plot_fig_5_2(results: list, out_dir: Path):
    group_b = _by_group(results, "B")  # BC-B
    if not group_b:
        return
    fig, ax = plt.subplots(figsize=(6, 5))
    hd_vals = [r["params"]["hd_dim"] for r in group_b]
    energies = [r["energy_uj"] / 1e3 for r in group_b]
    areas = [r["area_mm2"] for r in group_b]
    colors = ["#1f77b4" if h == 2048 else "#ff7f0e" for h in hd_vals]
    ax.scatter(energies, areas, c=colors, s=80, alpha=0.8, edgecolors="black")
    for i, r in enumerate(group_b):
        ax.annotate(f"B{r['dp']}", (energies[i], areas[i]), fontsize=9, xytext=(5, 5), textcoords="offset points")
    ax.set_xlabel("Energy (kµJ)")
    ax.set_ylabel("Area (mm²)")
    ax.set_title("Group BC: Architecture vs. Energy & Area")
    ax.legend(handles=[
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#1f77b4", label="hd_dim=2048"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="#ff7f0e", label="hd_dim=4096"),
    ])
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_2_arch_energy_area.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-3: inner_dim vs cycles, Energy ────────────────────────────────────
def plot_fig_5_3(results: list, out_dir: Path):
    inner_exps = [r for r in results if r["params"].get("inner_dim") in (1024, 2048, 4096) and r["params"].get("frequency") == 1e8]
    if not inner_exps:
        return
    inner_exps = sorted(inner_exps, key=lambda r: r["params"]["inner_dim"])
    dims = [str(r["params"]["inner_dim"]) for r in inner_exps]
    cycles = [r.get("p3_execution_cycles", 0) / 1e3 for r in inner_exps]
    energies = [r["energy_uj"] / 1e3 for r in inner_exps]
    fig, ax1 = plt.subplots(figsize=(5, 4))
    x = range(len(dims))
    ax1.bar([i - 0.2 for i in x], cycles, 0.4, label="p3_cycles (k)", color="#1f77b4")
    ax1.set_ylabel("Execution Cycles (k)")
    ax2 = ax1.twinx()
    ax2.bar([i + 0.2 for i in x], energies, 0.4, label="Energy (kµJ)", color="#ff7f0e", alpha=0.7)
    ax2.set_ylabel("Energy (kµJ)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(dims)
    ax1.set_xlabel("inner_dim")
    ax1.set_title("inner_dim vs. Cycles & Energy (100 MHz)")
    ax1.legend(loc="upper left")
    ax2.legend(loc="upper right")
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_3_inner_dim_cycles.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-4: Frequency vs Accuracy ───────────────────────────────────────────
def plot_fig_5_4(results: list, out_dir: Path):
    g_inner2048 = [r for r in _by_group(results, "G") if r["params"].get("inner_dim") == 2048]
    h_base = _by_group(results, "H")
    fig, ax = plt.subplots(figsize=(7, 5))
    if g_inner2048:
        freqs = [_freq_mhz(r) for r in sorted(g_inner2048, key=_freq_mhz)]
        accs = [r["accuracy"] for r in sorted(g_inner2048, key=_freq_mhz)]
        ax.plot(freqs, accs, "o-", label="G: inner_dim=2048", linewidth=2, markersize=8)
    if h_base:
        freqs = [_freq_mhz(r) for r in sorted(h_base, key=_freq_mhz)]
        accs = [r["accuracy"] for r in sorted(h_base, key=_freq_mhz)]
        ax.plot(freqs, accs, "s-", label="H: base arch", linewidth=2, markersize=8)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Accuracy")
    ax.set_title("Frequency vs. Accuracy")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_4_freq_vs_accuracy.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-5: Frequency vs Timing ─────────────────────────────────────────────
def plot_fig_5_5(results: list, out_dir: Path):
    freq_exps = [r for r in results if "frequency" in r["params"] and r.get("timing_us")]
    freq_exps = sorted(freq_exps, key=_freq_mhz)
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {"A": "#1f77b4", "BC": "#ff7f0e", "DEGH": "#2ca02c"}
    for dg in ["A", "BC", "DEGH"]:
        subset = [r for r in freq_exps if _display_group(r) == dg]
        if subset:
            ax.scatter([_freq_mhz(r) for r in subset], [r["timing_us"] for r in subset], c=colors[dg], label=dg, s=50)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Timing (µs)")
    ax.set_title("Frequency vs. Timing")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_5_freq_vs_timing.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-6: Frequency vs timing_slack ───────────────────────────────────────
def plot_fig_5_6(results: list, out_dir: Path):
    slack_exps = [r for r in results if r.get("p2_timing_slack_ns") is not None]
    slack_exps = sorted(slack_exps, key=_freq_mhz)
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {"A": "#1f77b4", "BC": "#ff7f0e", "DEGH": "#2ca02c"}
    for dg in ["A", "BC", "DEGH"]:
        subset = [r for r in slack_exps if _display_group(r) == dg]
        if subset:
            ax.scatter([_freq_mhz(r) for r in subset], [r["p2_timing_slack_ns"] for r in subset], c=colors[dg], label=dg, s=50)
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Timing Slack (ns)")
    ax.set_title("Frequency vs. Timing Slack")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_6_freq_vs_slack.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-7: Pareto Accuracy vs Energy ──────────────────────────────────────
def plot_fig_5_7(results: list, out_dir: Path):
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {"A": "#1f77b4", "BC": "#ff7f0e", "DEGH": "#2ca02c"}
    for dg in ["A", "BC", "DEGH"]:
        subset = [r for r in results if _display_group(r) == dg]
        if subset:
            ax.scatter(
                [r["energy_uj"] / 1e3 for r in subset],
                [r["accuracy"] for r in subset],
                c=colors[dg], s=60, alpha=0.8, edgecolors="black", label=dg
            )
            for r in subset:
                ax.annotate(f"{r.get('group','?')}{r['dp']}", (r["energy_uj"] / 1e3, r["accuracy"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Energy (kµJ)")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs. Energy (Pareto Front)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_7_pareto_energy.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-9: 3D Pareto Front (Accuracy, Latency, Energy) ──────────────────────
def _is_pareto_dominated(idx: int, points: list, objectives: tuple) -> bool:
    """Check if point idx is dominated by any other. objectives: (max_acc, min_lat, min_ene)."""
    acc_i, lat_i, ene_i = points[idx]
    for j, (acc_j, lat_j, ene_j) in enumerate(points):
        if j == idx:
            continue
        # j dominates i if j is >= acc, <= lat, <= ene, with at least one strict
        if acc_j >= acc_i and lat_j <= lat_i and ene_j <= ene_i:
            if acc_j > acc_i or lat_j < lat_i or ene_j < ene_i:
                return True
    return False


def plot_fig_5_9_pareto_3d(results: list, out_dir: Path, acc_threshold: float = 0.75):
    """3D scatter: Accuracy (Y), Latency (X), Energy (Z). Feasible vs Infeasible, threshold plane."""
    # Extract data
    acc = [r["accuracy"] for r in results]
    lat = [r["timing_us"] / 1000 for r in results]  # ms for readability
    ene = [r["energy_uj"] / 1e6 for r in results]   # J (×10⁶ µJ)

    feasible = [r for r in results if r["accuracy"] >= acc_threshold]
    infeasible = [r for r in results if r["accuracy"] < acc_threshold]

    # Pareto front among feasible
    points = [(r["accuracy"], r["timing_us"], r["energy_uj"]) for r in feasible]
    pareto_idx = [i for i in range(len(points)) if not _is_pareto_dominated(i, points, (1, -1, -1))]
    pareto_points = [feasible[i] for i in pareto_idx]

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    # Accuracy threshold plane (horizontal at acc_threshold)
    lat_min, lat_max = min(lat), max(lat)
    ene_min, ene_max = min(ene), max(ene)
    lat_plane = np.linspace(lat_min, lat_max, 10)
    ene_plane = np.linspace(ene_min, ene_max, 10)
    LAT, ENE = np.meshgrid(lat_plane, ene_plane)
    ACC = np.full_like(LAT, acc_threshold)
    ax.plot_surface(LAT, ACC, ENE, alpha=0.25, color="yellow", label="Accuracy threshold")

    # Infeasible points (below threshold) — light orange triangles
    if infeasible:
        ax.scatter(
            [r["timing_us"] / 1000 for r in infeasible],
            [r["accuracy"] for r in infeasible],
            [r["energy_uj"] / 1e6 for r in infeasible],
            c="#ffb347", marker="^", s=80, alpha=0.9, edgecolors="black", label="Infeasible"
        )

    # Feasible points — dark green circles
    if feasible:
        ax.scatter(
            [r["timing_us"] / 1000 for r in feasible],
            [r["accuracy"] for r in feasible],
            [r["energy_uj"] / 1e6 for r in feasible],
            c="#2d5a27", marker="o", s=60, alpha=0.9, edgecolors="black", label="Feasible"
        )

    # Pareto front — red stars (highlight)
    if pareto_points:
        ax.scatter(
            [r["timing_us"] / 1000 for r in pareto_points],
            [r["accuracy"] for r in pareto_points],
            [r["energy_uj"] / 1e6 for r in pareto_points],
            c="#c41e3a", marker="*", s=200, alpha=1.0, edgecolors="black", label="Pareto front"
        )

    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("Accuracy")
    ax.set_zlabel("Energy (J)")
    ax.set_title("3D Design Space: Accuracy, Latency, Energy")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(lat_min, lat_max)
    ax.set_ylim(min(acc), max(acc))
    ax.set_zlim(ene_min, ene_max)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_9_pareto_3d.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Fig 5-8: Pareto Accuracy vs Timing ───────────────────────────────────────
def plot_fig_5_8(results: list, out_dir: Path):
    fig, ax = plt.subplots(figsize=(7, 5))
    colors = {"A": "#1f77b4", "BC": "#ff7f0e", "DEGH": "#2ca02c"}
    for dg in ["A", "BC", "DEGH"]:
        subset = [r for r in results if _display_group(r) == dg]
        if subset:
            ax.scatter(
                [r["timing_us"] for r in subset],
                [r["accuracy"] for r in subset],
                c=colors[dg], s=60, alpha=0.8, edgecolors="black", label=dg
            )
            for r in subset:
                ax.annotate(f"{r.get('group','?')}{r['dp']}", (r["timing_us"], r["accuracy"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Timing (µs)")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs. Timing (Pareto Front)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "fig_5_8_pareto_timing.png", dpi=150, bbox_inches="tight")
    plt.close()


# ── Tables ────────────────────────────────────────────────────────────────────
def _fmt_num(x, decimals=0):
    if x is None:
        return "—"
    if isinstance(x, float):
        if x >= 1000:
            return f"{x:,.0f}"
        return f"{x:.{decimals}f}".rstrip("0").rstrip(".")
    return str(x)


def gen_tables(results: list, tables_dir: Path):
    """Generate Markdown tables and table images (PNG)."""
    tables_dir.mkdir(parents=True, exist_ok=True)

    # ── Table 1: Overall statistics ───────────────────────────────────────────
    acc = [r["accuracy"] for r in results]
    ene = [r["energy_uj"] for r in results]
    tim = [r["timing_us"] for r in results]
    area = [r["area_mm2"] for r in results]
    cycles = [r.get("p3_execution_cycles") for r in results if r.get("p3_execution_cycles")]

    md = """# 表 5-1：33 點實驗之 PPA 統計

| 指標 | 最小值 | 最大值 | 平均值 |
| :--- | :--- | :--- | :--- |
| Accuracy | {acc_min:.3f} | {acc_max:.3f} | {acc_avg:.3f} |
| Energy (µJ) | {ene_min:,.0f} | {ene_max:,.0f} | {ene_avg:,.0f} |
| Timing (µs) | {tim_min:,.1f} | {tim_max:,.1f} | {tim_avg:,.1f} |
| Area (mm²) | {area_min:.2f} | {area_max:.2f} | {area_avg:.2f} |
| p3_cycles | {cyc_min:,} | {cyc_max:,} | {cyc_avg:,.0f} |
""".format(
        acc_min=min(acc), acc_max=max(acc), acc_avg=sum(acc) / len(acc),
        ene_min=min(ene), ene_max=max(ene), ene_avg=sum(ene) / len(ene),
        tim_min=min(tim), tim_max=max(tim), tim_avg=sum(tim) / len(tim),
        area_min=min(area), area_max=max(area), area_avg=sum(area) / len(area),
        cyc_min=int(min(cycles)) if cycles else 0, cyc_max=int(max(cycles)) if cycles else 0,
        cyc_avg=sum(cycles) / len(cycles) if cycles else 0,
    )
    (tables_dir / "table_5_1_overall_stats.md").write_text(md, encoding="utf-8")

    # ── Table 2: Group A EDA ───────────────────────────────────────────────────
    group_a = _by_group(results, "A")
    if group_a:
        rows = []
        names = ["A1 low", "A2 high", "A3 cg+leak", "A4 area", "A5 timing"]
        for i, r in enumerate(group_a):
            rows.append(f"| {r['group']}{r['dp']} | {names[i]} | {r['accuracy']:.3f} | {r['energy_uj']:,.0f} | {r['timing_us']:,.1f} | {r['area_mm2']:.2f} | {r.get('p2_dynamic_power_mw', 0):.1f} |")
        md = """# 表 5-2：Group A EDA 策略之 PPA 比較

| DP | 策略簡述 | Accuracy | Energy (µJ) | Timing (µs) | Area (mm²) | Power (mW) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(rows)
        (tables_dir / "table_5_2_group_a.md").write_text(md, encoding="utf-8")

    # ── Table 3: Group BC ─────────────────────────────────────────────────────
    group_b = _by_group(results, "B")
    group_c = _by_group(results, "C")
    arch_names = ["small (oc1=4,oc2=8)", "mid (oc1=16,oc2=32)", "hd=4096 small", "hd=4096 large", "hd=4096 mixed"]
    rows_b = []
    for i, r in enumerate(group_b):
        arch = arch_names[i] if i < len(arch_names) else "-"
        rows_b.append(f"| B{r['dp']} | {arch} | {r['params']['hd_dim']} | {r['params']['reram_size']} | {r['accuracy']:.3f} | {r['energy_uj']:,.0f} | {r['area_mm2']:.2f} |")
    rows_c = []
    for r in group_c:
        cyc = int(r.get("p3_execution_cycles", 0))
        rows_c.append(f"| C{r['dp']} | {r['params']['inner_dim']} | {cyc:,} | {r['accuracy']:.3f} | {r['energy_uj']:,.0f} | {r['timing_us']:,.1f} |")
    md = """# 表 5-3：Group BC 架構與 inner_dim

## BC-B 架構規模

| DP | 架構 | hd_dim | reram | Accuracy | Energy (µJ) | Area (mm²) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(rows_b) + """

## BC-C inner_dim

| DP | inner_dim | p3_cycles | Accuracy | Energy (µJ) | Timing (µs) |
| :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(rows_c)
    (tables_dir / "table_5_3_group_bc.md").write_text(md, encoding="utf-8")

    # ── Table 4: Group DEGH 頻率精選 ───────────────────────────────────────────
    degh = [r for r in results if r.get("group") in ("D", "E", "G", "H")]
    degh = sorted(degh, key=lambda r: (_freq_mhz(r), r["params"].get("inner_dim", 0)))
    rows = []
    for r in degh[:20]:  # 精選前 20 筆
        freq = _freq_mhz(r)
        inner = r["params"].get("inner_dim", "-")
        arch = f"inner={inner}" if inner != 1024 else "base"
        if r["group"] == "D":
            arch = "small"
        elif r["group"] == "E":
            arch = "large"
        slack = r.get("p2_timing_slack_ns") or 0
        rows.append(f"| {r['group']}{r['dp']} | {arch} | {freq:.0f} | {r['accuracy']:.3f} | {r['energy_uj']:,.0f} | {r['timing_us']:,.1f} | {slack:.2f} |")
    md = """# 表 5-4：Group DEGH 頻率與 PPA（精選）

| DP | 架構 | 頻率 (MHz) | Accuracy | Energy (µJ) | Timing (µs) | Slack (ns) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(rows)
    (tables_dir / "table_5_4_group_degh.md").write_text(md, encoding="utf-8")

    # ── Table 5: Pareto 候選 ───────────────────────────────────────────────────
    pareto_candidates = [r for r in results if r["accuracy"] >= 0.90]
    pareto_candidates = sorted(pareto_candidates, key=lambda r: r["energy_uj"])[:10]
    rows = []
    for r in pareto_candidates:
        rows.append(f"| {r['group']}{r['dp']} | {_display_group(r)} | {r['accuracy']:.3f} | {r['energy_uj']:,.0f} | {r['timing_us']:,.1f} | {r['area_mm2']:.2f} |")
    md = """# 表 5-5：Pareto 候選（Accuracy ≥ 0.90）

| DP | 組別 | Accuracy | Energy (µJ) | Timing (µs) | Area (mm²) |
| :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(rows)
    (tables_dir / "table_5_5_pareto.md").write_text(md, encoding="utf-8")

    # ── 繪製表格圖 (matplotlib table) ────────────────────────────────────────
    def _draw_table(rows, cols, title, fname):
        fig, ax = plt.subplots(figsize=(12, max(4, len(rows) * 0.35)))
        ax.axis("off")
        table = ax.table(cellText=rows, colLabels=cols, loc="center", cellLoc="center")
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(1.2, 1.8)
        for (i, j), cell in table.get_celld().items():
            if i == 0:
                cell.set_facecolor("#4472C4")
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_facecolor("#E7E6E6" if i % 2 == 0 else "white")
        plt.title(title, fontsize=12)
        plt.tight_layout()
        plt.savefig(tables_dir / fname, dpi=120, bbox_inches="tight")
        plt.close()

    # Table image: Group A
    if group_a:
        rows = [[f"{r['group']}{r['dp']}", f"{r['accuracy']:.3f}", f"{r['energy_uj']/1e3:.0f}k", f"{r['timing_us']:.0f}", f"{r['area_mm2']:.2f}"] for r in group_a]
        _draw_table(rows, ["DP", "Accuracy", "Energy (kµJ)", "Timing (µs)", "Area (mm²)"], "Group A: EDA PPA", "table_5_2_group_a.png")

    # Table image: Pareto
    pc = [r for r in results if r["accuracy"] >= 0.90][:8]
    rows = [[f"{r['group']}{r['dp']}", _display_group(r), f"{r['accuracy']:.3f}", f"{r['energy_uj']/1e3:.0f}k", f"{r['timing_us']:.0f}"] for r in pc]
    _draw_table(rows, ["DP", "Group", "Accuracy", "Energy (kµJ)", "Timing (µs)"], "Pareto (Acc >= 0.90)", "table_5_5_pareto.png")


def main():
    parser = argparse.ArgumentParser(description="Generate DSE result figures")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input JSON path")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help="Output directory for figures")
    parser.add_argument("--tables-dir", type=Path, default=DEFAULT_TABLES, help="Output directory for tables")
    parser.add_argument("--acc-threshold", type=float, default=0.75, help="Accuracy threshold for feasible (fig 5-9)")
    parser.add_argument("--no-tables", action="store_true", help="Skip table generation")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = load_data(args.input)

    if not args.no_tables:
        gen_tables(results, args.tables_dir)
        print(f"Tables saved to {args.tables_dir}")

    plot_fig_5_1(results, args.output_dir)
    plot_fig_5_2(results, args.output_dir)
    plot_fig_5_3(results, args.output_dir)
    plot_fig_5_4(results, args.output_dir)
    plot_fig_5_5(results, args.output_dir)
    plot_fig_5_6(results, args.output_dir)
    plot_fig_5_7(results, args.output_dir)
    plot_fig_5_8(results, args.output_dir)
    plot_fig_5_9_pareto_3d(results, args.output_dir, acc_threshold=args.acc_threshold)

    print(f"Figures saved to {args.output_dir}")


if __name__ == "__main__":
    main()
