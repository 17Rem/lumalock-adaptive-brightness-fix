# Third-party notices

## gpu_aux

The AMD and Intel ctypes bindings in `lumalock/vendor/gpu_aux/adl.py` and `intel.py` are from [cnbright/gpu_aux](https://github.com/cnbright/gpu_aux), commit `eda49e230b48a7a8b995b664a8a0756b2bde99f1`.

Copyright (c) 2026 cnbright. Licensed under MIT. The original [license](lumalock/vendor/gpu_aux/LICENSE) is included. The two upstream source files are unmodified; their SHA-256 digests and source revision are recorded in [SOURCE.json](lumalock/vendor/gpu_aux/SOURCE.json). Package initialization and integration are part of LumaLock.

## Drivers and device firmware

GPU driver DLLs, vendor SDK header archives, monitor firmware images and captured brightness table payloads are not distributed with this project. The compatibility profile contains identity metadata and cryptographic digests. Required factory tables are read from the user's own compatible device at runtime.

NVIDIA, AMD, Intel, BOE and Novatek names identify interoperability targets; the project is not affiliated with or endorsed by those companies.
