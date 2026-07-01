# Hyper-V WMI 代码示例 — 导航索引

命名空间 `root\virtualization\v2` 的 PowerShell 调用示例，共 **113** 条，按领域分类。完整示例见 [EXAMPLES.md](EXAMPLES.md)，按类索引见 `data/db/examples.json`。

标注：`[已验证]` 表示示例可正常执行；`[需特定环境]` 表示需要相应硬件或平台支持（如 NPIV HBA、SEV-SNP CPU、RemoteFX GPU 等）。

## 读取与枚举

- [已验证] 读取宿主信息 `read_host`
- [已验证] 列出所有虚拟机 `read_vm_list`
- [已验证] 读取虚拟机的配置与资源分配 `read_vm_settings`
- [已验证] 批量获取虚拟机概览信息 `read_summary`
- [已验证] 读取可分区 GPU `read_gpu`
- [已验证] 读取可直通设备 (DDA 可分配 PCI Express 设备) `read_dda_pool`
- [已验证] 读取主机 NUMA 拓扑与容量信息 `host_numa_caps`
- [已验证] 读取处理器与 NUMA 拓扑 `processor_topology`
- [已验证] 读取主机资源容量池 `host_pools`
- [已验证] 读取来宾 KVP 键值对 `kvp_read`
- [已验证] 读取主机复制能力与配置 `replication_caps`
- [已验证] 读取并修改主机实时迁移服务设置 `live_migration_config`
- [已验证] DDA 设备直通流程与方法签名核对 `dda_dismount_doc`
- [需特定环境] 探测容器镜像管理服务类的可用性 `container_image`
- [已验证] 查询来宾群集与 VSS 集成组件信息 `vss_cluster_query`
- [已验证] 查询透明桥接服务(只读) `transparent_bridge`
- [已验证] 读取虚拟机的 VTL2/paravisor 设置 `vtl2_settings`

## 生命周期与版本

- [已验证] 虚拟机生命周期基础:创建、修改资源、删除与 Job 轮询 `_foundation`
- [已验证] 创建第一代虚拟机 `def_gen1`
- [已验证] 创建第二代虚拟机 `def_gen2`
- [已验证] 请求虚拟机状态变更 (RequestStateChange 启动与停止) `state_change`
- [已验证] 保存并恢复虚拟机状态 `save_restore_state`
- [需特定环境] 经集成组件优雅关机/重启/休眠 `graceful_shutdown`
- [已验证] 导出虚拟机定义 (ExportSystemDefinition) `export_vm`
- [已验证] 导入虚拟机定义生成计划虚拟机(ImportSystemDefinition) `import_planned`
- [已验证] 将虚拟机配置导入为计划虚拟机并校验落地为真实虚拟机 `planned_realize`
- [已验证] 读取与升级虚拟机配置版本 `config_version`
- [已验证] 读取与修改 BIOS GUID 及虚拟机 Generation ID `vmgenid_bios`
- [已验证] 端到端组合:纯 WMI 搭建完整的第二代虚拟机 `e2e_full_vm`
- [需特定环境] 校验虚拟机是否可迁移至目标主机 `migration_check`

## 处理器

- [已验证] 设置虚拟处理器数量 `cpu_count`
- [已验证] 设置 CPU 预留、上限与相对权重 `cpu_reserve_limit_weight`
- [已验证] 启用处理器功能限制 (LimitProcessorFeatures / LimitCPUID) `cpu_compat`
- [已验证] 启用嵌套虚拟化 `cpu_nested`
- [已验证] 设置每核硬件线程数 (HwThreadsPerCore) `smt_threads`

## 内存与 NUMA

- [已验证] 设置静态内存 `mem_static`
- [已验证] 启用动态内存并设置上下限 `mem_dynamic`
- [已验证] 配置虚拟机 MMIO 地址空间（GPU-P/DDA 大 BAR） `mmio_gap`
- [已验证] 配置虚拟机 NUMA 拓扑 `numa_topology`

## 存储

- [已验证] 为虚拟机添加合成 SCSI 控制器 `add_scsi`
- [已验证] 创建 VHDX 文件 `create_vhd`
- [已验证] 创建 VHDX 并挂载到虚拟机 `attach_vhd`
- [已验证] 为虚拟机添加合成 DVD 驱动器 `add_dvd`
- [已验证] 向虚拟 DVD 驱动器插入 ISO 镜像 `dvd_insert_iso`
- [已验证] 扩容VHDX虚拟磁盘 `vhd_resize`
- [已验证] 读取VHDX元数据 `vhd_info`
- [已验证] 转换VHDX类型(动态盘转固定盘) `vhd_convert`
- [已验证] 合并差分盘到父盘 `vhd_merge`
- [已验证] 压缩VHDX虚拟磁盘 `vhd_compact`
- [已验证] 校验 VHDX 磁盘完整性 `vhd_validate`
- [已验证] 为差分虚拟硬盘重新设置父盘 `vhd_setparent`
- [需特定环境] 配置共享 VHDX 与 SCSI-3 持久预留 `shared_vhd`
- [已验证] 为第一代虚拟机的软盘驱动器装入虚拟软盘 `gen1_floppy`
- [已验证] 将 VHD 挂载到主机 `mount_vhd_host`

## 网络

- [已验证] 为虚拟机添加合成网卡 `add_nic`
- [已验证] 将合成网卡接入虚拟交换机 `connect_switch`
- [已验证] 创建内部(Internal)虚拟交换机 `create_switch`
- [已验证] 为虚拟机网络适配器设置静态 MAC 地址 `mac_static`
- [已验证] 设置端口 VLAN (AccessVlanId) `vlan_set`
- [已验证] 设置虚拟网卡带宽限制 `net_bandwidth`
- [已验证] 配置虚拟网卡端口安全 (MAC 欺骗防护/DHCP 守卫/路由守卫/来宾组网) `nic_security`
- [需特定环境] 配置虚拟网卡硬件卸载 (SR-IOV/VMQ/IPsec) `nic_sriov_offload`
- [已验证] 为虚拟网卡配置扩展端口 ACL `nic_acl`
- [已验证] 配置虚拟网卡端口隔离 (Msvm_EthernetSwitchPortIsolationSettingData) `nic_isolation_pvlan`
- [已验证] 为来宾注入静态 IP(无 DHCP) `guest_network_config`

## 安全(安全启动 / vTPM / 隔离)

- [已验证] 启用或禁用虚拟机安全启动 `set_secureboot`
- [已验证] 设置安全启动模板 (SecureBootTemplateId) `secureboot_template`
- [已验证] 为第二代虚拟机启用 vTPM 安全设置 `vtpm_security`
- [已验证] 创建启用来宾状态隔离的机密虚拟机(GuestStateIsolationType) `guest_isolation`
- [已验证] 为第一代虚拟机启用密钥存储驱动器 `key_storage_drive`

## GPU 分区与设备直通

- [已验证] 为虚拟机添加 GPU 分区(GPU-P) `gpu_partition`
- [已验证] 为 GPU 分区(GPU-P)写入显存配额 `gpu_partition_vram`
- [已验证] 指定一块可分区 GPU 并分配分区(含主机侧 PartitionCount) `gpu_specific_assign`
- [已验证] 按比例设置 GPU 分区显存配额 `gpu_vram_fraction`
- [需特定环境] 在主机侧启用 RemoteFX GPU 虚拟化 `synth3d_enable`
- [需特定环境] 为虚拟机添加合成光纤通道适配器 (虚拟 HBA) `fibre_channel`
- [已验证] 为虚拟机添加虚拟持久内存(PMEM)控制器 `pmem_controller`
- [需特定环境] 添加 RemoteFX 3D 显示控制器(旧机制) `remotefx_3d`
- [已验证] 为虚拟机添加合成电池 `battery_setting`

## 快照与备份

- [已验证] 创建虚拟机检查点 `snapshot_create`
- [已验证] 应用虚拟机检查点 `snapshot_apply`
- [已验证] 重命名并读取检查点 `snapshot_rename`
- [已验证] 导出单个检查点定义 `snapshot_export`
- [已验证] 删除检查点子树 (DestroySnapshotTree) `snapshot_tree_delete`
- [已验证] 创建参考点(增量备份与变更块跟踪 RCT) `reference_point`
- [需特定环境] 创建虚拟机集合级快照 `collection_snapshot`
- [需特定环境] 创建集合级参考点(增量备份/CBT) `collection_refpoint`

## 配置、集成服务与输入

- [已验证] 重命名虚拟机 `rename_vm`
- [已验证] 设置虚拟机备注 (VSSD.Notes) `set_notes`
- [已验证] 设置虚拟机自动启动与自动停止动作 `set_autostart`
- [已验证] 设置虚拟机自动启动延迟与故障恢复操作 `automatic_actions`
- [已验证] 设置检查点类型(生产/标准) `checkpoint_type`
- [已验证] 设置虚拟机启动顺序 `boot_order`
- [已验证] 配置第一代虚拟机的 BIOS 与启动顺序 `gen1_bios`
- [已验证] 配置虚拟机串口连接命名管道 `serial_com`
- [已验证] 为双串口分别配置命名管道 `serial_pipe_full`
- [已验证] 切换集成服务组件启用状态 `integration_services`
- [已验证] 启用来宾服务接口组件 `guest_services`
- [已验证] 启用与调用来宾集成服务 `guest_service_control`
- [已验证] 从主机向来宾推送 KVP 键值对 `kvp_push`
- [已验证] 配置合成显示控制器分辨率 `video_display`
- [已验证] 设置虚拟机的增强会话传输类型 `enhanced_session`
- [已验证] 向虚拟机注入键盘输入 `keyboard_input`
- [已验证] 向虚拟机注入鼠标输入 `mouse_input`
- [已验证] 向虚拟机发送 Ctrl+Alt+Del `cad_input`

## 管理与运维

- [已验证] 修改主机管理服务设置(ModifyServiceSettings) `host_settings`
- [已验证] 创建自定义资源池 `resource_pool_create`
- [需特定环境] 创建子资源池 `resource_pool_child`
- [已验证] 创建虚拟机集合并添加成员 `vm_groups`
- [已验证] 启用与禁用虚拟机资源度量 `metrics_enable`
- [需特定环境] 获取虚拟机缩略图 `thumbnail_screenshot`
- [已验证] 管理增强会话终端设置与交互式会话访问控制 `terminal_access`
- [已验证] 异步作业轮询范式 `job_pattern`
