# 翻译风格指南 (Translation Style Guide)

Hyper-V WMI schema 描述的中文（及后续其它语言）翻译规范。配合 [GLOSSARY.md](./GLOSSARY.md)（术语）与 `scripts/qa_lint.py`（自动质检）使用，让翻译质量**可持续、可复核**，而非一次性。

> 译文唯一真相是 `data/db/translations_zh.json`（英文原文 → 中文）。**只改这个文件**，docs/web 都是产物，改产物会丢。

---

## 1. 术语
- 一律遵循 **GLOSSARY.md**。常见：endpoint=终结点、hierarchical=分层、layered=层叠、extent=盘区、metric=度量、reference point=参考点、quiesce=停顿、replication=复制 / replica=副本、guest=来宾 / host=主机。
- 改动术语先改 GLOSSARY.md，再全量归一，不要只改个别字段。

## 2. 不翻译（DNT, Do-Not-Translate）
以下**保留英文原文**，不得翻译：
- **标识符**：类名/方法名/属性名/参数名（`Msvm_*`、`CIM_*`、`Win32_*`、`RequestedState` 等）。
- **缩写**：`NUMA`、`VHD`、`VHDX`、`SR-IOV`、`IOV`、`VMQ`、`RDMA`、`GUID`、`TPM`、`UEFI`、`BIOS`、`GPU`、`PCIe`、`SGX`、`TDX`、`CXL`、`VTL`、`RemoteFX`、`WMI`、`CIM` …（完整清单见 GLOSSARY.md「保留英文」）。
- **产品名 / 型号（枚举值常见）**：`Windows Server 2003/2008/...`、`RedHat Enterprise Linux`、`Sun Java Desktop System`、`Intel(R) Itanium(R)`、`Pentium(R) III Xeon(TM)`、`Socket A (Socket 462)` 等 OS / CPU / 插槽名。
- **代码 / 字面量**：`TRUE`/`FALSE`、数值、路径、format 占位符、原文中的转义与换行（`\n`、字面 `/n`）。

## 3. 语气与句式
- **技术中立**，陈述句。不用第二人称（避免"你/您"）：`Indicates whether...` → 「指示是否……」，不要「指示你是否……」。
- 被动语态可转主动，更通顺：`is used to control` → 「用于控制」。
- 句末用中文句号「。」。一句一义，不强行合并多句。

## 4. 标点
- 中文文本用**全角**标点：，。；：「」（）。
- 英文短语 / 标识符 / 代码内部保留**半角**：`Msvm_X`、`(value = 4)`、`0x1000`。
- 列举用「、」；中英混排时英文与中文间不强制加空格，但缩写/数字与中文之间可留半角空格以提升可读（如「4 GB 内存」）。

## 5. 数字与单位
- 阿拉伯数字保留。单位保留英文（`MB`/`GB`/`ms`/`MHz`）。`per second` → 「每秒」，`in milliseconds` → 「以毫秒为单位」。

## 6. 原文瑕疵
- 英文原文自身的**拼写/语义错误**（如 `PreapreFailover`、`to to`、`currenthost`、`does allow`）**照译，不替英文纠错**——中文里用正确的词表达即可，不在译文里复刻错别字，也不改英文原文。

## 7. 上下文例外（不要机械套术语表）
- **Extended Replication**（过程）= 扩展复制；只有 **Extended Replica**（名词）= 扩展副本。
- 数学区间 “endpoints of range / inclusively” 的 **endpoint** 保留「端点」，不改终结点。
- **node** = 节点（与 endpoint 无关）。
- 行内 `(DEPRECATED)` 标注 = 「（已弃用）」；属性/方法**标题**的废弃标记统一「（废弃）」。

---

## 8. 质量流程（让"这次好"变成"每次都好"）
1. **改译文** → 只改 `data/db/translations_zh.json`。
2. **过 lint** → 跑 `python scripts/qa_lint.py`，不通过不合入（查：覆盖、残留英文、标识符丢失、术语违规、产品名误译）。
3. **重生成产物** → `python scripts/merge.py`（如改了数据）/ `gen_bilingual_md.py`（docs）；web 实时读 JSON 无需重生成。
4. **新增 build 时走 TM（翻译记忆）复用**：
   - `translations_zh.json` 即翻译记忆（TM）。
   - 重跑 `collect_i18n.py` 得新 build 的去重串；**已在 TM 里的直接复用**（保证跨版本一致、不返工），**只翻译新增串**。
   - `qa_lint.py` 会报「TM 覆盖率」与未译清单。
5. **回译核查（可选，抓语义漂移）**：对改动批次做 ZH→EN' 与原文比对。
6. **复核**：缺母语人工时，用**与翻译时不同的模型 + 本指南作 rubric** 做对抗式复核（已实践多轮）。
