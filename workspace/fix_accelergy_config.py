import shutil
from pathlib import Path

CONFIG_PATH = Path("/root/.config/accelergy/accelergy_config.yaml")

def fix_duplicate_blocks(path: Path):
    if not path.exists():
        print("Config file not found.")
        return

    text = path.read_text()

    # Split blocks by version header
    parts = text.split("version:")

    if len(parts) <= 2:
        print("No duplicate blocks found.")
        return

    print("Duplicate config detected. Fixing...")

    # reconstruct file with only first block
    cleaned = "version:" + parts[1]

    # backup original
    backup_path = path.with_suffix(".yaml.bak")
    shutil.copy(path, backup_path)
    print(f"Backup saved to {backup_path}")

    path.write_text(cleaned)
    print("Config cleaned successfully.")

if __name__ == "__main__":
    fix_duplicate_blocks(CONFIG_PATH)