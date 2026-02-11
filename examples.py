"""
Example usage of pymsio readers.

Usage:
    python examples.py path/to/your/file.raw   # or .mzML
"""

from pathlib import Path
from pymsio.readers import ReaderFactory


def main(file_path: str):
    path = Path(file_path)

    # 1) Get appropriate reader (Thermo RAW or mzML)
    reader = ReaderFactory.get_reader(path)

    # 2) Read metadata (Polars DataFrame)
    meta_df = reader.get_meta_df()
    print("=== Metadata ===")
    print(meta_df.head())
    print()

    # 3) Read one frame (np.ndarray, shape (N, 2), columns: [mz, intensity])
    frame_num = int(meta_df.item(0, "frame_num"))
    peaks = reader.get_frame(frame_num)
    print(f"=== Frame {frame_num} ===")
    print(f"  shape: {peaks.shape}")
    print()

    # 4) Load full dataset
    msdata = reader.load()
    print("=== Full Dataset ===")
    print(f"  peak_arr shape: {msdata.peak_arr.shape}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    main(sys.argv[1])
