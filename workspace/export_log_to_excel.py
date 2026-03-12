#!/usr/bin/env python3
"""Export experiment log analysis to Excel (.xlsx)."""
import csv
import sys
from pathlib import Path

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

CSV_PATH = Path(__file__).parent / "experiment_log_analysis.csv"
XLSX_PATH = Path(__file__).parent / "experiment_log_analysis.xlsx"


def main():
    if not HAS_PANDAS:
        print("pandas not installed. Install with: pip install pandas openpyxl")
        print(f"CSV available at: {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    df.to_excel(XLSX_PATH, index=False, sheet_name="Experiment Log")
    print(f"Excel saved to: {XLSX_PATH}")


if __name__ == "__main__":
    main()
