import pandas as pd
import glob
import os
import re
import json
# 显式导入，确保环境能找到它
try:
    import tabulate
except ImportError:
    print("\n错误: 未找到 tabulate 库。")
    print("请执行以下命令安装: py -m pip install tabulate")
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
            print(f"成功加载翻译字典，包含 {len(translations)} 条映射规则。")
        except Exception as e:
            print(f"读取 JSON 失败: {e}")

    all_dfs = []
    version_list = []

    # 3. 读取数据
    for file_path in file_list:
        filename = os.path.basename(file_path)
        match = re.search(r"WmiDoc_Final_(\d+)_WithEnums", filename)
        if match:
            build_num = match.group(1)
            print(f"读取版本: {build_num}")
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df['Version'] = build_num
            all_dfs.append(df)
            version_list.append(build_num)

    # 4. 合并与排序
    full_df = pd.concat(all_dfs, ignore_index=True)
    sorted_versions = sorted(version_list, key=int, reverse=True)

    # 5. 提取元数据 (基于最高版本)
    full_df['Version_Int'] = full_df['Version'].astype(int)
    metadata = full_df.sort_values('Version_Int').drop_duplicates(subset=['Class', 'Member'], keep='last').copy()

    # 处理描述
    metadata.rename(columns={'Desc': 'Desc_EN'}, inplace=True)
    def get_translated_desc(row):
        mapping_key = f"{row['Class']}:{row['Member']}"
        return translations.get(mapping_key, row['Desc_EN'])

    print("正在应用翻译...")
    metadata['Desc'] = metadata.apply(get_translated_desc, axis=1)

    if 'Access' not in metadata.columns:
        metadata['Access'] = metadata.apply(lambda r: "Method" if r['Category'] == 'Method' else "Property", axis=1)

    # 6. 透视表生成
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
    print(f"正在导出 Master Excel: {output_xlsx}")
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
    print(f"正在导出 Master CSV: {output_csv}")
    result.to_csv(output_csv, index=False, encoding='utf-8-sig')

    # 11. 拆分生成 MD
    print(f"正在拆分生成个体文档 (docs/)...")
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)

    index_list = []
    grouped = result.groupby('Class')
    
    total_classes = len(grouped)
    current_count = 0

    for class_name, group in grouped:
        current_count += 1
        if current_count % 50 == 0:
            print(f"进度: {current_count}/{total_classes} 类已处理...")

        sub_group = group.drop(columns=['Class'])
        safe_name = "".join([c for c in class_name if c.isalnum() or c == '_']).strip()
        md_filename = f"{safe_name}.md"
        md_path = os.path.join(docs_dir, md_filename)
        
        index_list.append(f"- [{class_name}](./{docs_dir}/{md_filename})")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# WMI Class: {class_name}\n\n")
            f.write(f"[⬅️ 返回类索引](../README_INDEX.md) | [📊 下载全量表 CSV](../{output_csv})\n\n")
            f.write(f"## 成员列表与兼容性报告\n\n")
            # 导出为 MD 表格
            f.write(sub_group.to_markdown(index=False))
            f.write(f"\n\n---\n*数据自动生成于: {pd.Timestamp.now().strftime('%Y-%m-%d')}*")

    # 12. 生成索引页
    print("正在生成 README_INDEX.md...")
    index_list.sort()
    with open("README_INDEX.md", 'w', encoding='utf-8') as f:
        f.write("# WMI 类快速索引\n\n")
        f.write(f"本仓库共包含 {total_classes} 个 WMI 类。点击下方类名查看详细属性与版本兼容性报告。\n\n")
        f.write("\n".join(index_list))
        f.write("\n\n---\n[🔙 返回主页](./README.md)")

    print(f"\n成功！子文档已生成在 {docs_dir}/ 文件夹下。")

if __name__ == "__main__":
    analyze_wmi_diff()