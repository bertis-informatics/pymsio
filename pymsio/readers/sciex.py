import os
from pathlib import Path
from collections import defaultdict
from typing import Sequence, Union, List, Optional, Dict, NamedTuple

import numpy as np
import polars as pl

from pymsio.readers.base import MassSpecFileReader
from pymsio.readers.ms_data import MassSpecData, PeakArray


class MRMChromatogram(NamedTuple):
    """Single MRM transition chromatogram."""
    compound_name: str
    q1_mz: float
    q3_mz: float
    rt: np.ndarray       # float32, seconds
    intensity: np.ndarray  # float32

ENV_DLL_DIR = "PYMSIO_SCIEX_DLL_DIR"
REQUIRED_DLLS = [
    "Clearcore2.Data.dll",
    "Clearcore2.Data.AnalystDataProvider.dll",
]


def find_sciex_dll_dir() -> Path:
    candidates = []

    env = os.getenv(ENV_DLL_DIR)
    if env:
        candidates.append(Path(env))

    pkg_dir = Path(__file__).resolve().parents[1]
    pkg_path = pkg_dir / "dlls" / "sciex"
    cwd_path = Path.cwd() / "dlls" / "sciex"

    candidates.append(pkg_path)
    candidates.append(cwd_path)

    for d in candidates:
        if d and d.is_dir() and all((d / f).exists() for f in REQUIRED_DLLS):
            return d

    raise FileNotFoundError(
        "SCIEX DLLs not found. Place the DLLs in one of the following locations:\n"
        f"- <set {ENV_DLL_DIR}>\n"
        f"- {pkg_path} (inside the installed pymsio package)\n"
        f"- {cwd_path} (relative to your working directory)\n"
        "Required:\n- " + "\n- ".join(REQUIRED_DLLS)
    )


LOADED_DLL = False
_DLL_LOAD_ERROR: str = ""

try:
    import clr

    clr.AddReference("System")
    import System
    from System.Globalization import CultureInfo
    from System.Threading import Thread

    from pymsio.readers.utils import DotNetArrayToNPArray

    dll_dir = find_sciex_dll_dir()

    # Add dll_dir to the path so dependent DLLs are resolved automatically
    import sys
    if str(dll_dir) not in sys.path:
        sys.path.insert(0, str(dll_dir))

    for filename in REQUIRED_DLLS:
        clr.AddReference(os.path.join(dll_dir, filename))

    from Clearcore2.Data.AnalystDataProvider import (
        AnalystWiffDataProvider,
        AnalystDataProviderFactory,
    )

    LOADED_DLL = True

except Exception as exc:
    _DLL_LOAD_ERROR = f"{type(exc).__name__}: {exc}"


class SciexWiffReader(MassSpecFileReader):
    """Reader for SCIEX WIFF / WIFF2 files via Clearcore2 .NET DLLs (pythonnet).

    Frame numbering is 1-indexed and flattened across experiments and cycles:
        frame_num = cycle_idx * num_experiments + exp_idx + 1

    The companion ``.wiff.scan`` file must reside in the same directory as
    the ``.wiff`` file; the Clearcore2 library locates it automatically.

    Notes
    -----
    The SCIEX Clearcore2 library requires **write access** to the directory
    that contains the WIFF file even for read-only operations.
    """

    thread_safe = False

    def __init__(
        self,
        filepath: Union[str, Path],
        num_workers: int = 0,
        sample_index: int = 0,
    ):
        if not LOADED_DLL:
            raise RuntimeError(f"Failed to load SCIEX DLLs: {_DLL_LOAD_ERROR}")

        super().__init__(filepath, num_workers)

        scan_file = self.file_path.with_suffix(".wiff.scan")
        if not scan_file.exists():
            raise FileNotFoundError(
                f".wiff.scan file not found: {scan_file}\n"
                "Both the .wiff and .wiff.scan files must be in the same directory."
            )

        # Fix locale so that Clearcore2 parses decimal numbers correctly
        en_us = CultureInfo("en-US")
        Thread.CurrentThread.CurrentCulture = en_us
        Thread.CurrentThread.CurrentUICulture = en_us

        try:
            self._provider = AnalystWiffDataProvider()
            self._batch = AnalystDataProviderFactory.CreateBatch(
                str(self.file_path), self._provider
            )
        except System.UnauthorizedAccessException:
            raise PermissionError(
                f"SCIEX library requires write access to the directory containing "
                f"the WIFF file: {self.file_path.parent}"
            )

        self._sample = self._batch.GetSample(sample_index)
        self._ms_sample = self._sample.MassSpectrometerSample

        num_exp = self._ms_sample.ExperimentCount
        self._experiments = [
            self._ms_sample.GetMSExperiment(i) for i in range(num_exp)
        ]
        self._num_experiments: int = num_exp
        self._num_cycles: int = self._experiments[0].Details.NumberOfScans

        self._meta_df: Optional[pl.DataFrame] = None

    # ------------------------------------------------------------------
    # Resource management
    # ------------------------------------------------------------------

    def close(self):
        if hasattr(self, "_experiments"):
            for exp in self._experiments:
                try:
                    exp.Dispose()
                except Exception:
                    pass
            self._experiments = []
        if hasattr(self, "_sample") and self._sample is not None:
            try:
                self._sample.Dispose()
            except Exception:
                pass
            self._sample = None
        if hasattr(self, "_provider") and self._provider is not None:
            self._provider.Close()
            self._provider = None
        System.GC.Collect()
        System.GC.WaitForPendingFinalizers()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def num_frames(self) -> int:
        return self._num_cycles * self._num_experiments

    @property
    def num_spectra(self) -> int:
        return self.num_frames

    @property
    def first_scan_number(self) -> int:
        return 1

    @property
    def last_scan_number(self) -> int:
        return self.num_frames

    @property
    def acquisition_date(self) -> str:
        return self._sample.Details.AcquisitionDateTime.ToString("O")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _frame_to_exp_cycle(self, frame_num: int):
        """Convert 1-indexed frame number to (exp_idx, cycle_idx)."""
        idx = frame_num - 1
        exp_idx = idx % self._num_experiments
        cycle_idx = idx // self._num_experiments
        return exp_idx, cycle_idx

    def _read_peaks_arrays(self, frame_num: int) -> PeakArray:
        exp_idx, cycle_idx = self._frame_to_exp_cycle(frame_num)
        exp = self._experiments[exp_idx]
        spectrum = exp.GetMassSpectrum(cycle_idx)

        if spectrum.NumDataPoints == 0:
            return PeakArray.empty()

        mz_arr = DotNetArrayToNPArray(spectrum.GetActualXValues(), dtype=np.float32)
        inten_arr = DotNetArrayToNPArray(spectrum.GetActualYValues(), dtype=np.float32)

        if len(mz_arr) == 0:
            return PeakArray.empty()

        mask = inten_arr > 0
        n_valid = np.count_nonzero(mask)

        if n_valid == 0:
            return PeakArray.empty()
        if n_valid == len(mz_arr):
            return PeakArray(mz_arr, inten_arr)

        idx = np.flatnonzero(mask)
        return PeakArray(mz_arr[idx], inten_arr[idx])

    def _get_isolation(self, exp_idx: int, cycle_idx: int):
        """Return (isolation_min_mz, isolation_max_mz) for an MS2 scan.

        Returns (None, None) when no precursor is available (e.g. IDA empty
        product scan where the survey did not select a precursor).
        """
        exp = self._experiments[exp_idx]
        details = exp.Details
        info = exp.GetMassSpectrumInfo(cycle_idx)

        # ParentMZ is cycle-dependent (works for both IDA and SWATH)
        center_mz = float(info.ParentMZ)
        if center_mz <= 0:
            # No precursor selected for this cycle (IDA empty scan)
            return None, None

        iso_width = 0.0
        mri = details.MassRangeInfo
        if mri.Length > 0:
            iso_width = float(mri[0].IsolationWindow)

        if iso_width <= 0:
            iso_width = 3.0  # fallback

        return center_mz - iso_width / 2.0, center_mz + iso_width / 2.0

    def _read_scan_meta(self, frame_num: int, cols: Dict[str, list]) -> None:
        exp_idx, cycle_idx = self._frame_to_exp_cycle(frame_num)
        exp = self._experiments[exp_idx]
        details = exp.Details
        info = exp.GetMassSpectrumInfo(cycle_idx)

        rt = float(exp.GetRTFromExperimentCycle(cycle_idx)) * 60.0  # min → sec
        ms_level = int(info.MSLevel)

        if ms_level == 1:
            isolation_min_mz = None
            isolation_max_mz = None
        else:
            isolation_min_mz, isolation_max_mz = self._get_isolation(
                exp_idx, cycle_idx
            )

        cols["frame_num"].append(frame_num)
        cols["time_in_seconds"].append(rt)
        cols["ms_level"].append(ms_level)
        cols["isolation_min_mz"].append(isolation_min_mz)
        cols["isolation_max_mz"].append(isolation_max_mz)
        try:
            mz_lo = float(details.StartMass)
            mz_hi = float(details.StopMass)
        except Exception:
            # StartMass/StopMass are only valid for full scan experiments (e.g. not MRM)
            mz_lo = None
            mz_hi = None
        cols["mz_lo"].append(mz_lo)
        cols["mz_hi"].append(mz_hi)

    def _build_meta_df(self, cols: Dict[str, list]) -> pl.DataFrame:
        meta_df = pl.DataFrame(cols, schema=self.meta_schema, nan_to_null=True)
        self._meta_df = meta_df
        return meta_df

    # ------------------------------------------------------------------
    # Public API (MassSpecFileReader interface)
    # ------------------------------------------------------------------

    def get_meta_df(self) -> pl.DataFrame:
        if self._meta_df is not None:
            return self._meta_df

        cols: Dict[str, list] = defaultdict(list)
        for frame_num in self._progress(
            range(self.first_scan_number, self.last_scan_number + 1),
            desc="read meta",
        ):
            self._read_scan_meta(frame_num, cols)

        return self._build_meta_df(cols)

    def get_frame(self, frame_num: int) -> PeakArray:
        return self._read_peaks_arrays(frame_num)

    def get_frames(self, frame_nums: Sequence[int]) -> List[PeakArray]:
        return [
            self.get_frame(int(fn))
            for fn in self._progress(frame_nums, desc="load spectra")
        ]

    def load(self, progress=None) -> MassSpecData:
        scan_range = range(self.first_scan_number, self.last_scan_number + 1)
        need_meta = self._meta_df is None

        cols: Dict[str, list] = defaultdict(list) if need_meta else {}
        all_spectra: List[PeakArray] = []

        for fn in self._progress(scan_range, progress=progress, desc="load spectra"):
            if need_meta:
                self._read_scan_meta(fn, cols)
            all_spectra.append(self._read_peaks_arrays(fn))

        if need_meta:
            self._build_meta_df(cols)

        return MassSpecData.create(self.run_name, self._meta_df, all_spectra)

    @property
    def experiment_type(self) -> str:
        return str(self._experiments[0].Details.ExperimentType)


class SciexMRMReader(SciexWiffReader):
    """Reader for SCIEX MRM WIFF files.

    Each experiment corresponds to one MRM transition (Q1 → Q3).
    Use ``get_mrm_chromatograms()`` to retrieve all transition chromatograms.
    ``get_frame()`` and ``load()`` are not applicable for MRM data.
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        num_workers: int = 0,
        sample_index: int = 0,
    ):
        super().__init__(filepath, num_workers, sample_index)

        exp_type = self.experiment_type
        if "MRM" not in exp_type.upper():
            raise ValueError(
                f"Expected MRM experiment type, got: {exp_type}. "
                "Use SciexWiffReader for DDA/DIA files."
            )

    # ------------------------------------------------------------------
    # MRM-specific API
    # ------------------------------------------------------------------

    def get_mrm_chromatograms(self) -> List[MRMChromatogram]:
        """Return one MRMChromatogram per transition.

        In SCIEX MRM WIFF files, all transitions are stored in a single
        experiment. ``GetMassSpectrum(cycle)`` returns pseudo-mz values
        (0, 1, 2, ...) as transition indices and the corresponding
        intensities. Transition metadata (name, Q1, Q3) is in
        ``Details.MassRangeInfo``.

        Returns
        -------
        List[MRMChromatogram]
            Each entry contains compound_name, q1_mz, q3_mz,
            rt (float32, seconds), intensity (float32).
        """
        exp = self._experiments[0]
        det = exp.Details
        mri = det.MassRangeInfo
        n_transitions = mri.Length
        n_cycles = det.NumberOfScans

        # RT array (seconds)
        rt_arr = np.array(
            [float(exp.GetRTFromExperimentCycle(j)) * 60.0 for j in range(n_cycles)],
            dtype=np.float32,
        )

        # intensity matrix: shape (n_cycles, n_transitions)
        int_matrix = np.zeros((n_cycles, n_transitions), dtype=np.float32)
        for j in self._progress(range(n_cycles), desc="load MRM chromatograms"):
            spectrum = exp.GetMassSpectrum(j)
            int_j = DotNetArrayToNPArray(spectrum.GetActualYValues(), dtype=np.float32)
            if len(int_j) == n_transitions:
                int_matrix[j] = int_j

        # Build one MRMChromatogram per transition
        return [
            MRMChromatogram(
                compound_name=str(mri[i].Name),
                q1_mz=float(mri[i].Q1Mass),
                q3_mz=float(mri[i].Q3Mass),
                rt=rt_arr,
                intensity=int_matrix[:, i].copy(),
            )
            for i in range(n_transitions)
        ]

    # ------------------------------------------------------------------
    # Disable spectrum-based methods
    # ------------------------------------------------------------------

    def get_frame(self, _frame_num: int) -> PeakArray:
        raise NotImplementedError(
            "get_frame() is not available for MRM data. "
            "Use get_mrm_chromatograms() instead."
        )

    def get_frames(self, _frame_nums: Sequence[int]) -> List[PeakArray]:
        raise NotImplementedError(
            "get_frames() is not available for MRM data. "
            "Use get_mrm_chromatograms() instead."
        )

    def load(self, _progress=None) -> MassSpecData:
        raise NotImplementedError(
            "load() is not available for MRM data. "
            "Use get_mrm_chromatograms() instead."
        )
