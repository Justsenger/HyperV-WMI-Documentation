# Hyper-V WMI 术语表 (Glossary)

英文为主键的统一译名表，用于保证全部字段术语一致，并作为翻译成其它语言的基准。
**新增语言**：在每个表格加一列即可，例如 `| ja | de |`。

> 核心术语 124 + 扩充领域术语 204 + 保留英文缩写 59。


## 虚拟化核心

| English | 中文 (zh) | 说明 |
|---|---|---|
| virtual machine | 虚拟机 |  |
| virtual system | 虚拟系统 |  |
| hypervisor | 虚拟机监控程序 |  |
| host | 主机 |  |
| guest | 来宾 |  |
| partition | 分区 |  |
| nested virtualization | 嵌套虚拟化 |  |
| hierarchical | 分层 | 与 layered 区分 |
| layered | 层叠 | 与 hierarchical 区分 |
| generation | 代 | 第一代/第二代 |
| virtualization extension | 虚拟化扩展 |  |

## 快照/复制/迁移

| English | 中文 (zh) | 说明 |
|---|---|---|
| snapshot | 快照 |  |
| checkpoint | 检查点 |  |
| reference point | 参考点 |  |
| replication | 复制 | 过程 |
| replica | 副本 | 名词,被复制出的对象 |
| failover | 故障转移 |  |
| failback | 故障回切 |  |
| migration | 迁移 |  |
| live migration | 实时迁移 |  |
| storage migration | 存储迁移 |  |
| recovery | 恢复 |  |
| collection | 集合 |  |
| primordial | 原始 |  |
| consumer | 使用者 | CIM 语境 |

## 计算资源

| English | 中文 (zh) | 说明 |
|---|---|---|
| processor | 处理器 |  |
| virtual processor | 虚拟处理器 |  |
| memory | 内存 |  |
| resource pool | 资源池 |  |
| setting data | 设置数据 |  |
| allocation | 分配 |  |
| weight | 权重 |  |
| reservation | 预留 |  |
| limit | 限制 |  |
| quota | 配额 |  |
| socket | 插槽 |  |
| core | 核心 |  |
| thread | 线程 |  |

## 存储

| English | 中文 (zh) | 说明 |
|---|---|---|
| virtual hard disk | 虚拟硬盘 |  |
| extent | 盘区 | CIM StorageExtent |
| storage | 存储 |  |
| disk | 磁盘 |  |
| drive | 驱动器 |  |
| volume | 卷 |  |
| logical disk | 逻辑磁盘 |  |
| storage pool | 存储池 |  |
| persistent memory | 持久内存 |  |

## 网络

| English | 中文 (zh) | 说明 |
|---|---|---|
| ethernet switch | 以太网交换机 |  |
| virtual switch | 虚拟交换机 |  |
| switch port | 交换机端口 |  |
| endpoint | 终结点 | 微软标准译法;数学区间端点除外 |
| network adapter | 网络适配器 |  |
| ethernet port | 以太网端口 |  |
| teaming | 组合 |  |
| offload | 卸载 |  |
| bandwidth | 带宽 |  |
| isolation | 隔离 |  |
| forwarding | 转发 |  |
| bridging | 桥接 |  |

## 安全

| English | 中文 (zh) | 说明 |
|---|---|---|
| shielded | 受防护 |  |
| key protector | 密钥保护程序 |  |
| security | 安全 |  |
| encryption | 加密 |  |
| attestation | 证明 |  |
| secure boot | 安全启动 |  |
| speculative execution | 推测执行 |  |

## CIM/WMI 结构

| English | 中文 (zh) | 说明 |
|---|---|---|
| class | 类 |  |
| property | 属性 |  |
| method | 方法 |  |
| parameter | 参数 |  |
| association | 关联 |  |
| instance | 实例 |  |
| qualifier | 限定符 |  |
| enumeration | 枚举 |  |
| reference | 引用 |  |
| capabilities | 功能 |  |
| service | 服务 |  |
| job | 作业 |  |
| provider | 提供程序 |  |
| element | 元素 |  |
| setting | 设置 |  |
| component | 组件 |  |
| collection | 集合 |  |

## 状态/状况

| English | 中文 (zh) | 说明 |
|---|---|---|
| enabled | 已启用 |  |
| disabled | 已禁用 |  |
| state | 状态 |  |
| status | 状态 |  |
| operational status | 运行状态 |  |
| health state | 运行状况状态 |  |
| requested state | 请求的状态 |  |
| enabled state | 启用状态 |  |
| transition | 转换 |  |

## 通用动作

| English | 中文 (zh) | 说明 |
|---|---|---|
| indicate | 指示 |  |
| represent | 表示 |  |
| specify | 指定 |  |
| configure | 配置 |  |
| request | 请求 |  |
| support | 支持 |  |
| retrieve | 检索 |  |
| define | 定义 |  |
| modify | 修改 |  |
| create | 创建 |  |
| destroy | 销毁 |  |
| export | 导出 |  |
| import | 导入 |  |
| deprecated | 弃用 |  |

## 度量与补充

| English | 中文 (zh) | 说明 |
|---|---|---|
| metric | 度量 | 区别 metric value |
| metric value | 度量值 |  |
| metric definition | 度量定义 |  |
| managed element | 受管元素 |  |
| boot source | 启动源 |  |
| pointing device | 指针设备 |  |
| access point | 访问点 |  |
| saved state | 已保存状态 |  |
| controller | 控制器 |  |
| namespace | 命名空间 |  |
| firmware | 固件 |  |
| cluster | 群集 |  |
| fibre channel | 光纤通道 |  |
| subnet | 子网 |  |
| container image | 容器映像 |  |
| gpu partition | GPU 分区 |  |
| friendly name | 友好名称 |  |
| trunk | 中继 |  |

## 扩充领域术语（agent 逐字段抽取，按出现频次）

| English | 中文 (zh) | 频次 | 备选 |
|---|---|---|---|
| block size | 块大小 | 10 |  |
| numa node | NUMA 节点 | 8 |  |
| recovery server | 恢复服务器 | 8 |  |
| container | 容器 | 7 |  |
| media | 介质 | 7 |  |
| vram | VRAM | 7 |  |
| trunking mode | 中继模式 | 6 |  |
| test replica | 测试副本 | 6 |  |
| compute engine | 计算引擎 | 6 |  |
| decode engine | 解码引擎 | 6 |  |
| encode engine | 编码引擎 | 6 |  |
| forwarding database | 转发数据库 | 5 |  |
| indication | 指示 | 5 |  |
| superclass | 超类 | 5 |  |
| cardinality | 基数 | 5 |  |
| replication relationship | 复制关系 | 5 |  |
| node | 节点 | 5 |  |
| guest service interface | 来宾服务接口 | 5 |  |
| octet | 八位字节 | 5 |  |
| subclass | 子类 | 4 |  |
| logical device | 逻辑设备 | 4 |  |
| service access point | 服务访问点 | 4 |  |
| switch extension | 交换机扩展 | 4 |  |
| transparent bridging | 透明桥接 | 4 |  |
| serial controller | 串行控制器 | 4 |  |
| timestamp | 时间戳 | 4 |  |
| display controller | 显示控制器 | 4 |  |
| network port | 网络端口 | 4 |  |
| interactive session | 交互式会话 | 4 |  |
| guest cluster | 来宾群集 | 4 |  |
| hba | HBA | 4 |  |
| virtual system configuration | 虚拟系统配置 | 4 |  |
| vrss | VRSS | 4 |  |
| transport type | 传输类型 | 4 |  |
| queue | 队列 | 4 |  |
| serial port | 串行端口 | 3 |  |
| floppy controller | 软盘控制器 | 3 |  |
| video controller | 视频控制器 | 3 |  |
| computer system | 计算机系统 | 3 |  |
| primary server | 主服务器 | 3 |  |
| resource type | 资源类型 | 3 |  |
| aggregation | 聚合 | 3 |  |
| assignable device | 可分配设备 | 3 |  |
| protocol controller | 协议控制器 | 3 |  |
| connection point | 连接点 | 3 |  |
| synthetic | 合成 | 3 |  |
| offline | 脱机 | 3 |  |
| port | 端口 | 3 |  |
| disk merge | 磁盘合并 | 3 |  |
| flex io device | Flex IO 设备 | 3 |  |
| heartbeat | 检测信号 | 3 |  |
| port profile | 端口配置文件 | 3 |  |
| profile | 配置文件 | 3 |  |
| sap | SAP | 3 |  |
| logical unit | 逻辑单元 | 3 |  |
| crash consistent | 崩溃一致 | 3 |  |
| interface | 接口 | 3 |  |
| recovery snapshot | 恢复快照 | 3 |  |
| initial replication | 初始复制 | 3 |  |
| planned computer system | 计划计算机系统 | 3 |  |
| parent pool | 父池 | 3 |  |
| application consistent | 应用程序一致 | 3 |  |
| descriptor | 描述符 | 3 |  |
| pool | 池 | 3 |  |
| feature setting | 功能设置 | 3 |  |
| video memory | 视频内存 | 3 |  |
| resolution | 分辨率 | 3 |  |
| removable media | 可移动介质 | 3 |  |
| authentication | 身份验证 | 3 |  |
| refresh rate | 刷新率 | 3 |  |
| address space | 地址空间 | 3 |  |
| virtual function | 虚拟函数 | 3 |  |
| default queue | 默认队列 | 3 |  |
| synthetic hba | 合成 HBA | 3 |  |
| serial number | 序列号 | 3 |  |
| vf | VF | 3 |  |
| queue pair | 队列对 | 3 |  |
| trunk mode | 中继模式 | 3 |  |
| frame | 帧 | 2 |  |
| alert | 警报 | 2 |  |
| admission control | 准入控制 | 2 |  |
| base class | 基类 | 2 |  |
| media access device | 介质访问设备 | 2 |  |
| alert indication | 警报指示 | 2 |  |
| trunking | 中继 | 2 |  |
| video head | 视频头 | 2 |  |
| terminal connection | 终端连接 | 2 |  |
| abstract class | 抽象类 | 2 |  |
| schema | schema | 2 |  |
| dedicated | 独占 | 2 |  |
| shared | 共享 | 2 |  |
| weak association | 弱关联 | 2 |  |
| baud rate | 波特率 | 2 |  |
| aggregation function | 聚合函数 | 2 |  |
| servicing operation | 维护操作 | 2 |  |
| remote session | 远程会话 | 2 |  |
| network stack | 网络栈 | 2 |  |
| bus | 总线 | 2 |  |
| storage image | 存储映像 | 2 |  |
| image | 映像 | 2 |  |
| network connectivity | 网络连接 | 2 |  |
| pass-through device | 直通设备 | 2 |  |
| fibre channel switch | 光纤通道交换机 | 2 |  |
| synthetic ethernet adapter | 合成以太网适配器 | 2 |  |
| emulated ethernet adapter | 模拟以太网适配器 | 2 |  |
| ide controller | IDE 控制器 | 2 |  |
| virtual battery | 虚拟电池 | 2 |  |
| virtual computer system | 虚拟计算机系统 | 2 |  |
| extension component | 扩展组件 | 2 |  |
| volume shadow copy service | 卷影复制服务 | 2 |  |
| routing domain | 路由域 | 2 |  |
| parent partition | 父分区 | 2 |  |
| metric service | 度量服务 | 2 |  |
| native vlan | 本机 VLAN | 2 |  |
| protocol endpoint | 协议终结点 | 2 |  |
| forwarding entry | 转发条目 | 2 |  |
| compatibility vector | 兼容性向量 | 2 |  |
| member | 成员 | 2 |  |
| chassis manager | 机箱管理器 | 2 |  |
| compaction | 压缩 | 2 |  |
| consistency checker | 一致性检查器 | 2 |  |
| integrity | 完整性 | 2 |  |
| performance | 性能 | 2 |  |
| gateway | 网关 | 2 |  |
| multicast | 多播 | 2 |  |
| power cycle | 电源循环 | 2 |  |
| rct | RCT | 2 |  |
| delta | 增量 | 2 |  |
| save state | 保存状态 | 2 |  |
| snapshot collection | 快照集合 | 2 |  |
| storage device enclosure | 存储设备机箱 | 2 |  |
| tape drive | 磁带驱动器 | 2 |  |
| unicast | 单播 | 2 |  |
| vmbus | VMBus | 2 |  |
| video processor | 视频处理器 | 2 |  |
| key-value pair | 键值对 | 2 |  |
| virtual disk image | 虚拟磁盘映像 | 2 |  |
| integration component | 集成组件 | 2 |  |
| planned virtual system | 计划虚拟系统 | 2 |  |
| container image repository | 容器映像存储库 | 2 |  |
| vhd snapshot | VHD 快照 | 2 |  |
| trustee | 受信者 | 2 |  |
| disk image | 磁盘映像 | 2 |  |
| hibernate | 休眠 | 2 |  |
| sample interval | 采样间隔 | 2 |  |
| backing store | 后备存储 | 2 |  |
| return code | 返回码 | 2 |  |
| thumbnail | 缩略图 | 2 |  |
| child pool | 子池 | 2 |  |
| power state | 电源状态 | 2 |  |
| credential | 凭据 | 2 |  |
| online | 联机 | 2 |  |
| quiesce | 停顿 | 2 |  |
| data root | 数据根目录 | 2 |  |
| embedded instance | 内嵌实例 | 2 |  |
| timeout period | 超时期限 | 2 |  |
| guest service | 来宾服务 | 2 |  |
| migration policy | 迁移策略 | 2 |  |
| data protection | 数据保护 | 2 |  |
| resource sub-type | 资源子类型 | 2 |  |
| scan mode | 扫描模式 | 2 |  |
| recovery action | 恢复操作 | 2 |  |
| vlan encapsulation | VLAN 封装 | 2 |  |
| video architecture | 视频体系结构 | 2 |  |
| link technology | 链路技术 | 2 |  |
| power management | 电源管理 | 2 |  |
| topology | 拓扑 | 2 |  |
| worker process | 工作进程 | 2 |  |
| read-only | 只读 | 2 |  |
| thumbprint | 指纹 | 2 |  |
| load balancing | 负载均衡 | 2 |  |
| breakdown dimension | 分解维度 | 2 |  |
| virtual subnet | 虚拟子网 | 2 |  |
| broadcast | 广播 | 2 |  |
| encryption method | 加密方法 | 2 |  |
| read-only property | 只读属性 | 2 |  |
| runtime state | 运行时状态 | 2 |  |
| replication type | 复制类型 | 2 |  |
| disk drive | 磁盘驱动器 | 2 |  |
| static mac address | 静态 MAC 地址 | 2 |  |
| dynamic memory | 动态内存 | 2 |  |
| guest state | 来宾状态 | 2 |  |
| virtual numa node | 虚拟 NUMA 节点 | 2 |  |
| vendor | 供应商 | 2 |  |
| differencing disk | 差异磁盘 | 2 |  |
| resilient change tracking | 弹性更改跟踪 | 2 |  |
| extended acl | 扩展 ACL | 2 |  |
| replication cycle | 复制周期 | 2 |  |
| memory block | 内存块 | 2 |  |
| unicast address | 单播地址 | 2 |  |
| resource allocation setting data | 资源分配设置数据 | 2 |  |
| alignment | 对齐方式 | 2 |  |
| key | 键 | 2 |  |
| prefix length | 前缀长度 | 2 |  |
| launch control | 启动控制 | 2 |  |
| maximum transmission unit | 最大传输单元 | 2 |  |
| memory-mapped io gap | 内存映射 IO 间隙 | 2 |  |
| environment variable | 环境变量 | 2 |  |
| chassis | 机箱 | 2 |  |
| switching mode | 交换模式 | 2 |  |
| latency | 延迟 | 2 |  |
| sector size | 扇区大小 | 2 |  |
| private mode | 专用模式 | 2 |  |
| synthetic debugging | 合成调试 | 2 |  |

## 保留英文（不翻译）

标识符（类名/方法名/属性名 `Msvm_*`/`CIM_*`/`Win32_*`）与下列缩写一律保留英文：

`NUMA`、`vNUMA`、`VHD`、`VHDX`、`VHD Set`、`SR-IOV`、`IOV`、`VMQ`、`VMMQ`、`RSS`、`vRSS`、`RDMA`、`RoCE`、`GUID`、`TPM`、`UEFI`、`BIOS`、`VLAN`、`PVLAN`、`QoS`、`IPsec`、`SMB`、`SMB3`、`KVP`、`VSS`、`RDP`、`FC`、`FCoE`、`SCSI`、`IDE`、`GPU`、`vGPU`、`PCI Express`、`PCIe`、`MMIO`、`SGX`、`TDX`、`CXL`、`DMA`、`IOMMU`、`PMU`、`SMT`、`NIC`、`MAC`、`DHCP`、`IP`、`IPv4`、`IPv6`、`ACL`、`WMI`、`CIM`、`DMTF`、`ACPI`、`NVMe`、`ARM64`、`x64`、`VTL`、`RemoteFX`、`DDA`


## ⚠️ 上下文例外（不要机械套用名词表）

- **Extended Replication**（复制过程/关系）= 扩展复制；只有 **Extended Replica**（名词）才是「扩展副本」。
- 数学区间 “inclusively / endpoints of range” 的 **endpoint** 保留译「端点」，不改「终结点」。
- **node** = 节点（与 endpoint 无关，勿改）。
- 行内 `(DEPRECATED)` 标注译「（已弃用）」；属性/方法**标题**的废弃标记统一为「（废弃）」。
- **Replica**（名词，被复制出的对象）= 副本；**replication**（过程）= 复制，勿混。