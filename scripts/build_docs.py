"""
build_docs.py — 由原始 WMI 采集数据生成对照报告与文档。

输入:
    data/raw/<build>.csv          各 Windows Build 的采集结果 (文件名即 Build 号)
    data/version_matrix.csv       人工维护的 Build × 虚拟机版本兼容矩阵
    data/translations_zh.json     中文翻译字典 (可选, 形如 "Class:Member": "译文")

输出:
    docs/<Prefix>/<Class>.md      每个 WMI 类的成员 × 版本对照表 (按类名前缀分目录)
    data/reports/comparison.csv   全量成员存在性透视表
    README.md                     首页: 版本矩阵 + 类索引

用法:
    python scripts/build_docs.py            # 生成 README 与对照报告
    python scripts/build_docs.py --docs     # 额外重新生成 docs/ 下全部类文档

说明:
    版本兼容矩阵 (data/version_matrix.csv) 为人工核对维护, 不由本脚本推算。
"""

import argparse
import csv
import glob
import json
import os
import sys
import unicodedata
from datetime import datetime

# Windows 控制台默认 GBK, 强制 UTF-8 以正常输出 emoji / 中文
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 仓库根目录 (本文件位于 scripts/ 下)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
REPORTS_DIR = os.path.join(ROOT, "data", "reports")
DOCS_DIR = os.path.join(ROOT, "docs")
ALIAS_FILE = os.path.join(ROOT, "data", "translations_zh.json")
MATRIX_FILE = os.path.join(ROOT, "data", "version_matrix.csv")
README_FILE = os.path.join(ROOT, "README.md")
REPORT_CSV = os.path.join(REPORTS_DIR, "comparison.csv")

YES, NO = "✅", "❌"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def class_prefix(cls):
    """类名前缀 (Msvm / CIM / Win32 / MSFT …), 用作 docs 子目录。"""
    return cls.split("_", 1)[0] if "_" in cls else "_misc"


def class_relpath(cls):
    """类文档相对仓库根的链接路径。"""
    return f"./docs/{class_prefix(cls)}/{cls}.md"


def load_raw():
    """读取 data/raw 下所有采集 CSV, 返回 (builds_降序, rows)。

    rows: list[dict]，每行含 Class/Member/Type/Category/Desc/Build。
    """
    files = glob.glob(os.path.join(RAW_DIR, "*.csv"))
    if not files:
        raise SystemExit(f"❌ 未在 {RAW_DIR} 找到原始 CSV")

    def build_of(path):
        # 文件名即 Build 号, 如 data/raw/29560.csv
        return int(os.path.splitext(os.path.basename(path))[0])

    files.sort(key=build_of, reverse=True)  # 新版本在前
    builds = [str(build_of(f)) for f in files]

    rows = []
    for path in files:
        b = str(build_of(path))
        log(f"读取 Build {b} …")
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                r["Build"] = b
                rows.append(r)
    log(f"共 {len(rows)} 条成员记录, 覆盖 {len(builds)} 个 Build")
    return builds, rows


def load_alias():
    if not os.path.exists(ALIAS_FILE):
        return {}
    with open(ALIAS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _dw(s):
    """显示宽度: 东亚宽字符与 emoji (✅/❌/中文) 计为 2, 与 tabulate 一致。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(s))


def _pad(s, width):
    return str(s) + " " * (width - _dw(s))


def md_table(headers, rows):
    """生成左对齐的 GitHub 管线表 (与 pandas/tabulate 'pipe' 风格一致)。"""
    widths = [_dw(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _dw(cell))
    head = "| " + " | ".join(_pad(h, widths[i]) for i, h in enumerate(headers)) + " |"
    sep = "|" + "|".join(":" + "-" * (widths[i] + 1) for i in range(len(headers))) + "|"
    body = [
        "| " + " | ".join(_pad(c, widths[i]) for i, c in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([head, sep, *body])


def build_class_docs(builds, rows, alias):
    """为每个类生成 docs/<Class>.md, 返回类名列表 (排序后)。"""
    os.makedirs(DOCS_DIR, exist_ok=True)

    # 聚合: class -> member -> 元数据, 保留首次出现顺序
    classes = {}
    for r in rows:
        cls, mem = r["Class"], r["Member"]
        c = classes.setdefault(cls, {})
        m = c.get(mem)
        if m is None:
            m = {"type": r.get("Type", ""), "desc": "", "builds": set(), "order": len(c)}
            c[mem] = m
        m["builds"].add(r["Build"])
        if not m["desc"] and r.get("Desc"):
            m["desc"] = r["Desc"]

    for cls, members in classes.items():
        headers = ["Member", "Type", *builds, "Desc", "Desc_EN"]
        table_rows = []
        for mem, m in sorted(members.items(), key=lambda kv: kv[1]["order"]):
            desc = m["desc"] or "[无描述]"
            desc_en = alias.get(f"{cls}:{mem}", desc)  # 无译文时回退英文原文
            presence = [YES if b in m["builds"] else NO for b in builds]
            table_rows.append([mem, m["type"] or "", *presence, desc, desc_en])

        safe = "".join(ch for ch in cls if ch.isalnum() or ch == "_").strip()
        subdir = os.path.join(DOCS_DIR, class_prefix(cls))
        os.makedirs(subdir, exist_ok=True)
        content = (
            f"# {cls}\n\n"
            f"[⬅️ 返回索引](../../README.md)\n\n"
            f"{md_table(headers, table_rows)}\n"
        )
        with open(os.path.join(subdir, f"{safe}.md"), "w", encoding="utf-8") as f:
            f.write(content)

    log(f"已生成 {len(classes)} 个类文档")
    return sorted(classes.keys())


def write_report_csv(builds, rows):
    """成员存在性透视表 -> data/reports/WMI_Version_Comparison_Report.csv。"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    seen = {}
    for r in rows:
        seen.setdefault((r["Class"], r["Member"]), set()).add(r["Build"])
    with open(REPORT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Class", "Member", *builds])
        for (cls, mem), bset in sorted(seen.items()):
            w.writerow([cls, mem, *[YES if b in bset else NO for b in builds]])
    log(f"已写出对照报告 {os.path.relpath(REPORT_CSV, ROOT)}")


def read_matrix():
    """读取人工维护的版本兼容矩阵, 返回 (vm_cols, rows)。"""
    with open(MATRIX_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        vm_cols = header[2:]
        rows = list(reader)
    return vm_cols, rows


def write_readme(class_names):
    vm_cols, matrix = read_matrix()

    head = "| 版本号 (Build) | 对应 Windows 发行版本 | " + " | ".join(vm_cols) + " |"
    sep = "| :--- | :--- | " + "".join(":---: | " for _ in vm_cols)
    body = []
    for row in matrix:
        build, osname, flags = row[0], row[1], row[2:]
        cells = [YES if v.strip().upper() == "Y" else NO for v in flags]
        body.append(f"| **{build}** | {osname} | " + " | ".join(cells) + " |")
    matrix_table = "\n".join([head, sep, *body])

    index = "\n".join(f"- [{c}]({class_relpath(c)})" for c in class_names)

    content = f"""# Windows WMI 版本对照报告

本仓库整理了 Windows **Hyper-V / CIM** 命名空间下 WMI 类、属性与方法在各 Build 间的版本兼容性对照表。

- 原始采集数据: [`data/raw/`](./data/raw/)（各 Build 一份 CSV）
- 全量对照报告: [`data/reports/`](./data/reports/)（CSV / XLSX）
- 各类详细文档: [`docs/`](./docs/)（共 {len(class_names)} 个类）
- 采集脚本: [`scripts/collect_wmi.ps1`](./scripts/collect_wmi.ps1) · 生成脚本: [`scripts/build_docs.py`](./scripts/build_docs.py)

## 📅 虚拟机配置版本兼容性矩阵

下表为各 Windows Build 所支持的 Hyper-V 虚拟机配置版本（列）。**该矩阵为人工核对维护**，数据源见 [`data/version_matrix.csv`](./data/version_matrix.csv)。

{matrix_table}

---

## 📂 WMI 类索引（{len(class_names)} 个）

{index}

---
*由 `scripts/build_docs.py` 生成。*
"""
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    log("已生成 README.md")


def main():
    ap = argparse.ArgumentParser(description="生成 WMI 版本对照文档")
    ap.add_argument("--docs", action="store_true", help="同时重新生成 docs/ 下全部类文档")
    args = ap.parse_args()

    log("🚀 开始构建 WMI 对照文档 …")
    builds, rows = load_raw()

    if args.docs:
        alias = load_alias()
        class_names = build_class_docs(builds, rows, alias)
        write_report_csv(builds, rows)
    else:
        # 仅刷新 README 时, 类索引取自现有 docs/ 目录 (含子目录)
        class_names = sorted(
            os.path.splitext(f)[0]
            for _, _, files in os.walk(DOCS_DIR)
            for f in files
            if f.endswith(".md")
        )

    write_readme(class_names)
    log("✅ 完成")


if __name__ == "__main__":
    main()
