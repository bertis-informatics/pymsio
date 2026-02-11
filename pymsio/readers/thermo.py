import os
from tqdm import trange
from pathlib import Path

import numpy as np
import numba as nb
import polars as pl
from pathlib import Path
from typing import Sequence, Union, List, Iterator, Optional, Dict, Any

from pymsio.readers.base import MassSpecFileReader, MassSpecData

ENV_DLL_DIR = "PYMSIO_THERMO_DLL_DIR"
REQUIRED_DLLS = [
    "ThermoFisher.CommonCore.Data.dll",
    "ThermoFisher.CommonCore.RawFileReader.dll",
]

def find_thermo_dll_dir() -> Path:
    candidates = []

    env = os.getenv(ENV_DLL_DIR)
    if env:
        candidates.append(Path(env))

    pkg_dir = Path(__file__).resolve().parents[1]
    pkg_path = pkg_dir / "dlls" / "thermo_fisher"
    cwd_path = Path.cwd() / "dlls" / "thermo_fisher"

    candidates.append(pkg_path)
    candidates.append(cwd_path)

    for d in candidates:
        if d and d.is_dir() and all((d / f).exists() for f in REQUIRED_DLLS):
            return d

    raise FileNotFoundError(
        "Thermo DLLs not found. Place the DLLs in one of the following locations:\n"
        f"- <set {ENV_DLL_DIR}>\n"
        f"- {pkg_path} (inside the installed pymsio package)\n"
        f"- {cwd_path} (relative to your working directory)\n"
        "Required:\n- " + "\n- ".join(REQUIRED_DLLS)
    )


try:
    import clr

    clr.AddReference("System")
    import System

    from pymsio.utils.util import DotNetArrayToNPArray

    dll_dir = find_thermo_dll_dir()

    for filename in REQUIRED_DLLS:
        clr.AddReference(os.path.join(dll_dir, filename))

    import ThermoFisher
    from ThermoFisher.CommonCore.RawFileReader import RawFileReaderAdapter
    from ThermoFisher.CommonCore.Data.Interfaces import IScanEvent, IScanEventBase

    LOADED_DLL = True
except Exception:
    LOADED_DLL = False


class ThermoRawReader(MassSpecFileReader):
    thread_safe = False

    def __init__(
        self,
        filepath: Union[str, Path],
        num_workers: int = 0,
        centroided: bool = True,
    ):
        if not LOADED_DLL:
            raise ValueError("ERROR DLL import")

        super().__init__(filepath, num_workers)

        self._meta_schema = {
            "frame_num": pl.UInt32,
            "time_in_seconds": pl.Float32,
            "ms_level": pl.UInt8,
            "isolation_min_mz": pl.Float32,
            "isolation_max_mz": pl.Float32,
            "mz_lo": pl.Float32,
            "mz_hi": pl.Float32,
        }

        self.centroided = centroided

        self.filepath = str(filepath)
        self._raw = RawFileReaderAdapter.FileFactory(self.filepath)
        self._raw.SelectInstrument(ThermoFisher.CommonCore.Data.Business.Device.MS, 1)

        self._meta_df: Optional[pl.DataFrame] = None

    def close(self):
        if self._raw is not None:
            self._raw.Dispose()
            self._raw = None

    @property
    def acquisition_date(self) -> str:
        return self._raw.CreationDate.ToString("o")

    @property
    def num_frames(self) -> int:
        return (
            self._raw.RunHeaderEx.LastSpectrum - self._raw.RunHeaderEx.FirstSpectrum + 1
        )

    @property
    def first_scan_number(self) -> int:
        return self._raw.RunHeaderEx.FirstSpectrum

    @property
    def last_scan_number(self) -> int:
        return self._raw.RunHeaderEx.LastSpectrum

    @property
    def instrument(self) -> str:
        return System.String.Join(
            " -> ", self._raw.GetAllInstrumentNamesFromInstrumentMethod()
        )

    def _read_peaks_arrays(
        self, frame_num: int, prefer_centroid: Optional[bool] = None
    ):
        if prefer_centroid is None:
            prefer_centroid = self.centroided 

        is_centroid = self._raw.IsCentroidScanFromScanNumber(frame_num)

        if (not is_centroid) and prefer_centroid:
            # Scan is profile, but user wanted centroid
            data = self._raw.GetSimplifiedCentroids(frame_num)  # ISimpleScanAccess
        else:
            # return data as-is
            data = self._raw.GetSimplifiedScan(frame_num)  # ISimpleScanAccess

        mz_arr = DotNetArrayToNPArray(data.Masses)
        inten_arr = DotNetArrayToNPArray(data.Intensities)

        if mz_arr is None or len(mz_arr) == 0:
            return np.empty((0, 2), dtype=np.float32)
        
        mask = inten_arr > 0

        if not np.all(mask):
            mz_arr = mz_arr[mask]
            inten_arr = inten_arr[mask]

        result = np.empty((len(mz_arr), 2), dtype=np.float32)

        result[:, 0] = mz_arr
        result[:, 1] = inten_arr

        return result

    def get_meta_df(self) -> pl.DataFrame:
        if self._meta_df is not None:
            return self._meta_df

        min_frame = self.first_scan_number
        max_frame = self.last_scan_number

        rows: List[Dict[str, Any]] = []

        for frame_num in trange(min_frame, max_frame + 1, desc="Reading Thermo meta"):
            scan_stats = self._raw.GetScanStatsForScanNumber(frame_num)
            scan_event = IScanEventBase(self._raw.GetScanEventForScanNumber(frame_num))

            try:
                rt = float(scan_stats.StartTime)  # minutes
            except AttributeError:
                rt = float(self._raw.RetentionTimeFromScanNumber(frame_num))

            ms_level = int(scan_event.MSOrder)

            if ms_level == 1:
                isolation_min_mz = None
                isolation_max_mz = None
            else:
                reaction = scan_event.GetReaction(0)
                if reaction.PrecursorRangeIsValid:
                    isolation_min_mz = reaction.FirstPrecursorMass
                    isolation_max_mz = reaction.LastPrecursorMass
                else:
                    isolation_center = float(reaction.PrecursorMass)
                    isolation_width  = float(reaction.IsolationWidth)
                    isolation_min_mz = isolation_center - isolation_width / 2.0
                    isolation_max_mz = isolation_min_mz + isolation_width / 2.0

            mz_lo = float(scan_stats.LowMass)
            mz_hi = float(scan_stats.HighMass)

            rows.append(
                {
                    "frame_num": frame_num,
                    "time_in_seconds": rt * 60,
                    "ms_level": ms_level,
                    "isolation_min_mz": isolation_min_mz,
                    "isolation_max_mz": isolation_max_mz,
                    "mz_lo": mz_lo,
                    "mz_hi": mz_hi,
                }
            )

        meta_df = pl.DataFrame(
            rows,
            schema=self._meta_schema,
            nan_to_null=True, 
        )

        self._meta_df = meta_df
        return meta_df

    def get_frame(self, frame_num: int) -> np.ndarray:
        return self._read_peaks_arrays(frame_num)

    def get_frames(self, frame_nums: Sequence[int]) -> List[np.ndarray]:
        return list(self.iter_frames(frame_nums, desc="Reading Thermo frames"))

    def iter_frames(
        self, frame_nums: Sequence[int], desc: str = "Reading Thermo frames"
    ) -> Iterator[np.ndarray]:
        frame_nums = np.asarray(frame_nums, dtype=np.int32)

        for i in trange(len(frame_nums), desc=desc):
            fn = int(frame_nums[i])
            yield self.get_frame(fn)

    def load(self) -> MassSpecData:
        meta_df = self.get_meta_df()

        min_frame = int(meta_df["frame_num"].min())
        max_frame = int(meta_df["frame_num"].max())

        batch_size = 1024 * 10
        batch_ranges = [
            (start, min(start + batch_size - 1, max_frame))
            for start in range(min_frame, max_frame + 1, batch_size)
        ]

        all_spectra: List[np.ndarray] = []

        for frame_num in trange(min_frame, max_frame + 1, desc="load spectra"):
            peaks = self.get_frame(frame_num)
            all_spectra.append(peaks)

        return MassSpecData.create(self.run_name, meta_df, all_spectra)
