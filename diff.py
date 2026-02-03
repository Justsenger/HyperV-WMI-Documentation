import pandas as pd
import glob
import os
import re
import json

def analyze_wmi_diff():
    # --- 配置区域 ---
    file_pattern = "WmiDoc_Final_*_WithEnums.csv"
    alias_file = "wmi_alias.json"
    output_xlsx = "WMI_Version_Comparison_Report.xlsx"
    output_csv = "WMI_Version_Comparison_Report.csv" # 新增 CSV 文件名

    # 1. 自动获取所有符合规则的 CSV 文件
    file_list = glob.glob(file_pattern)
    if not file_list:
        print("错误: 当前目录下未找到匹配的 CSV 文件！")
        return

    # 2. 加载翻译映射表 (JSON)
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

    # 3. 读取 CSV 数据并提取版本号
    for file_path in file_list:
        filename = os.path.basename(file_path)
        match = re.search(r"WmiDoc_Final_(\d+)_WithEnums", filename)
        if match:
            build_num = match.group(1)
            print(f"读取版本: {build_num} ({filename})")
            # 读取原始数据时建议也用 utf-8-sig
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df['Version'] = build_num
            all_dfs.append(df)
            version_list.append(build_num)

    # 4. 合并数据并处理版本顺序
    full_df = pd.concat(all_dfs, ignore_index=True)
    sorted_versions = sorted(version_list, key=int, reverse=True)

    # 5. 基于最高版本保留基础信息
    full_df['Version_Int'] = full_df['Version'].astype(int)
    metadata = full_df.sort_values('Version_Int').drop_duplicates(subset=['Class', 'Member'], keep='last').copy()

    # --- 分离中英文描述 ---
    metadata.rename(columns={'Desc': 'Desc_EN'}, inplace=True)

    def get_translated_desc(row):
        mapping_key = f"{row['Class']}:{row['Member']}"
        return translations.get(mapping_key, row['Desc_EN'])

    if translations:
        print("正在应用 Class + Member 定位翻译...")
        metadata['Desc'] = metadata.apply(get_translated_desc, axis=1)
    else:
        metadata['Desc'] = metadata['Desc_EN']

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

    # 9. 导出到 Excel
    print(f"正在导出 Excel: {output_xlsx}")
    try:
        with pd.ExcelWriter(output_xlsx, engine='openpyxl') as writer:
            result.to_excel(writer, index=False, sheet_name='WMI对比差异')
            ws = writer.sheets['WMI对比差异']
            ws.auto_filter.ref = ws.dimensions
            ws.freeze_panes = "C2"
            for i, col in enumerate(result.columns):
                col_letter = ws.cell(row=1, column=i+1).column_letter
                if col == 'Desc' or col == 'Desc_EN':
                    ws.column_dimensions[col_letter].width = 100
                else:
                    ws.column_dimensions[col_letter].width = 22
        print("Excel 导出完成。")
    except Exception as e:
        print(f"Excel 导出失败: {e}")

    # 10. 新增：直接从 Dataframe 导出到 CSV (解决勾选符号变问号的问题)
    print(f"正在导出 CSV: {output_csv}")
    try:
        # 关键点：使用 utf-8-sig 编码，这样 Excel 打开时能识别 ✅/❌ 且不会乱码
        result.to_csv(output_csv, index=False, encoding='utf-8-sig')
        print("CSV 导出完成。")
    except Exception as e:
        print(f"CSV 导出失败: {e}")

if __name__ == "__main__":
    analyze_wmi_diff()