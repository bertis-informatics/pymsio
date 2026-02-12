from typing import Union, List, Sequence
from pathlib import Path

import math
import h5py

import polars as pl
import numpy as np
import numba as nb


META_SCHEMA = {
    "frame_num": pl.UInt32,
    "mz_lo": pl.Float32,
    "mz_hi": pl.Float32,
    "time_in_seconds": pl.Float32,
    "ms_level": pl.UInt8,
    "isolation_min_mz": pl.Float32,
    "isolation_max_mz": pl.Float32,
}


def get_frame_num_to_index_arr(frame_nums: List[int]):
    num_to_idx = np.zeros(frame_nums[-1] + 1, dtype=np.uint32)
    num_to_idx[frame_nums] = np.arange(len(frame_nums), dtype=np.uint32)
    return num_to_idx


@nb.njit(cache=True, fastmath=True)
def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


@nb.njit(parallel=True, fastmath=True, cache=True)
def compute_z_score_cdf_numba(
    peak_arr: np.ndarray, peak_range_arr: np.ndarray
) -> np.ndarray:
    """
    peak_arr: shape (N, 2) where peak_arr[:,1] is intensity (float32/float64)
    peak_range_arr: shape (M, 2) [start, end) integer
    returns: float32 array of length N in [0,1] (robust z -> normal CDF)
    """
    n = peak_arr.shape[0]
    out = np.empty(n, dtype=np.float32)

    for i in range(n):
        out[i] = 0.5

    for i in nb.prange(peak_range_arr.shape[0]):
        st = int(peak_range_arr[i, 0])
        ed = int(peak_range_arr[i, 1])
        if ed > st:
            ab = peak_arr[st:ed, 1]  # view
            # Numba(>=0.47)
            q1, q2, q3 = np.quantile(ab, np.array([0.25, 0.5, 0.75]))
            iqr = q3 - q1
            if iqr > 0.0:
                inv = 1.0 / iqr
                for j in range(st, ed):
                    z = (peak_arr[j, 1] - q2) * inv
                    out[j] = _norm_cdf(z)

    return out


class MassSpecData:

    thread_safe = False

    def __init__(self, run_name: str, meta_df: pl.DataFrame, peak_arr: np.ndarray):

        self.run_name = run_name
        self.frame_num_to_index = get_frame_num_to_index_arr(meta_df["frame_num"])
        self.meta_df = meta_df
        self.peak_arr = peak_arr
        self.z_score_arr = None

    @classmethod
    def create(
        cls, run_name: str, meta_df: pl.DataFrame, list_of_peaks: List[np.ndarray]
    ):

        assert meta_df.shape[0] == len(list_of_peaks)

        meta_df = (
            meta_df.with_columns(
                peak_count=np.asarray(
                    [peaks.shape[0] for peaks in list_of_peaks], dtype=np.uint32
                )
            )
            .with_columns(pl.col("peak_count").cum_sum().alias("peak_stop"))
            .with_columns(pl.col("peak_stop").shift(1).fill_null(0).alias("peak_start"))
            .select(pl.col(list(META_SCHEMA)), pl.col("peak_start", "peak_stop"))
        )
        peak_arr = np.concatenate(list_of_peaks, axis=0)

        return cls(run_name, meta_df, peak_arr)

    def compute_z_score(self):
        if self.z_score_arr is None:
            peak_range_arr = self.meta_df.select(
                pl.col("peak_start", "peak_stop")
            ).to_numpy()
            self.z_score_arr = compute_z_score_cdf_numba(self.peak_arr, peak_range_arr)

    def get_peak_index(self, frame_num: int):
        idx = self.frame_num_to_index[frame_num]
        st = self.meta_df.item(idx, "peak_start")
        ed = self.meta_df.item(idx, "peak_stop")
        return st, ed

    def get_peaks(self, frame_num: int):
        st, ed = self.get_peak_index(frame_num)
        return self.peak_arr[st:ed]

    def get_all_peak_df(self):
        frame_num_arr = np.empty(self.peak_arr.shape[0], dtype=np.uint32)
        for fn, st, ed in self.meta_df.select(
            pl.col("frame_num", "peak_start", "peak_stop")
        ).iter_rows():
            frame_num_arr[st:ed] = fn

        peak_df = pl.DataFrame(
            {
                "frame_num": frame_num_arr,
                "mz": self.peak_arr[:, 0],
                "ab": self.peak_arr[:, 1],
            }
        )
        return peak_df

    def collect_peaks(self, frame_nums: Sequence[int]):

        peak_idx_df = self.meta_df[self.frame_num_to_index[frame_nums]].select(
            pl.col("frame_num", "peak_start", "peak_stop")
        )

        num_peaks = peak_idx_df.select(
            (pl.col("peak_stop") - pl.col("peak_start")).alias("num_peaks")
        )["num_peaks"].sum()

        frame_num_arr = np.empty(num_peaks, dtype=np.uint32)
        mz_arr = np.empty(num_peaks, dtype=np.float32)
        ab_arr = np.empty(num_peaks, dtype=np.float32)
        z_arr = (
            None if self.z_score_arr is None else np.empty(num_peaks, dtype=np.float32)
        )

        st = 0
        for frame_index, (frame_num, peak_st, peak_ed) in enumerate(
            peak_idx_df.iter_rows()
        ):
            peaks = self.peak_arr[peak_st:peak_ed, :]
            ed = st + peaks.shape[0]
            if peaks.shape[0] > 0:
                frame_num_arr[st:ed] = frame_num
                mz_arr[st:ed] = peaks[:, 0]
                ab_arr[st:ed] = peaks[:, 1]
                if self.z_score_arr is not None:
                    z_arr[st:ed] = self.z_score_arr[peak_st:peak_ed]
            st = ed

        return frame_num_arr, mz_arr, ab_arr, z_arr

    def write_hdf(
        self,
        file_path: Union[str, Path],
        overwrite: bool = False,
    ):
        file_path = Path(file_path)
        group_key = self.run_name

        with h5py.File(file_path, "a") as hf:
            if group_key in hf:
                if overwrite:
                    del hf[group_key]
                else:
                    raise FileExistsError("LC/MS data already exists")
            hf_grp = hf.create_group(group_key)
            _ = hf_grp.create_dataset("peak", data=self.peak_arr, dtype=np.float32)

        self.meta_df.to_pandas().to_hdf(
            file_path, key=f"{group_key}/meta_df", index=False
        )
