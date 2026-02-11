import pytest
import numpy as np
import polars as pl

from pymsio.readers.base import META_SCHEMA


def _validate_meta_df(meta_df: pl.DataFrame) -> None:
    """Common assertions for any reader's meta DataFrame."""
    assert isinstance(meta_df, pl.DataFrame)
    assert meta_df.shape[0] > 0, "meta_df should not be empty"

    for col in ("frame_num", "time_in_seconds", "ms_level", "mz_lo", "mz_hi"):
        assert col in meta_df.columns, f"missing column: {col}"

    assert meta_df["frame_num"].is_sorted(), "frame_num should be sorted"
    assert (meta_df["ms_level"] >= 1).all(), "ms_level should be >= 1"


def _validate_peaks(peaks: np.ndarray) -> None:
    """Common assertions for a single frame's peak array."""
    assert isinstance(peaks, np.ndarray)
    assert peaks.dtype == np.float32
    if peaks.size > 0:
        assert peaks.ndim == 2
        assert peaks.shape[1] == 2


def _validate_mass_spec_data(ms_data) -> None:
    """Common assertions for MassSpecData returned by load()."""
    assert ms_data is not None
    assert ms_data.meta_df.shape[0] > 0
    assert ms_data.peak_arr.ndim == 2
    assert ms_data.peak_arr.shape[1] == 2
    assert ms_data.peak_arr.dtype == np.float32


# ---------------------------------------------------------------------------
# MzML reader tests
# ---------------------------------------------------------------------------


class TestMzmlReader:

    def test_get_meta_df(self, mzml_path):
        from pymsio.readers.mzml import MzmlFileReader

        reader = MzmlFileReader(mzml_path)
        meta_df = reader.get_meta_df()
        _validate_meta_df(meta_df)

    def test_get_frame(self, mzml_path):
        from pymsio.readers.mzml import MzmlFileReader

        reader = MzmlFileReader(mzml_path)
        meta_df = reader.get_meta_df()
        first_frame = int(meta_df["frame_num"][0])
        peaks = reader.get_frame(first_frame)
        _validate_peaks(peaks)

    def test_load(self, mzml_path):
        from pymsio.readers.mzml import MzmlFileReader

        reader = MzmlFileReader(mzml_path)
        ms_data = reader.load()
        _validate_mass_spec_data(ms_data)


# ---------------------------------------------------------------------------
# Thermo RAW reader tests
# ---------------------------------------------------------------------------


class TestThermoReader:

    def test_get_meta_df(self, raw_path):
        from pymsio.readers.thermo import ThermoRawReader

        reader = ThermoRawReader(raw_path)
        meta_df = reader.get_meta_df()
        _validate_meta_df(meta_df)
        reader.close()

    def test_get_frame(self, raw_path):
        from pymsio.readers.thermo import ThermoRawReader

        reader = ThermoRawReader(raw_path)
        first_frame = reader.first_scan_number
        peaks = reader.get_frame(first_frame)
        _validate_peaks(peaks)
        reader.close()

    def test_load(self, raw_path):
        from pymsio.readers.thermo import ThermoRawReader

        reader = ThermoRawReader(raw_path)
        ms_data = reader.load()
        _validate_mass_spec_data(ms_data)
        reader.close()
