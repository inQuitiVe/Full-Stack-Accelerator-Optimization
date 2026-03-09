#!/bin/sh
#
# run_merged.sh — 整合實驗 runner（36 點：run_15 + run_10 + run_5 去重）
#
# 合併 EDA、ARCH、INNER、ARCH_EXT、FREQ 群組，輸出至 dse_merged_p1p2p3.json
#
# Usage:
#   ./run_merged.sh   # Path 1 + Path 2 + Path 3 (full validation, default)
#
# Environment variables (optional):
#   EDA_HOST   — EDA Server IP (default: 132.239.17.21)
#   EDA_PORT   — EDA Server port (default: 5000)
#   SYNTH_MODE — fast | slow (default: fast)
#   OUTPUT     — Output JSON path (default: dse_merged_p1p2p3.json)
#

set -e

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${WORKSPACE_DIR}"

EDA_HOST="${EDA_HOST:-132.239.17.21}"
EDA_PORT="${EDA_PORT:-5000}"
SYNTH_MODE="${SYNTH_MODE:-fast}"

EXTRA_ARGS="--path2 --path3"

echo "=============================================="
echo "Merged Experiment (36 points, deduplicated)"
echo "  Working directory: ${WORKSPACE_DIR}"
echo "  EDA_HOST=${EDA_HOST} EDA_PORT=${EDA_PORT}"
echo "  SYNTH_MODE=${SYNTH_MODE}"
echo "  Mode: Path 1 + Path 2 + Path 3 (full)"
echo "  Output: dse_merged_p1p2p3.json"
echo "  Groups: EDA(5) ARCH(5) INNER(13) ARCH_EXT(9) FREQ(4)"
echo "=============================================="

if [ -n "${OUTPUT}" ]; then
    python3 run_merged_experiments.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}" \
        -o "${OUTPUT}"
else
    python3 run_merged_experiments.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}"
fi

echo ""
echo "Done. Check workspace/ for dse_merged_p1p2p3.json (36 data points)"
