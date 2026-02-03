# WMI Class: Msvm_EthernetSwitchPortVlanSettingData

[⬅️ 返回索引](../README.md) | [📊 下载全量表 CSV](../WMI_Version_Comparison_Report.csv)

## 成员列表与兼容性对照

| Member               | Type   | Category   | Access   | 26100   | 22621   | 20348   | 19045   | 17763   | 14393   | Desc                                                                        | Desc_EN                                                                     |
|:---------------------|:-------|:-----------|:---------|:--------|:--------|:--------|:--------|:--------|:--------|:----------------------------------------------------------------------------|:----------------------------------------------------------------------------|
| AccessVlanId         | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The vlan ID in access mode.                                                 | The vlan ID in access mode.                                                 |
| Caption              | String | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | [无描述]                                                                       | [无描述]                                                                       |
| Description          | String | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | [无描述]                                                                       | [无描述]                                                                       |
| ElementName          | String | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | [无描述]                                                                       | [无描述]                                                                       |
| InstanceID           | String | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | [无描述]                                                                       | [无描述]                                                                       |
| NativeVlanId         | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The vlan ID in trunk mode.                                                  | The vlan ID in trunk mode.                                                  |
| OperationMode        | UInt32 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The vlan operation modes. [枚举值: 1 - Access; 2 - Trunk; 3 - Private]         | The vlan operation modes. [枚举值: 1 - Access; 2 - Trunk; 3 - Private]         |
| PrimaryVlanId        | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The primary vlan ID in private mode.                                        | The primary vlan ID in private mode.                                        |
| PruneVlanIdArray     | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The prune vlan ID bitmap in trunk mode.                                     | The prune vlan ID bitmap in trunk mode.                                     |
| PvlanMode            | UInt32 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The private vlan modes. [枚举值: 1 - Isolated; 2 - Community; 3 - Promiscuous] | The private vlan modes. [枚举值: 1 - Isolated; 2 - Community; 3 - Promiscuous] |
| SecondaryVlanId      | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The secondary vlan ID in private mode.                                      | The secondary vlan ID in private mode.                                      |
| SecondaryVlanIdArray | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The secondary vlan ID bitmap in private mode.                               | The secondary vlan ID bitmap in private mode.                               |
| TrunkVlanIdArray     | UInt16 | Property   | Property | ✅       | ✅       | ✅       | ✅       | ✅       | ✅       | The trunk vlan ID bitmap in trunk mode.                                     | The trunk vlan ID bitmap in trunk mode.                                     |

---
*更新日期: 2026-02-03*