# 平台与显卡支持 / Platform backends

LumaLock 将面板协议与显卡通信分开。面板型号、固件代码、原始曲线及写后校验要求对所有平台相同。接口可用且核验通过后，才能应用曲线。

| 平台 | 通信接口 | 运行条件 | 验证状态 |
| --- | --- | --- | --- |
| Windows / NVIDIA | NVAPI 原生 AUX、I²C-over-AUX | 64 位 NVIDIA 驱动，提供所用 AUX 入口 | RTX 4070 SUPER 实测 |
| Windows / AMD | ADL Native AUX、DDCBlockAccess | 64 位 AMD 驱动，提供这两个入口 | 实验性；离线测试 |
| Windows / Intel | IGCL `ctlAUXAccess` | 官方 `ControlLib.dll` 可加载；写操作需要管理员权限 | 实验性；离线测试 |
| Linux | DRM AUX 字符设备、`i2c-dev` | 驱动同时开放匹配设备，且当前用户有读写权限 | 实验性；离线测试 |

**“已实现”不等于已在每种显卡上实测。** 新接口的结构、长度、地址转换、错误处理及写入边界已做离线测试。驱动版本、访问权限、显示接口路由和面板通信时序仍需对应实物确认。macOS 未实现。

## 使用

Windows：

```powershell
.\run.cmd list
.\run.cmd check
.\run.cmd apply
.\run.cmd restore
```

默认 `--backend auto`。可加 `--backend nvidia`、`--backend amd` 或 `--backend intel`，只检查指定驱动。双显卡电脑以实际连接显示器的输出接口为准。

Linux：

```sh
sh ./run.sh list
sh ./run.sh check
sh ./run.sh apply
sh ./run.sh restore
```

多块候选时，使用 `list` 返回的完整标识。例如 `--display "nvidia:0x12345678"`，该标识只是示例。Linux 标识含 `|`，必须加引号。旧的 NVIDIA 十六进制显示器编号仍可使用。

`list` 中某个接口缺失，不影响其他可用接口。例如仅有 NVIDIA 显卡时，提示 Intel 库缺失并不代表 NVIDIA 操作失败。`check` 会临时调整查询窗口和 AUX 状态，完成后恢复；不写亮度表。

## Windows 驱动依赖

- NVIDIA 使用系统的 `nvapi64.dll`，保留原有已验证通信方式。
- AMD 使用系统 ADL。缺少 `NativeAUXChannel_Access` 或 `DDCBlockAccess_Get` 时，列出具体错误并停止该接口。
- Intel 使用官方 IGCL 的 `ControlLib.dll`。安装对应显卡驱动和官方 IGCL 运行库，使系统能够加载该库。按照 Intel 的接口要求，涉及 AUX 写入的 `check/apply/restore` 需要以管理员身份运行。

项目包含固定版本的 MIT 授权 AMD/Intel Python 接口代码，不分发显卡驱动 DLL。来源、版本和哈希见 `lumalock/vendor/gpu_aux/SOURCE.json`。

## Linux 接口与权限

Linux 需要内核启用 `CONFIG_DRM_DISPLAY_DP_AUX_CHARDEV`，驱动注册 AUX/I²C 适配器，以及可用的 `i2c-dev` 模块。用户需要对选中的 `/dev/drm_dp_auxN` 和 `/dev/i2c-N` 有读写权限。可通过系统设备权限配置授予访问；管理员测试也可用 `sudo sh ./run.sh check`，但这样生成的日志可能归 root 所有。

工具只从 `/sys/class/drm_dp_aux_dev` 枚举 AUX，要求 I²C 适配器与它具有相同的真实 sysfs 父目录及名称，并且配对唯一。不会按设备编号猜测配对，也不会扫描其他 I²C 总线。无法唯一配对时停止并报告原因。

有些驱动没有开放这些接口。此时不能仅凭显卡品牌认定支持；需要驱动提供接口。WSL 通常不提供直连显示器的这些设备，不等同于原生 Linux 硬件测试。

## 读写差异与保护

NVIDIA 和 Intel 可逐次表达原生 AUX、I²C 读写及 MOT（保持连续事务）阶段。AMD DDC 和 Linux `i2c-dev` 路径使用带 STOP 的 I²C 事务；程序保留指针等待和 16/8 字节分段读取，不伪称其具备逐阶段 MOT 控制。如果面板不能接受这种事务方式，固件/曲线读回核验会失败，不进入亮度表写入。

所有后端只接收公共面板层允许的操作。原生写入只限已验证的初始化状态；私有写入只限已验证的查询窗口、固件页选择和原始/高值曲线短包。程序不提供任意地址写入、刷固件或跳过核验开关，也不会在驱动报告写失败后自动重试该包。Linux 内核和厂商驱动内部的重试行为由它们自身决定。

恢复进程重新检查通信接口、端点、EDID 和控制器身份。Intel 的句柄只在进程内有效，因此恢复标识使用 PCI 位置和系统输出编号，不能把旧进程的句柄交给新进程。

## 开发依据

- [Intel IGCL AUX API](https://intel.github.io/drivers.gpu.control-library/Control/api.html)
- [AMD ADL DDC API](https://gpuopen-librariesandsdks.github.io/adl/group__I2CDDCEDIDAPI.html)
- [gpu_aux 驱动接口研究及实现](https://github.com/cnbright/gpu_aux)
- [Linux DRM AUX/I²C 注册](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/display/drm_dp_helper.c)
- [Linux AUX 字符设备](https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/display/drm_dp_aux_dev.c)

## English summary

Windows NVIDIA is hardware-validated. Windows AMD/Intel and Linux adapters are implemented with offline tests and remain experimental. All use the same strict panel/firmware profile. `auto` discovers available backends; `--backend` restricts discovery and `--display` selects a full endpoint identity. Linux requires uniquely paired DRM AUX and I²C devices plus permissions. Intel AUX writes require administrator privileges. AMD/Linux use stopped I²C transactions; full firmware and LUT verification must succeed with those semantics before LUT writes. No unverified profile override is provided.
