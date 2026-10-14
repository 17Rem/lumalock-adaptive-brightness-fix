# LumaLock — Portable Monitor Auto-Dimming Fix

**Stop content-adaptive brightness changes on compatible BOE NE180QDM-NZ4 portable monitors.** LumaLock locks the panel to its verified factory high-brightness curve through DisplayPort AUX, without disassembly or flashing firmware.

**解决便携屏随画面明暗自动调光、白色背景出现后缓慢变亮的问题。** 适用于通过完整兼容性核验的 BOE NE180QDM-NZ4 / NT71873 面板组合。

[中文完整使用说明](docs/USAGE.zh-CN.md) · [Platform support / 平台支持](docs/BACKENDS.md) · [How it works](docs/TECHNICAL.md)

## What it fixes

Some portable monitors gradually brighten or dim when the image changes, even with Windows adaptive brightness disabled. On the tested DisplayPort pass-through setup, replacing the active brightness lookup table with the panel's own factory high curve removed that gradual change and retained a bright image.

Search terms: portable monitor auto dimming, adaptive brightness, dynamic contrast, CABC, content-adaptive backlight, BOE0C64, NE180QDM-NZ4, NT71873, 便携屏自动亮度、动态对比度、自动变暗、亮度锁定。

This is a narrowly matched panel workaround. It is not a universal CABC switch: the same size, resolution, refresh rate, or advertised brightness does not establish compatibility.

## Compatibility

| Item | Supported profile |
| --- | --- |
| Panel | BOE NE180QDM-NZ4, EDID product BOE0C64 |
| Controller | Novatek NT71873; matching sink identity required |
| Firmware | Exact supported code and both factory curve fingerprints must match |
| Connection | DisplayPort/eDP AUX must reach the supported panel; the tested setup uses a DP pass-through board |
| Windows NVIDIA | Hardware tested |
| Windows AMD / Intel | Implemented, experimental; offline tests only |
| Native Linux | DRM AUX + uniquely paired I²C device; experimental, offline tests only |
| macOS | Not implemented |

Different device serial numbers and manufacturing dates are allowed. Firmware or curve mismatches stop the operation. HDMI, docks, adapters and USB-C video paths depend on whether the required AUX interface actually reaches the panel. See [backend requirements](docs/BACKENDS.md).

## Quick start

Use **64-bit Python 3.10 or newer** and your GPU's driver. No pip packages are required. Intel additionally requires the official IGCL runtime. Download and extract the source.

### Graphical interface / 图形界面

**Windows: double-click `LumaLock.pyw`.** The interface opens without a command window when Python's `.pyw` association is installed. You can also run `run.cmd` without arguments, or `python -m lumalock gui`.

**Windows 用户双击 `LumaLock.pyw` 即可打开界面。** 选择屏幕后，点击「检查兼容性」「固定高亮度」或「恢复自适应」。界面使用黑白灰与荧光黄的工业信息设计，支持实际进度、操作记录和错误恢复状态。

Linux: run `sh ./run.sh gui` in a desktop session. The GUI uses Tkinter; some Linux distributions package it separately (for example `python3-tk` on Debian/Ubuntu). The CLI remains usable without Tk.

Progress is **per stage**: verified firmware blocks and completed write packets use actual counts. Connection, readback and cleanup show activity without inventing a percentage. Reaching 100% for writing does not mean the full operation is finished; wait for the final result. Actions and window closing are blocked while a transaction or its watchdog recovery is pending.

### Command line

Open a terminal in this directory:

Windows:

```powershell
.\run.cmd list
.\run.cmd check
.\run.cmd apply
```

Linux:

```sh
sh ./run.sh list
sh ./run.sh check
sh ./run.sh apply
```

- `list` discovers candidates. A candidate still needs firmware verification.
- `check` verifies the live firmware fingerprints and curves. It temporarily changes query controls, restores them, and does not write the brightness table.
- `apply` repeats verification and applies the fixed high curve to volatile panel RAM.
- `restore` repeats verification and restores the factory adaptive curve.

To undo the setting:

```powershell
.\run.cmd restore
```

On Linux use `sh ./run.sh restore`. Multiple matching monitors require `--display "ENDPOINT_ID"` using the exact identity printed by `list`. You can restrict discovery with `--backend nvidia`, `amd`, `intel` or `linux`.

Wait for the result; verification and writing can take a few minutes. Keep the display connected and avoid running another monitor-control tool simultaneously. There is no automatic start-up service. Reapply after power loss, sleep or reconnecting if the effect resets.

## Recovery and local data

Writes are limited to the two fingerprint-verified curves. The program checks every completed table, restores query controls, and starts a separate recovery process with a six-minute deadline. Recovery cannot be guaranteed if the display disconnects or the driver stops responding. If recovery fails, stop other monitor tools, wait for recovery to finish, then power-cycle the display.

This tool does not flash firmware or create a full firmware backup. It saves the original **256-byte brightness table**, recovery state and diagnostic logs locally:

- Windows: `%LOCALAPPDATA%\LumaLock`
- Linux: `$XDG_STATE_HOME/lumalock`, or `~/.local/state/lumalock`

Logs may contain display identity, device data and raw firmware reads. Do not attach the entire state directory to a public issue. Share the error text, panel model, OS and selected backend first. `LUMALOCK_STATE_DIR` can override the location; keep it outside this source directory.

## Development

```sh
python -B -m unittest discover -s tests -v
```

Tests use synthetic device data and do not access hardware. The source distribution contains compatibility hashes, not captured vendor firmware or factory table bytes. See [technical notes](docs/TECHNICAL.md) and the [release checklist](docs/RELEASING.md).

## License

LumaLock code is available under the [MIT License](LICENSE). Vendored AMD/Intel bindings retain their own MIT notice; see [third-party notices](THIRD_PARTY_NOTICES.md).
