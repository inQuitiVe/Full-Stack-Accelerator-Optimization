#!/bin/sh
#
# run_exp_10_supplemental.sh — 獨立執行 10 個補充實驗（Group G），不影響主實驗輸出
#
# 僅執行 DP 23–32（DP 12 retry + frequency sweep），輸出至 dse_10_supplemental_p1p2p3.json
# 主實驗 dse_22_* / dse_32_* 完全不受影響。
#
# Usage:
#   ./run_exp_10_supplemental.sh   # Path 1 + Path 2 + Path 3 (full validation)
#
# Environment variables (optional):
#   EDA_HOST  — EDA Server IP (default: 132.239.17.21)
#   EDA_PORT  — EDA Server port (default: 5000)
#   SYNTH_MODE — fast | slow (default: fast)
#   OUTPUT    — Output JSON path (default: dse_10_supplemental_p1p2p3.json)
#

set -e

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${WORKSPACE_DIR}"

EDA_HOST="${EDA_HOST:-132.239.17.21}"
EDA_PORT="${EDA_PORT:-5000}"
SYNTH_MODE="${SYNTH_MODE:-fast}"

EXTRA_ARGS="--path2 --path3"

echo "=============================================="
echo "10-Point Supplemental Experiment (Group G)"
echo "  Working directory: ${WORKSPACE_DIR}"
echo "  EDA_HOST=${EDA_HOST} EDA_PORT=${EDA_PORT}"
echo "  SYNTH_MODE=${SYNTH_MODE}"
echo "  Mode: Path 1 + Path 2 + Path 3 (full)"
echo "  Output: dse_10_supplemental_p1p2p3.json"
echo "  (獨立於主實驗，不影響 dse_22/dse_32)"
echo "=============================================="

if [ -n "${OUTPUT}" ]; then
    python3 run_10_supplemental.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}" \
        -o "${OUTPUT}"
else
    python3 run_10_supplemental.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}"
fi

echo ""
echo "Done. Check workspace/ for dse_10_supplemental_p1p2p3.json (10 data points)"
