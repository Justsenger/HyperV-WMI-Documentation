import pandas as pd
import glob
import os
import re
import json
from datetime import datetime

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

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 开始执行 WMI 版本对比分析...")

    # 1. 获取 CSV 文件
    file_list = glob.glob(file_pattern)
    if not file_list:
        print(f"❌ 错误: 当前目录下未找到匹配的 CSV 文件 ({file_pattern})！")
        return
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📂 找到 {len(file_list)} 个原始数据文件。")

    # 2. 加载翻译映射表
    translations = {}
    if os.path.exists(alias_file):
        try:
            with open(alias_file, "r", encoding="utf-8") as f:
                translations = json.load(f)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📝 成功加载翻译字典，包含 {len(translations)} 条映射。")
        except Exception as e:
            print(f"⚠️ 读取 JSON 失败: {e}")

    # 3. 读取各版本数据 (恢复详细读取日志)
    all_dfs = []
    version_list = []
    for file_path in sorted(file_list):
        filename = os.path.basename(file_path)
        match = re.search(r"WmiDoc_Final_(\d+)_WithEnums", filename)
        if match:
            build_num = match.group(1)
            print(f"   -> 正在读取 Build: {build_num} ...")
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df['Version'] = build_num
            all_dfs.append(df)
            version_list.append(build_num)

    # 4. 合并与排序
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔄 正在合并数据并提取元数据...")
    full_df = pd.concat(all_dfs, ignore_index=True)
    full_df['Version_Int'] = full_df['Version'].astype(int)
    sorted_versions = sorted(list(set(version_list)), key=int, reverse=True)

    # 5. 提取元数据 (基于最高版本)
    metadata = full_df.sort_values('Version_Int').drop_duplicates(subset=['Class', 'Member'], keep='last').copy()
    metadata.rename(columns={'Desc': 'Desc_EN'}, inplace=True)
    metadata['Desc'] = metadata.apply(lambda r: translations.get(f"{r['Class']}:{r['Member']}", r['Desc_EN']), axis=1)

    # 6. 生成兼容性透视表 (✅/❌)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 生成各 Build 版本间的兼容性矩阵...")
    pivot = full_df.pivot_table(index=['Class', 'Member'], columns='Version', aggfunc='size', fill_value=0)
    for col in pivot.columns:
        pivot[col] = pivot[col].apply(lambda x: "✅" if x > 0 else "❌")

    # 7. 合并最终结果
    result = metadata.merge(pivot, on=['Class', 'Member'], how='left')
    base_cols = ['Class', 'Member', 'Type']
    final_cols = base_cols + sorted_versions + ['Desc', 'Desc_EN']
    result = result[[c for c in final_cols if c in result.columns]]

    # 8. 导出 Master 报表
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 导出报表: {output_xlsx}")
    try:
        with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
            result.to_excel(writer, index=False, sheet_name='WMI对比差异')
            ws = writer.sheets['WMI对比差异']
            ws.freeze_panes = "C2"
            # 自动调整列宽
            for i, col in enumerate(result.columns):
                ws.column_dimensions[chr(65+i) if i<26 else 'A'+chr(65+i-26)].width = 20
    except Exception as e:
        print(f"❌ Excel 导出失败: {e}")
    
    result.to_csv(output_csv, index=False, encoding='utf-8-sig')

    # 9. 生成详细文档 (docs/*.md)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📄 正在拆分生成各类的详细 Markdown 文档...")
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
        index_list.append(f"- [{class_name}](./docs/{md_filename})")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# {class_name}\n\n")
            f.write(f"[⬅️ 返回索引](../README.md)\n\n")
            f.write(sub_group.to_markdown(index=False))

    # 10. 生成主 README.md (包含 12.4 Krypton 列)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📝 正在生成主 README.md 索引页...")
    
    vm_cols = ["255.0", "254.0", "12.4", "12.3", "12.2", "12.1", "12.0", "11.2", "11.1", "11.0", "10.5", "10.0", "9.3", "9.2", "9.1", "9.0", "8.3", "8.2", "8.1", "8.0", "7.1", "7.0", "6.2", "5.0"]
    
    # 按照你的截图对齐 ✅/❌ 逻辑
    build_definitions = [
        ("29560", "Windows 11 27H1 (Krypton/Insider)", ["✅"]*24),
        ("28000", "Windows 11 26H1", ["❌"]*2 + ["✅"]*22),
        ("26200", "Windows 11 25H2", ["❌"]*6 + ["✅"]*14 + ["❌"]*4),
        ("26100", "Win 11 24H2 / Server 2025", ["❌"]*6 + ["✅"]*14 + ["❌"]*4),
        ("22621", "Windows 11 22H2 / 23H2", ["❌"]*9 + ["✅"]*11 + ["❌"]*4),
        ("22000", "Windows 11 21H2", ["❌"]*11 + ["✅"]*9 + ["❌"]*4),
        ("20348", "Windows Server 2022", ["❌"]*11 + ["✅"]*9 + ["❌"]*4),
        ("19045", "Win10 22H2 / LTSC 2021", ["❌"]*13 + ["✅"]*7 + ["❌"]*4),
        ("17763", "Win Server 2019 / LTSC 2019", ["❌"]*15 + ["✅"]*9),
        ("14393", "Win10 1607 / Server 2016", ["❌"]*19 + ["✅"]*5),
    ]

    table_body = ""
    for b_num, b_os, support in build_definitions:
        table_body += f"| **{b_num}** | {b_os} | " + " | ".join(support) + " |\n"

    readme_content = f"""# Windows WMI 版本对照报告

本仓库包含一份详细的 WMI (Windows Management Instrumentation) 类、属性及方法的版本兼容性对照表。主要涵盖了主流版本的变化情况。

## 📅 报告涵盖的 Windows 版本说明

| 版本号 (Build) | 对应 Windows 发行版本 | {" | ".join(vm_cols)} |
| :--- | :--- | {":---: | " * len(vm_cols)}
{table_body}
---

## 📂 WMI 类索引 ({total_classes} 个)

{chr(10).join(sorted(index_list))}

---
*更新日期: {datetime.now().strftime('%Y-%m-%d')}*
"""

    with open("README.md", 'w', encoding='utf-8') as f:
        f.write(readme_content)

    # 11. 最终输出统计日志
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ 处理完成！包含 12.4 Krypton 支持列。")
    print(f"   - 整理 WMI 类: {total_classes} 个")
    print(f"   - 生成详情页: {docs_dir}/*.md")
    print(f"   - 主索引文件: README.md")

if __name__ == "__main__":
    analyze_wmi_diff()