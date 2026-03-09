#!/bin/sh
#
# run_exp_5_aggressive.sh — 獨立執行 5 個激進頻率實驗（200–300 MHz）
#
# 使用 small arch 測試 200/225/250/275/300 MHz，輸出至 dse_5_aggressive_p1p2p3.json
# 主實驗及 10 點補充實驗完全不受影響。
#
# Usage:
#   ./run_exp_5_aggressive.sh   # Path 1 + Path 2 + Path 3 (full validation)
#
# Environment variables (optional):
#   EDA_HOST  — EDA Server IP (default: 132.239.17.21)
#   EDA_PORT  — EDA Server port (default: 5000)
#   SYNTH_MODE — fast | slow (default: fast)
#   OUTPUT    — Output JSON path (default: dse_5_aggressive_p1p2p3.json)
#

set -e

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${WORKSPACE_DIR}"

EDA_HOST="${EDA_HOST:-132.239.17.21}"
EDA_PORT="${EDA_PORT:-5000}"
SYNTH_MODE="${SYNTH_MODE:-fast}"

EXTRA_ARGS="--path2 --path3"

echo "=============================================="
echo "5-Point Aggressive Frequency (200–300 MHz)"
echo "  Working directory: ${WORKSPACE_DIR}"
echo "  EDA_HOST=${EDA_HOST} EDA_PORT=${EDA_PORT}"
echo "  SYNTH_MODE=${SYNTH_MODE}"
echo "  Mode: Path 1 + Path 2 + Path 3 (full)"
echo "  Output: dse_5_aggressive_p1p2p3.json"
echo "  (base arch @ 200/225/250/275/300 MHz)"
echo "=============================================="

if [ -n "${OUTPUT}" ]; then
    python3 run_5_aggressive_freq.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}" \
        -o "${OUTPUT}"
else
    python3 run_5_aggressive_freq.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}"
fi

echo ""
echo "Done. Check workspace/ for dse_5_aggressive_p1p2p3.json (5 data points)"
