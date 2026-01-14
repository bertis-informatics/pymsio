from pathlib import Path
import argparse

from pymsio.readers import ReaderFactory 

def main():
    parser = argparse.ArgumentParser(
        description="Simple MS reader demo (meta_df & peaks)"
    )
    parser.add_argument("raw_path", type=str, help="Path to .raw / .mzML / ... file")
    args = parser.parse_args()

    raw_path = Path(args.raw_path)

    reader = ReaderFactory.get_reader(raw_path)

    meta_df = reader.get_meta_df()                # polars DataFrame   

    print("=== meta_df ===")
    print(meta_df.head())

    # peak_arr = reader.get_frames(list(range(meta_df["frame_num"].min(), meta_df["frame_num"].max()+1)))            # numpy ndarray (N x 2 or N x ?)
    # # peak_arr = reader.get_frames(frame_nums=[1,3,10])  

    # print("\n=== peaks ===")
    # print("peak_arr[0] shape:", peak_arr[0].shape)
    # print("col 0=m/z\t1=intensity")
    # print(peak_arr[0])

    # peak_arr_1 = reader.get_frame(frame_num=1)
    
    msdata = reader.load()
    print(msdata.peak_arr.shape)


if __name__ == "__main__":
    main()