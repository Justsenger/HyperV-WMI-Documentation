import pandas as pd
import glob
import os
import re
import json

# 显式检测 tabulate
try:
    from tabulate import tabulate
except ImportError:
    print("\n错误: 未找到 tabulate 库。")
    print("请执行命令安装: py -m pip install tabulate")
    exit(1)

def analyze_wmi_diff():
    # --- 配置区域 ---
    file_pattern = "WmiDoc_Final_*_WithEnums.csv"
    alias_file = "wmi_alias.json"
    output_xlsx = "WMI_Version_Comparison_Report.xlsx"
    output_csv = "WMI_Version_Comparison_Report.csv"
    docs_dir = "docs"

    # 1. 获取 CSV 文件
    file_list = glob.glob(file_pattern)
    if not file_list:
        print("错误: 当前目录下未找到匹配的 CSV 文件！")
        return

    # 2. 加载翻译映射表
    translations = {}
    if os.path.exists(alias_file):
        try:
            with open(alias_file, "r", encoding="utf-8") as f:
                translations = json.load(f)
            print(f"成功加载翻译字典，包含 {len(translations)} 条映射。")
        except Exception as e:
            print(f"读取 JSON 失败: {e}")

    all_dfs = []
    version_list = []

    # 3. 读取各版本数据
    for file_path in file_list:
        filename = os.path.basename(file_path)
        match = re.search(r"WmiDoc_Final_(\d+)_WithEnums", filename)
        if match:
            build_num = match.group(1)
            print(f"处理版本数据: {build_num}")
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df['Version'] = build_num
            all_dfs.append(df)
            version_list.append(build_num)

    # 4. 合并与排序
    full_df = pd.concat(all_dfs, ignore_index=True)
    sorted_versions = sorted(list(set(version_list)), key=int, reverse=True)

    # 5. 提取元数据 (基于最高版本)
    full_df['Version_Int'] = full_df['Version'].astype(int)
    metadata = full_df.sort_values('Version_Int').drop_duplicates(subset=['Class', 'Member'], keep='last').copy()

    # 处理描述
    metadata.rename(columns={'Desc': 'Desc_EN'}, inplace=True)
    def get_translated_desc(row):
        mapping_key = f"{row['Class']}:{row['Member']}"
        return translations.get(mapping_key, row['Desc_EN'])

    metadata['Desc'] = metadata.apply(get_translated_desc, axis=1)

    if 'Access' not in metadata.columns:
        metadata['Access'] = metadata.apply(lambda r: "Method" if r['Category'] == 'Method' else "Property", axis=1)

    # 6. 生成版本支持透视表 (✅/❌)
    pivot = full_df.pivot_table(index=['Class', 'Member'], columns='Version', aggfunc='size', fill_value=0)
    for col in pivot.columns:
        pivot[col] = pivot[col].apply(lambda x: "✅" if x > 0 else "❌")

    # 7. 合并最终结果
    result = metadata.merge(pivot, on=['Class', 'Member'], how='left')

    # 8. 整理列顺序
    base_cols = ['Class', 'Member', 'Type', 'Category', 'Access']
    final_cols = base_cols + sorted_versions + ['Desc', 'Desc_EN']
    result = result[[c for c in final_cols if c in result.columns]]

    # 9. 导出 Master XLSX
    print(f"导出 Excel 报告: {output_xlsx}")
    try:
        with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
            result.to_excel(writer, index=False, sheet_name='WMI对比差异')
            ws = writer.sheets['WMI对比差异']
            ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "C2"
            for i, col in enumerate(result.columns):
                col_letter = ws.cell(row=1, column=i+1).column_letter
                ws.column_dimensions[col_letter].width = 100 if 'Desc' in col else 22
    except Exception as e:
        print(f"Excel 导出失败: {e}")

    # 10. 导出 Master CSV
    print(f"导出 CSV 报告: {output_csv}")
    result.to_csv(output_csv, index=False, encoding='utf-8-sig')

    # 11. 拆分生成详细文档
    print(f"生成类详细文档 (docs/)...")
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)

    index_list = []
    grouped = result.groupby('Class')
    total_classes = len(grouped)

    for class_name, group in grouped:
        sub_group = group.drop(columns=['Class'])
        safe_name = "".join([c for c in class_name if c.isalnum() or c == '_']).strip()
        md_filename = f"{safe_name}.md"
        md_path = os.path.join(docs_dir, md_filename)
        
        index_list.append(f"- [{class_name}](./{docs_dir}/{md_filename})")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# WMI Class: {class_name}\n\n")
            f.write(f"[⬅️ 返回索引](../README.md) | [📊 下载全量表 CSV](../{output_csv})\n\n")
            f.write(f"## 成员列表与兼容性对照\n\n")
            f.write(sub_group.to_markdown(index=False))
            f.write(f"\n\n---\n*更新日期: {pd.Timestamp.now().strftime('%Y-%m-%d')}*")

    # 12. 最终生成 README.md (硬核专业版)
    print("更新 README.md 主页文档...")
    index_links_str = "\n".join(sorted(index_list))
    
    readme_content = f"""# Windows WMI 版本对照报告 (WMI Version Comparison Report)

本仓库包含一份详细的 WMI (Windows Management Instrumentation) 类、属性及方法的版本兼容性对照表。主要涵盖了从 Windows 10 早期版本到最新的 Windows 11 及 Server 2025 的变化情况。

## 📊 完整数据表
GitHub 对超大文件渲染有限制，建议通过以下方式获取完整数据：

*   👉 **[点击此处下载 Excel 版 (推荐搜索与筛选)]({output_xlsx})**
*   👉 **[查看 Master CSV 原文件]({output_csv})**

---

## 📅 报告涵盖的 Windows 版本说明
本报告对比了以下内核版本中的 WMI 接口差异：

| 版本号 (Build) | 对应 Windows 发行版本 |
| :--- | :--- |
| **14393** | Windows 10 v1607 (Anniversary Update) / Server 2016 |
| **17763** | Windows Server 2019 / Windows 10 LTSC 2019 |
| **19045** | Windows 10 v22H2 / Enterprise LTSC 2021 |
| **20348** | **Windows Server 2022** |
| **22621** | Windows 11 v22H2 / 23H2 |
| **26100** | Windows 11 v24H2 / **Server 2025** |

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
该报告整理了以下核心 WMI 命名空间下的类：

*   **Win32_VideoController**: 视频控制器（显卡）属性。
*   **Msvm_ComputerSystem**: 虚拟机实例及其状态管理。
*   **Msvm_VirtualSystemSettingData**: 虚拟机全局设置（如安全引导、引导顺序）。
*   **Msvm_ProcessorSettingData / MemorySettingData**: 虚拟 CPU (含分层虚拟化) 与 内存 (含 SGX) 配置。
*   **Msvm_GpuPartitionSettingData**: GPU 分区与 GPU-P 核心属性（22621+ 版本显著增加）。
*   **Msvm_VirtualSystemManagementService**: 虚拟机生命周期管理方法接口。

---

## 🛠 如何使用
1.  **类索引查询**：在下方“类快速索引”中使用 `Ctrl+F` 搜类名，点击进入查看各版本 ✅/❌ 支持情况。
2.  **兼容性排查**：如果脚本在 Server 2025 正常但在 2022 报错，请检查对应成员在 `20348` 列是否为 ❌。
3.  **开发参考**：在调用 `ModifySystemSettings` 等方法前，确认目标系统的内核版本是否支持相关的属性（如 `EnableHierarchicalVirtualization`）。

---

## 📂 WMI 类快速索引 ({total_classes} 个)
{index_links_str}

---
*旨在辅助 Hyper-V 与 Windows 系统管理开发。*
"""
    with open("README.md", 'w', encoding='utf-8') as f:
        f.write(readme_content)

    print(f"\n处理完成！总共整理了 {total_classes} 个 WMI 类。")

if __name__ == "__main__":
    analyze_wmi_diff()