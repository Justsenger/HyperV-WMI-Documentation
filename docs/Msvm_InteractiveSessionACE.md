# WMI Class: Msvm_InteractiveSessionACE

[⬅️ 返回类索引](../README_INDEX.md) | [📊 下载全量表 CSV](../WMI_Version_Comparison_Report.csv)

## 成员列表与兼容性报告

| Member     | Type   | Category   | Access   | 26100   | 22621   | 20348   | 19045   | 17763   | 14393   | Desc                                                                                                                                                                                              | Desc_EN                                                                                                                                                                                           |
|:-----------|:-------|:-----------|:---------|:--------|:--------|:--------|:--------|:--------|:--------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| AccessType | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | Indicates whether the ACE grants or denies access to the trustee. [枚举值: 0 - Access Allowed; 1 - Access Denied]                                                                                    | Indicates whether the ACE grants or denies access to the trustee. [枚举值: 0 - Access Allowed; 1 - Access Denied]                                                                                    |
| Trustee    | String | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | Identifies the security principal that the ACE grants or denies access to. Valid formats for this property include the Windows SAM-compatible user name format and the Windows SID string format. | Identifies the security principal that the ACE grants or denies access to. Valid formats for this property include the Windows SAM-compatible user name format and the Windows SID string format. |

---
*数据自动生成于: 2026-02-03*