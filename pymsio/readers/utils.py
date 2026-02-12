import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import clr

    clr.AddReference("System")

    import ctypes

    from System.Runtime.InteropServices import GCHandle, GCHandleType
except Exception as e:
    logger.exception(
        "pythonnet/.NET runtime import failed. "
        f"Optional dependency unavailable: pythonnet/.NET import failed ({type(e).__name__}: {e}). "
        "Thermo RAW reader functionality will be disabled."
    )


def DotNetArrayToNPArray(src, dtype=np.float64):
    """
    See https://mail.python.org/pipermail/pythondotnet/2014-May/001527.html

    GCHandle pins the .NET array and np.frombuffer creates a zero-copy view.
    The pin is released in `finally`, so we must copy the data before returning;
    otherwise the numpy array becomes a dangling pointer and may segfault
    when the .NET GC compacts the heap.

    Pass dtype (e.g. np.float32) to convert in a single copy instead of two.
    """
    if src is None:
        return np.array([], dtype=dtype)
    src_hndl = GCHandle.Alloc(src, GCHandleType.Pinned)
    try:
        src_ptr = src_hndl.AddrOfPinnedObject().ToInt64()
        bufType = ctypes.c_double * len(src)
        cbuf = bufType.from_address(src_ptr)
        dest = np.array(cbuf, dtype=dtype)  # copy + convert while pinned
    finally:
        if src_hndl.IsAllocated:
            src_hndl.Free()
    return dest
