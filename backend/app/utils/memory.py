"""Force the interpreter and glibc to hand freed heap memory back to the OS.

WeasyPrint (cairo/pango) and pandas allocate large, often-fragmented blocks of
native memory. CPython's own GC won't touch that, and glibc's malloc keeps
freed arenas around for reuse instead of releasing them — so process RSS
climbs monotonically across requests on a long-lived server until it is
OOM-killed, even though nothing is actually "leaked" in the Python sense.
Call this after each memory-heavy operation (PDF render, batch row, Excel
parse) to collect Python garbage and trim glibc's free arenas.
"""

import ctypes
import gc

try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:
    _libc = None


def release_memory() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except Exception:
            pass
