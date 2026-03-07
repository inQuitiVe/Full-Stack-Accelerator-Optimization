#!/bin/sh
#
# run_exp.sh — 22-point experiment runner for Path 2/Path 3 validation
#
# Usage:
#   ./run_exp.sh   # Path 1 + Path 2 + Path 3 (full validation, default)
#
# Environment variables (optional):
#   EDA_HOST  — EDA Server IP (default: 132.239.17.21)
#   EDA_PORT  — EDA Server port (default: 5000)
#   SYNTH_MODE — fast | slow (default: fast)
#   OUTPUT    — Output JSON path (default: auto by mode, e.g. dse_22_p1p2p3.json)
#

set -e

WORKSPACE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${WORKSPACE_DIR}"

EDA_HOST="${EDA_HOST:-132.239.17.21}"
EDA_PORT="${EDA_PORT:-5000}"
SYNTH_MODE="${SYNTH_MODE:-fast}"

# Force Path 2 + Path 3 (full validation)
EXTRA_ARGS="--path2 --path3"

echo "=============================================="
echo "22-Point Differentiated Experiment"
echo "  Working directory: ${WORKSPACE_DIR}"
echo "  EDA_HOST=${EDA_HOST} EDA_PORT=${EDA_PORT}"
echo "  SYNTH_MODE=${SYNTH_MODE}"
echo "  Mode: Path 1 + Path 2 + Path 3 (full)"
echo "  Output: dse_22_p1p2p3.json"
echo "=============================================="

if [ -n "${OUTPUT}" ]; then
    python3 run_15_experiments.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}" \
        -o "${OUTPUT}"
else
    python3 run_15_experiments.py \
        ${EXTRA_ARGS} \
        --eda-host "${EDA_HOST}" \
        --eda-port "${EDA_PORT}" \
        --synth-mode "${SYNTH_MODE}"
fi

echo ""
echo "Done. Check workspace/ for dse_22_p1p2p3.json (22 data points)"
