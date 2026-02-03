# Windows WMI 版本对照报告 (WMI Version Comparison Report)

本仓库包含一份详细的 WMI (Windows Management Instrumentation) 类、属性及方法的版本兼容性对照表。主要涵盖了从 Windows 10 早期版本到最新的 Windows 11 及 Server 2025 的变化情况。

## 📊 完整数据表

GitHub 支持直接渲染 CSV 文件，你可以点击下方链接查看带搜索和过滤功能的完整表格：

👉 **[点击此处查看：WMI_Version_Comparison_Report.csv](./WMI_Version_Comparison_Report.csv)**

---

## 📅 报告涵盖的 Windows 版本说明

本报告对比了以下内核版本中的 WMI 接口差异：

| 版本号 (Build) | 对应 Windows 发行版本 |
| :--- | :--- |
| **14393** | Windows 10 v1607 (Anniversary Update) / Server 2016 |
| **19045** | Windows 10 v22H2 / Enterprise LTSC 2021 |
| **20348** | **Windows Server 2022** |
| **22621** | Windows 11 v22H2 / 23H2 |
| **26100** | Windows 11 v24H2 / Server 2025 |

---

## 💻 Hyper-V 主机与虚拟机配置版本兼容性

下表列出了不同版本的 Windows 主机支持的虚拟机配置版本（Configuration Version）。在进行跨版本迁移或 WMI 自动化管理时，请参考此表。

| Hyper-V 主机 Windows 版本 | 12.0 | 11.0 | 10.0 | 9.3 | 9.2 | 9.1 | 9.0 | 8.3 | 8.2 | 8.1 | 8.0 | 7.1 | 7.0 | 6.2 | 5.0 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Windows Server 2025** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Windows 11, 24H2** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Windows 11, 22H2 / 23H2** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Windows Server 2022** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Windows 10 LTSC 2021** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Windows Server 2019 / Win 10 LTSC 2019** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Windows Server 2016 / Win 10 LTSB 2016** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 🔍 WMI 类内容概述

该报告对比了以下核心 WMI 命名空间下的类：

*   **Win32_VideoController**: 视频控制器（显卡）属性。
*   **Msvm_ComputerSystem**: 虚拟机实例及其状态管理。
*   **Msvm_VirtualSystemSettingData**: 虚拟机全局设置（如安全引导、引导顺序）。
*   **Msvm_ProcessorSettingData / MemorySettingData**: 虚拟 CPU (含分层虚拟化) 与 内存 (含 SGX) 配置。
*   **Msvm_GpuPartitionSettingData**: GPU 分区与 GPU-P 核心属性（22621+ 版本显著增加）。
*   **Msvm_VirtualSystemManagementService**: 虚拟机生命周期管理方法接口。

## 🛠 如何使用

1.  **在线浏览**：直接点击仓库中的 CSV 文件。GitHub 的预览界面支持通过 `Filter` 框快速搜索类名（如输入 `Msvm`）。
2.  **兼容性排查**：如果你的脚本在 Server 2025 上运行正常但在 Server 2022 上报错，请在 CSV 中搜索对应的 `Member`，查看 `20348` 列是否为 ❌。
3.  **开发参考**：在调用 `ModifySystemSettings` 等方法前，确认目标系统的内核版本是否支持相关的属性（如 `EnableHierarchicalVirtualization`）。

---
*数据由自动化脚本提取，旨在辅助 Hyper-V 与 Windows 系统管理开发。*