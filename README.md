# Windows WMI 版本对照报告 (WMI Version Comparison Report)

本仓库包含一份详细的 WMI (Windows Management Instrumentation) 类、属性及方法的版本兼容性对照表。主要涵盖了从 Windows 10 早期版本到最新的 Windows 11 及 Server 2025 的变化情况。

## 📊 完整数据表

GitHub 支持直接渲染 CSV 文件，你可以点击下方链接查看带搜索和过滤功能的完整表格：

👉 **[点击此处查看：WMI_Version_Comparison_Report.csv](./WMI_Version_Comparison_Report.csv)**

---

## 🔍 内容概述

该报告对比了以下核心 WMI 类在不同 Windows 内核版本中的存在情况：

*   **Win32_VideoController**: 视频控制器（显卡）相关属性及方法。
*   **Msvm_ComputerSystem**: Hyper-V 虚拟机系统核心实例。
*   **Msvm_VirtualSystemSettingData**: 虚拟机设置数据。
*   **Msvm_ProcessorSettingData / Msvm_MemorySettingData**: 虚拟处理器与内存配置。
*   **Msvm_StorageAllocationSettingData**: 虚拟存储分配。
*   **Msvm_SummaryInformation**: 虚拟机摘要信息。
*   **Msvm_GpuPartitionSettingData / Msvm_PartitionableGpu**: GPU 分区与 GPU-P 相关。
*   **Msvm_VirtualSystemManagementService**: 虚拟机管理服务接口。

## 📅 对照版本说明

表格中的版本号对应以下主要的 Windows 发行版：

| 版本号 (Build) | 对应 Windows 版本 (参考) |
| :--- | :--- |
| **14393** | Windows 10 v1607 (Anniversary Update) / Server 2016 |
| **19045** | Windows 10 v22H2 |
| **22621** | Windows 11 v22H2 |
| **26100** | Windows 11 v24H2 / Server 2025 |

## 💡 数据预览

以下是部分核心数据的展示（仅作示例，完整内容请查看 CSV 文件）：

| Class | Member | Type | 14393 | 19045 | 22621 | 26100 | 描述 |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| Win32_VideoController | AdapterRAM | UInt32 | ✅ | ✅ | ✅ | ✅ | 指明视频适配器的内存大小。 |
| Msvm_ComputerSystem | ProcessID | UInt32 | ✅ | ✅ | ✅ | ✅ | 正在运行此虚拟机的进程标识符 (Vmwp.exe)。 |
| Msvm_ProcessorSettingData | EnableHierarchicalVirtualization | Boolean | ❌ | ❌ | ❌ | ✅ | 是否为虚拟机启用分层虚拟化 (Nested)。 |
| Msvm_PartitionableGpu | SupportsIncomingLiveMigration | Boolean | ❌ | ❌ | ❌ | ✅ | 指示可分区 GPU 是否支持实时迁移。 |

## 🛠 如何使用

1.  **在线浏览**：直接在 GitHub 点击 CSV 文件，利用顶部的 `Filter` 按钮搜索特定的类名（如 `Msvm`）或成员名。
2.  **本地分析**：将 `WMI_Version_Comparison_Report.csv` 下载后，使用 Excel、PowerBI 或 Python (Pandas) 进行离线分析。
3.  **开发参考**：在编写自动化脚本或 Hyper-V 管理工具时，检查特定属性（如 GPU-P 相关属性）在旧版本系统上的可用性。

---
*数据由自动化工具提取，仅供开发者参考。*