import os
from pathlib import Path
from typing import Dict, Tuple, Iterable

def count_lines_in_folder(folder: str, file_exts: Iterable[str] = None, encoding: str = 'utf-8') -> Tuple[Dict[str, int], int]:
    """Walk `folder` and count lines for files. Returns (per_file_counts, total_lines)."""
    folder_path = Path(folder)
    if not folder_path.exists():
        raise FileNotFoundError(f'Folder not found: {folder}')
    per_file = {}
    total = 0
    exts = None if file_exts is None else set(e.lower() for e in file_exts)
    for root, _, files in os.walk(folder_path):
        for fname in files:
            p = Path(root) / fname
            if exts is not None and p.suffix.lower() not in exts:
                continue
            try:
                with p.open('r', encoding=encoding, errors='replace') as f:
                    count = sum(1 for _ in f)
            except Exception:
                # skip unreadable/binary files
                continue
            per_file[str(p)] = count
            total += count
    return per_file, total