from pathlib import Path
from pymsio.readers import ReaderFactory 

path = Path("/home/ympark/pymsio_dev/tests/BD20190920_PTRC_TNBCCarboDoc_EB_Proteome_Plex1_F1.mzML.gz")   # or .mzML

# 1) Get appropriate reader
reader = ReaderFactory.get_reader(path)

# 2) Read metadata (Polars DataFrame)
meta_df = reader.get_meta_df()
print(meta_df.head())

# 3) Read one frame (np.ndarray, shape (N, 2), [mz, intensity])
frame_num = int(meta_df.item(0, "frame_num"))
peaks = reader.get_frame(frame_num)
print(peaks.shape)

# 4) Load full dataset 
msdata = reader.load()
print(msdata.peak_arr.shape)

# Read multiple frames
frame_nums = meta_df["frame_num"].to_list() # or List[] which has frame numbers
peak_arr = reader.get_frames(frame_nums)
print(len(peak_arr), peak_arr[0].shape)
