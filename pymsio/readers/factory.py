from pathlib import Path
from typing import Union

from .base import MassSpecFileReader
from .thermo import ThermoRawReader
from .mzml import MzmlFileReader
from .sciex import SciexWiffReader, SciexMRMReader


class ReaderFactory:
    supported_file_extensions = [".raw", ".mzml", ".mzml.gz", ".wiff", ".wiff2"]

    @classmethod
    def _normalize_ext(cls, path: Path) -> str:
        name = path.name.lower()
        if name.endswith(".mzml.gz"):
            return ".mzml.gz"
        return path.suffix.lower()

    @classmethod
    def get_reader(
        cls,
        filepath: Union[str, Path],
    ) -> MassSpecFileReader:
        if isinstance(filepath, str):
            filepath = Path(filepath)

        ext = cls._normalize_ext(filepath)

        if ext not in cls.supported_file_extensions:
            raise ValueError(
                f"Unsupported file type: {ext}. "
                f"Supported: {', '.join(cls.supported_file_extensions)}"
            )

        if ext == ".raw":
            reader = ThermoRawReader(filepath)
        elif ext in (".mzml", ".mzml.gz"):
            reader = MzmlFileReader(filepath)
        elif ext in (".wiff", ".wiff2"):
            # Open once, then promote to SciexMRMReader in-place if MRM
            reader = SciexWiffReader(filepath)
            if "MRM" in reader.experiment_type.upper():
                reader.__class__ = SciexMRMReader
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        return reader
