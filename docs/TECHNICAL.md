# Design and protocol notes

## Supported behavior

The supported NT71873 panel gradually changes its overall brightness with image content. Replacing the active RAM LUT with the verified factory high LUT removed the observed gradual transition. The implementation does not claim to identify a universal CABC control or change the monitor's flash firmware.

## Distribution without firmware

`lumalock/profiles/ne180qdm_nz4.json` contains panel identity and SHA-256 fingerprints only. It contains no captured firmware image or actual factory LUT payload. The manifest itself is hash-checked by `profile.py`.

On each operation, the program reads the supported device's code region (`0x000000–0x007FFF`) and factory tables (`0x029E00`, `0x029F00`). Each 256-byte block and both 128-byte halves must independently match their expected hashes three consecutive times. It then checks the whole code-region digest and both 256-byte table digests. The manifest's firmware marker is descriptive metadata; the code-region fingerprint is the verification gate.

This validates the required code region and tables, not every byte of the device's firmware. The curves are kept in memory for that operation and in private recovery state if needed. Tests generate synthetic code and tables instead of redistributing device captures.

## Transaction

1. Discover AUX endpoints and verify sink identity and EDID. Product/model must match; unit serial/date may differ.
2. Bind the chosen backend, endpoint, full EDID hash and sink identity to recovery state. Acquire the state-directory lock and start a separate watchdog.
3. Temporarily initialize AUX state and select only allowed firmware pages. Verify code and both factory curves, then restore page zero.
4. Check the restricted query window and expected `0x0C20` baseline. Temporarily open the RAM query range.
5. Read the active 256-byte table with 16-byte and 8-byte transfers, requiring repeated identical results. Refuse unknown active tables.
6. For `apply` or `restore`, send the selected verified table to `0x5600–0x56FF` as 43 short packets. For `check`, leave the active table unchanged.
7. Verify the complete table, close the query range, verify baseline and AUX state, and compare link health.

Only the observed original and high factory tables are accepted for writes. The public command interface has no arbitrary-address write, flash operation or compatibility override. A failed write is not automatically retried as an application operation. Failure recovery writes the original factory table, not necessarily the table active before the failed action.

## Recovery limits

The watchdog deadline is six minutes. Verification and writing stop earlier to reserve recovery time. The watchdog checks the same device identity before recovery and verifies locally saved table hashes before writing them. It does not replace a disconnected device with another matching display. Intel process handles are rediscovered from stable endpoint identity.

Recovery is best effort: device removal, driver failure, system shutdown or severe hangs can prevent it. The state-directory lock coordinates LumaLock instances sharing that directory; it does not coordinate unrelated tools or instances using a different state directory. Do not run them concurrently.

## Modules

| Module | Responsibility |
| --- | --- |
| `backends.py` | NVIDIA, AMD, Intel and Linux transport adapters |
| `protocol.py` | Bounded panel commands, reads, table verification and recovery |
| `compatibility.py` | Enumeration, identity matching and live fingerprint verification |
| `profile.py` | Public fingerprints and verified in-memory factory curves |
| `control.py` | CLI operations, transaction state and watchdog |
| `runtime.py` | State location, locks and process options |
| `progress.py` | Optional structured events; observer exceptions cannot interrupt hardware operations |
| `gui.py` | Native Tk UI, one worker thread and queue-based progress delivery |

See [backend notes](BACKENDS.md) for platform requirements and transport differences. Only Windows NVIDIA has been tested on physical hardware so far.

## GUI progress and concurrency

The GUI uses the same `control.run()` transaction as the CLI. Tk widgets are updated only on the main thread; driver calls and verification run in one non-daemon worker thread. Controls remain disabled until the UI consumes the final result. Window closing is deferred during active work and pending watchdog recovery.

Firmware progress advances only after a full block and both halves pass verification. Write progress advances only after each packet returns successfully. Recovery counts attempted packets and subsequently verifies the full original table. No overall percentage or completion ETA is fabricated. A write-stage 100% is followed by readback and cleanup; only the transaction's final result can produce a success state.

The Windows `LumaLock.pyw` entry launches without a console. `python -m lumalock` with no arguments also opens the GUI; explicit CLI actions do not import Tk. GUI tests mock transport access and skip widget checks where Tk or a display server is unavailable.
