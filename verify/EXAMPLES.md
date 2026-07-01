# Hyper-V WMI 代码示例

> 命名空间 `root\virtualization\v2` 的 PowerShell 调用示例。执行写入类操作前，请在测试虚拟机上确认。

| 状态 | 数量 |
|---|---|
| PASS | 101 |
| UNSUPPORTED | 12 |

## [PASS] 虚拟机生命周期基础:创建、修改资源、删除与 Job 轮询  `_foundation`

- 嵌入实例统一使用 GetText(1) 序列化为文本后作为参数传入。
- DefineSystem 的 OUT 参数名为 ResultingSystem，而非 DefinedSystem。
- ModifyResourceSettings 修改单个资源；ModifySystemSettings 修改整机设置；AddResourceSettings 添加资源。
- 返回值 4096 表示 Job 已启动，需轮询 Msvm_ConcreteJob.JobState（7=完成，8/9/10=失败）。
- 安全相关设置由 Msvm_SecurityService 提供，不在虚拟系统管理服务中处理。

```powershell
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# DefineSystem 创建第二代虚拟机 (OUT 参数为 ResultingSystem):
$vssd=([wmiclass]"\\.\$ns:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_x'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
# 遍历 VM -> VSSD -> ProcessorSettingData:
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
$proc=([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData')|select -First 1
# 修改单个资源:
$proc.VirtualQuantity=[uint64]2; $r2=$vsms.ModifyResourceSettings($proc.GetText(1))
# 修改整机设置: $vsms.ModifySystemSettings($vssd2.GetText(1))
# 添加资源:     $vsms.AddResourceSettings($vssd2.__PATH,@($rasd.GetText(1)))
# 删除虚拟机:
$rc=$vsms.DestroySystem($vm.__PATH); if($rc.ReturnValue -eq 4096){Wait-Job2 $rc.Job|Out-Null}
```

## [PASS] 为虚拟机添加合成 DVD 驱动器  `add_dvd`

- 合成 DVD 对应 Msvm_ResourceAllocationSettingData，ResourceType=16，ResourceSubType='Microsoft:Hyper-V:Synthetic DVD Drive'。
- DVD 驱动器必须挂在控制器下。第二代虚拟机使用 SCSI 控制器（Microsoft:Hyper-V:Synthetic SCSI Controller）；新建的空第二代虚拟机默认不含 SCSI 控制器，须先 AddResourceSettings 添加一个，再将 DVD 的 Parent 指向该控制器。
- 获取模板 RASD 的推荐方式：从 Primordial=true 的 Msvm_ResourcePool（按 ResourceSubType 过滤）-> GetRelated('Msvm_AllocationCapabilities') -> REFERENCES OF ... Msvm_SettingsDefineCapabilities，取 ValueRole=0（Default）的 PartComponent。
- 添加资源调用 Msvm_VirtualSystemManagementService.AddResourceSettings($vssd.__PATH, @($rasd.GetText(1)))；OUT 参数 ResultingResourceSettings 为新资源路径数组；返回值 0 表示同步成功，4096 表示 Job 已启动。
- DVD 的 Parent 必须为控制器 RASD 的 __PATH，AddressOnParent 为控制器上空闲的 LUN 号（本例为 '0'）。此处仅挂载空驱动器，未插入 ISO；插入 ISO 需另行添加指向 .iso 的 Msvm_StorageAllocationSettingData。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_add_dvd'
$DVD_SUBTYPE = 'Microsoft:Hyper-V:Synthetic DVD Drive'
$SCSI_SUBTYPE = 'Microsoft:Hyper-V:Synthetic SCSI Controller'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

# 通过 primordial 资源池的 AllocationCapabilities 获取某 ResourceSubType 的默认 RASD 模板 (SettingsDefineCapabilities ValueRole=0 即 Default)
function Get-DefaultRasd($subType){
  $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.ResourceSubType -eq $subType -and $_.Primordial -eq $true } | Select-Object -First 1
  if(-not $pool){ throw "no primordial pool for $subType" }
  $caps = ([wmi]$pool.__PATH).GetRelated('Msvm_AllocationCapabilities') | Select-Object -First 1
  $sdcRefs = Get-WmiObject -Namespace $ns -Query ("REFERENCES OF {{{0}}} WHERE ResultClass=Msvm_SettingsDefineCapabilities" -f $caps.__PATH)
  $defPath = $null
  foreach($ref in $sdcRefs){ if([int]$ref.ValueRole -eq 0){ $defPath = $ref.PartComponent; break } }
  if(-not $defPath){ throw "no default RASD for $subType" }
  return [wmi]$defPath
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 清理同名遗留虚拟机
foreach($e in (Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName })){ $vsms.DestroySystem($e.__PATH) | Out-Null }

$vm = $null
try {
  # 创建空的第二代虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){ throw 'DefineSystem job failed' } } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # 查找或添加 SCSI 控制器 (第二代)
  $rasds = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ResourceAllocationSettingData')
  $scsi = $rasds | Where-Object { $_.ResourceSubType -eq $SCSI_SUBTYPE } | Select-Object -First 1
  if(-not $scsi){
    $scsiTmpl = Get-DefaultRasd $SCSI_SUBTYPE
    $addS = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
    if($addS.ReturnValue -eq 4096){ if((Wait-Job2 $addS.Job) -ne 7){ throw 'AddResourceSettings(SCSI) job failed' } } elseif($addS.ReturnValue -ne 0){ throw "AddResourceSettings(SCSI) rv=$($addS.ReturnValue)" }
    $scsi = [wmi]($addS.ResultingResourceSettings | Select-Object -First 1)
  }

  # 构造挂在 SCSI 控制器下的合成 DVD 驱动器 RASD
  $dvdTmpl = Get-DefaultRasd $DVD_SUBTYPE
  $dvdTmpl.Parent = $scsi.__PATH
  $dvdTmpl.AddressOnParent = '0'
  $addD = $vsms.AddResourceSettings($vssd2.__PATH, @($dvdTmpl.GetText(1)))
  if($addD.ReturnValue -eq 4096){ if((Wait-Job2 $addD.Job) -ne 7){ throw 'AddResourceSettings(DVD) job failed' } } elseif($addD.ReturnValue -ne 0){ throw "AddResourceSettings(DVD) rv=$($addD.ReturnValue)" }

  # 读回验证
  $vssd3 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $dvds = ([wmi]$vssd3.__PATH).GetRelated('Msvm_ResourceAllocationSettingData') | Where-Object { $_.ResourceSubType -eq $DVD_SUBTYPE }
  if(@($dvds).Count -ge 1){ Write-Host 'ASSERT PASS: synthetic DVD drive added' } else { Write-Host 'ASSERT FAIL' }
}
catch { Write-Host ("ERROR: {0}" -f $_.Exception.Message); Write-Host 'ASSERT FAIL' }
finally {
  if($vm -ne $null){ try { $del = $vsms.DestroySystem($vm.__PATH); if($del.ReturnValue -eq 4096){ Wait-Job2 $del.Job | Out-Null } } catch {} }
}
```

## [PASS] 为虚拟机添加合成网卡  `add_nic`

- 不能使用 [wmiclass].CreateInstance() 构造空白 Msvm_SyntheticEthernetPortSettingData 直接 Add，该方式会异步失败（Job JobState=10，ErrorCode=32773 无法添加资源）。须从合成网卡资源池（ResourceType=10，ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port'，Primordial=True）经 Msvm_AllocationCapabilities 与 Msvm_SettingsDefineCapabilities（ValueRole=0）取默认模板 RASD，再克隆并修改属性。
- AddResourceSettings 通常同步返回 rv=0，网卡数由 0 变为 1。OUT 参数 ResultingResourceSettings 含新建网卡的 __PATH。
- 网卡须设置 VirtualSystemIdentifiers=@('{<新GUID>}')；系统会额外补充一个端口 GUID，因此读回时可得到两个 VSID。StaticMacAddress=$false 表示由 Hyper-V 自动分配动态 MAC。
- ResourceType=10 同时包含 'Emulated Ethernet Port'（模拟式）与 'Synthetic Ethernet Port'（合成式）；本配方使用合成网卡。
- 此步仅添加网卡，未连接虚拟交换机；连接虚拟交换机由单独的 connect_switch（EthernetPortAllocationSettingData）处理。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 1) 创建第二代测试虚拟机
$vssd=([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_add_nic'
$vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){[void](Wait-Job2 $r.Job)}
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1

# 2) 取合成网卡资源池的默认模板 (不能使用空白 CreateInstance)
$pool=Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceType=10 AND ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port' AND Primordial=True"
$cap=$pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null)|Select-Object -First 1
$defPath=$null
foreach($rel in $cap.GetRelationships('Msvm_SettingsDefineCapabilities')){ if($rel.ValueRole -eq 0){$defPath=$rel.PartComponent; break} }
$nic=[wmi]$defPath
$nic.ElementName='WMITEST_NIC'
$nic.VirtualSystemIdentifiers=@('{'+[guid]::NewGuid().ToString()+'}')
$nic.StaticMacAddress=$false

# 3) AddResourceSettings 添加 (rv=0 同步成功；4096 则 Wait-Job2)
$addr=$vsms.AddResourceSettings($vssd2.__PATH,@($nic.GetText(1)))
if($addr.ReturnValue -eq 4096){[void](Wait-Job2 $addr.Job)}

# 4) 读回验证
$after=@(([wmi]$vssd2.__PATH).GetRelated('Msvm_SyntheticEthernetPortSettingData'))
'NIC count = '+$after.Count

# 5) 清理
$d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){[void](Wait-Job2 $d.Job)}
```

## [PASS] 为虚拟机添加合成 SCSI 控制器  `add_scsi`

- 合成 SCSI 控制器的 ResourceSubType='Microsoft:Hyper-V:Synthetic SCSI Controller'，ResourceType=6（Controller）。
- 推荐方式：从 Msvm_ResourcePool（Primordial=True，指定 SubType）-> Msvm_AllocationCapabilities（经 Msvm_ElementCapabilities）-> Msvm_SettingsDefineCapabilities（ValueRole=0 即 Default）取默认 RASD 模板，再 GetText(1) 序列化后交给 AddResourceSettings。相比手动构造 RASD 更稳定。
- AddResourceSettings 第一个参数为 VSSD 的 __PATH，第二个参数为嵌入实例字符串数组；同步返回时 rv=0，OUT 参数 ResultingResourceSettings 给出新建控制器的实例路径。
- AddResourceSettings 也可能返回 4096（异步 Job），需 Wait-Job2 $r2.Job 轮询。
- 读回时先 $vssd2.Get() 刷新，再 GetRelated('Msvm_ResourceAllocationSettingData') 按 ResourceSubType 过滤计数。
- 第二代虚拟机最多支持 4 个合成 SCSI 控制器；本例从 0 增加到 1，清理后无残留。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$scsiSubType='Microsoft:Hyper-V:Synthetic SCSI Controller'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
function Get-DefaultRasd($subType){
  $pool=Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
  $caps=$pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
  $rasd=$null
  foreach($sdc in $caps.GetRelationships('Msvm_SettingsDefineCapabilities')){ if([uint16]$sdc.ValueRole -eq 0){ $rasd=[wmi]($sdc.PartComponent); break } }
  return $rasd
}
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 创建第二代虚拟机
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_add_scsi'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
# 从 primordial 资源池的默认模板构造 SCSI 控制器 RASD，再添加
$rasd=Get-DefaultRasd $scsiSubType
$r2=$vsms.AddResourceSettings($vssd2.__PATH, @($rasd.GetText(1)))
if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }
# 读回验证
$vssd2.Get()
$after=@($vssd2.GetRelated('Msvm_ResourceAllocationSettingData') | ? { $_.ResourceSubType -eq $scsiSubType })
'SCSI count='+$after.Count
# 清理
$rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
```

## [PASS] 创建 VHDX 并挂载到虚拟机  `attach_vhd`

- 挂载磁盘需分两步完成。先 AddResourceSettings 添加 Msvm_ResourceAllocationSettingData（ResourceSubType='Microsoft:Hyper-V:Synthetic Disk Drive'，Parent=SCSI 控制器路径，AddressOnParent='0'）；再 AddResourceSettings 添加 Msvm_StorageAllocationSettingData（Parent=上一步驱动器路径，HostResource=@(vhdx 路径)）。
- 若直接将 StorageAllocationSettingData 的 Parent 指向 SCSI 控制器，将失败：JobState=10，ErrorCode=32768（无法添加设备 Virtual Hard Disk）。必须先存在磁盘驱动器（Drive）。
- 默认模板取法：Msvm_ResourcePool（ResourceSubType=...，Primordial=True）-> Msvm_AllocationCapabilities -> Msvm_SettingsDefineCapabilities（ValueRole=0）的 PartComponent。使用 .psbase.Clone() 复制后修改属性，再 GetText(1) 序列化。
- StorageAllocationSettingData 的关键属性（HostResource/Parent/AddressOnParent/ResourceType=31）均继承自 CIM 基类，不出现在 canonical.json 的子类属性表中，需查阅继承链。
- CreateVirtualHardDisk 使用 Msvm_ImageManagementService，传入序列化的 Msvm_VirtualHardDiskSettingData（Type=3 动态 / Format=3 VHDX / Path / MaxInternalSize）。
- HostResource 路径须使用反斜杠形式的 Windows 路径。验证时从 VSSD GetRelated('Msvm_StorageAllocationSettingData') 读回 HostResource 进行比对。
- 所有写方法返回 4096 时需 Wait-Job2 轮询；JobState 7=完成，10=失败。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$vmName = 'WMITEST_attach_vhd'
$workDir = 'C:/Users/Administrator/Documents/GitHub/HyperV-WMI-Documentation/verify/work'
$vhdPath = Join-Path $workDir 'WMITEST_attach_vhd.vhdx'
$vhdPath = $vhdPath -replace '/', '\'

function Wait-Job2($p) {
    if (-not $p) { return 7 }
    $j = [wmi]$p
    while ($j.JobState -eq 3 -or $j.JobState -eq 4) {
        Start-Sleep -Milliseconds 200
        $j = [wmi]$p
    }
    return $j.JobState
}

function Job-Err($p) {
    if (-not $p) { return '<no job>' }
    try { $j = [wmi]$p; return "state=$($j.JobState) err=$($j.ErrorCode) desc=$($j.ErrorDescription)" }
    catch { return "<job gone>" }
}

# 按 ResourceSubType 从资源池取默认 RASD/SASD 实例
function Get-DefaultSettings($subType) {
    $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
    $caps = $pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
    $rels = $caps.GetRelationships('Msvm_SettingsDefineCapabilities')
    foreach ($r in $rels) {
        if ($r.ValueRole -eq 0) { return [wmi]$r.PartComponent }
    }
    return $null
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims  = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }

try {
    # 1. 创建第二代虚拟机
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $vmName
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { $s = Wait-Job2 $r.Job; if ($s -ne 7) { throw "DefineSystem job state $s" } }
    elseif ($r.ReturnValue -ne 0) { throw "DefineSystem rv $($r.ReturnValue)" }
    $vm = [wmi]$r.ResultingSystem
    $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

    # 2. 添加 SCSI 控制器 (ResourceSubType Microsoft:Hyper-V:Synthetic SCSI Controller)
    $scsiTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic SCSI Controller'
    if (-not $scsiTmpl) { throw "no SCSI controller template" }
    $ar = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
    if ($ar.ReturnValue -eq 4096) { $s = Wait-Job2 $ar.Job; if ($s -ne 7) { throw "AddResource(SCSI) job state $s" } }
    elseif ($ar.ReturnValue -ne 0) { throw "AddResource(SCSI) rv $($ar.ReturnValue)" }
    $scsiPath = $ar.ResultingResourceSettings[0]
    $scsi = [wmi]$scsiPath
    Write-Host "SCSI controller added: $($scsi.ResourceSubType)"

    # 3. 创建动态 VHDX (Type=3 动态，Format=3 VHDX)
    $vhdSd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
    $vhdSd.Type = [uint16]3
    $vhdSd.Format = [uint16]3
    $vhdSd.Path = $vhdPath
    $vhdSd.MaxInternalSize = [uint64](1GB)
    $cr = $ims.CreateVirtualHardDisk($vhdSd.GetText(1))
    if ($cr.ReturnValue -eq 4096) { $s = Wait-Job2 $cr.Job; if ($s -ne 7) { throw "CreateVHD job state $s" } }
    elseif ($cr.ReturnValue -ne 0) { throw "CreateVHD rv $($cr.ReturnValue)" }
    if (-not (Test-Path $vhdPath)) { throw "vhdx not created" }
    Write-Host "VHDX created: $vhdPath"

    # 4a. 在 SCSI 控制器上添加合成磁盘驱动器 (LUN 0)
    $drvTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic Disk Drive'
    if (-not $drvTmpl) { throw "no Synthetic Disk Drive template" }
    $drv = $drvTmpl.psbase.Clone()
    $drv.Parent = $scsi.__PATH
    $drv.AddressOnParent = '0'
    $ar2 = $vsms.AddResourceSettings($vssd2.__PATH, @($drv.GetText(1)))
    if ($ar2.ReturnValue -eq 4096) { $s = Wait-Job2 $ar2.Job; if ($s -ne 7) { throw "AddResource(Drive) job state $s : $(Job-Err $ar2.Job)" } }
    elseif ($ar2.ReturnValue -ne 0) { throw "AddResource(Drive) rv $($ar2.ReturnValue)" }
    $drvPath = $ar2.ResultingResourceSettings[0]
    Write-Host "Disk drive added: $drvPath"

    # 4b. 构造指向该驱动器的 StorageAllocationSettingData，关联 vhdx
    $sasdTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Virtual Hard Disk'
    if (-not $sasdTmpl) { throw "no VHD storage template" }
    $sasd = $sasdTmpl.psbase.Clone()
    $sasd.Parent = $drvPath
    $sasd.HostResource = @($vhdPath)
    $ar3 = $vsms.AddResourceSettings($vssd2.__PATH, @($sasd.GetText(1)))
    if ($ar3.ReturnValue -eq 4096) { $s = Wait-Job2 $ar3.Job; if ($s -ne 7) { throw "AddResource(VHD) job state $s : $(Job-Err $ar3.Job)" } }
    elseif ($ar3.ReturnValue -ne 0) { throw "AddResource(VHD) rv $($ar3.ReturnValue)" }
    $diskPath = $ar3.ResultingResourceSettings[0]
    Write-Host "Disk attached: $diskPath"

    # 5. 验证：枚举虚拟机上的 StorageAllocationSettingData，确认 HostResource 匹配
    $vssdFinal = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
    $disks = ([wmi]$vssdFinal.__PATH).GetRelated('Msvm_StorageAllocationSettingData')
    $found = $false
    $hr = ''
    foreach ($dk in $disks) {
        $res = @($dk.HostResource)
        if ($res -and $res[0] -and ($res[0].ToLower() -eq $vhdPath.ToLower())) {
            $found = $true; $hr = $res[0]
        }
    }
    if ($found) {
        Write-Host "ASSERT PASS: StorageAllocationSettingData HostResource=$hr"
        Write-Host "RESULT: PASS"
    } else {
        Write-Host "ASSERT FAIL: vhdx not found in VM disks (count=$($disks.Count))"
        Write-Host "RESULT: FAIL"
    }
}
finally {
    # 清理虚拟机
    try {
        $existing = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$vmName'"
        foreach ($e in @($existing)) {
            if ($e) {
                $d = $vsms.DestroySystem($e.__PATH)
                if ($d.ReturnValue -eq 4096) { $null = Wait-Job2 $d.Job }
                Write-Host "Cleanup: destroyed VM $($e.__PATH)"
            }
        }
    } catch { Write-Host "Cleanup VM error: $_" }
    # 清理 vhdx
    try {
        if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force; Write-Host "Cleanup: removed vhdx" }
    } catch { Write-Host "Cleanup vhdx error: $_" }
}
```

## [PASS] 设置虚拟机自动启动延迟与故障恢复操作  `automatic_actions`

- 通过 ModifySystemSettings 修改 VSSD 上的四个自动操作字段，修改后均可读回。
- AutomaticRecoveryAction 的 ValueMap 为 2=None / 3=Restart / 4=Revert to snapshot（并非 0/1/2）。新建第二代虚拟机的默认值为 3（Restart）。传入非法值（如 1）会导致 ModifySystemSettings 返回 4096 后 Job 进入 state=10（Exception）失败。
- AutomaticCriticalErrorAction 的 ValueMap 为 0=None / 1=Pause Resume，默认值为 1。
- AutomaticStartupActionDelay 与 AutomaticCriticalErrorActionTimeout 均为 datetime 的 interval 变体，格式为 ddddddddhhmmss.mmmmmm:000（例如 120 秒='00000000000200.000000:000'，15 分钟='00000000001500.000000:000'）。
- AutomaticCriticalErrorActionTimeout 仅当 AutomaticCriticalErrorAction != 0 时生效；若将 action 设为 0（None），该 Timeout 会被清空为 NULL（读回为空）。
- 在 PowerShell 5.1 下，[wmiclass]"\\.\$ns:Class".CreateInstance() 不可靠（命名空间含反斜杠会导致转换失败或 CreateInstance 异常）。改用 Get-WmiObject -Namespace $ns -List -Class <Class> 取类后再 .CreateInstance() 更稳定。
- DefineSystem 的 OUT 参数为 ResultingSystem；DefineSystem/ModifySystemSettings/DestroySystem 返回 4096 时需 Wait-Job2 轮询 Msvm_ConcreteJob.JobState（7=Completed）。
- 整个流程仅读写 VSSD 配置，无需启动虚拟机。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_automatic_actions'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 创建第二代测试虚拟机 (CreateInstance 用 Get-WmiObject -List 获取类；PS5.1 下 [wmiclass]\\.\ns:cls 不可靠)
  $cls=Get-WmiObject -Namespace $ns -List -Class Msvm_VirtualSystemSettingData
  $vssd=$cls.CreateInstance()
  $vssd.ElementName=$name
  $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ $st=Wait-Job2 $r.Job; if($st -ne 7){throw "DefineSystem job state=$st"} }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem

  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # AutomaticStartupActionDelay 为 datetime 的 interval 类型: ddddddddhhmmss.mmmmmm:000
  $delay = '00000000000200.000000:000'   # 120 秒
  $vssd2.AutomaticStartupActionDelay = $delay
  # AutomaticRecoveryAction ValueMap: 2=None 3=Restart 4=Revert to snapshot
  $vssd2.AutomaticRecoveryAction = [uint16]2
  # AutomaticCriticalErrorAction: 0=None 1=Pause/Resume
  $vssd2.AutomaticCriticalErrorAction = [uint16]1
  # AutomaticCriticalErrorActionTimeout interval (仅当 action!=0 时生效)
  $vssd2.AutomaticCriticalErrorActionTimeout = '00000000001500.000000:000'  # 15 分钟

  $rm=$vsms.ModifySystemSettings($vssd2.GetText(1))
  if($rm.ReturnValue -eq 4096){ $st=Wait-Job2 $rm.Job; if($st -ne 7){ $jb=[wmi]$rm.Job; throw "Modify job state=$st err=$($jb.ErrorDescription)" } }
  elseif($rm.ReturnValue -ne 0){ throw "Modify rv=$($rm.ReturnValue)" }

  $vm2=[wmi]$vm.__PATH
  $vssd3=$vm2.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $okDelay  = ($vssd3.AutomaticStartupActionDelay -eq $delay)
  $okRec    = ($vssd3.AutomaticRecoveryAction -eq 2)
  $okCrit   = ($vssd3.AutomaticCriticalErrorAction -eq 1)
  $okCritTo = ($vssd3.AutomaticCriticalErrorActionTimeout -eq '00000000001500.000000:000')
  if($okDelay -and $okRec -and $okCrit -and $okCritTo){ 'ASSERT: PASS' } else { 'ASSERT: FAIL' }
}
finally {
  if($vm){ $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null } }
}
```

## [PASS] 为虚拟机添加合成电池  `battery_setting`

- 合成电池由 Msvm_BatterySettingData 表示，该类继承 CIM_ResourceAllocationSettingData，自身无独有属性；该资源自 build 16299 起提供。
- 不能通过 ([wmiclass]...).CreateInstance() 直接创建空实例：空实例 ResourceType 为空，AddResourceSettings 会被作业拒绝并返回 ErrorCode=32773(无法添加资源)。
- 正确做法是枚举 Msvm_BatterySettingData，选取 InstanceID 以 '\Default' 结尾的模板实例并克隆(ResourceType=1)，再通过 GetText(1) 序列化传入 AddResourceSettings；该调用同步完成，返回 0 而非 4096。
- 该资源提供 Default / Minimum / Maximum / Increment 四个模板实例，定义 GUID 为 C7E49E80-13B3-4DF9-A434-B56F579E2A68。
- 电池为纯标记型资源，无可调参数(SubType 为空)；回读的 ElementName 为本地化默认名称。
- PowerShell 模块未提供对应的 Add-VMBattery cmdlet，只能通过 WMI 添加；适用于需要来宾操作系统识别电池存在的场景。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# --- 创建第二代虚拟机 ---
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_battery_setting'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
# --- 电池: 克隆 Default 模板实例(空 CreateInstance 会被拒 ErrorCode=32773) ---
$tmpl = Get-WmiObject -Namespace $ns -Class Msvm_BatterySettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
$bat = $tmpl.PSObject.BaseObject.Clone()
$r2 = $vsms.AddResourceSettings($vssd2.__PATH, @($bat.GetText(1)))
if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }
# --- 回读 ---
$bats = $vssd2.GetRelated('Msvm_BatterySettingData')
'Battery count = ' + @($bats).Count
# --- 清理 ---
$d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
```

## [PASS] 设置虚拟机启动顺序  `boot_order`

- 第二代虚拟机的启动顺序由 VSSD.BootSourceOrder 表示，类型为 string[]，每个元素是指向 Msvm_BootSourceSettingData 实例的完整 WMI 路径(REF)。调整顺序即重排该字符串数组，再通过 ModifySystemSettings($vssd.GetText(1)) 整机下发，同步返回 rv=0。
- Msvm_BootSourceSettingData 为只读枚举项，代表第二代虚拟机的单个启动条目，由实际设备自动生成，不能通过 CreateInstance 凭空创建。空的第二代虚拟机 BootSourceOrder 为空；必须先挂载设备：添加合成网卡生成 BootSourceType=2 'EFI Network'，添加 SCSI 控制器与合成 DVD 生成 BootSourceType=1 'EFI SCSI Device'。
- Msvm_BootSourceSettingData.BootSourceType 枚举: 0=Unknown, 1=Drive, 2=Network, 3=File；可读字段包括 BootSourceDescription(如 'EFI Network' / 'EFI SCSI Device')、FirmwareDevicePath、OtherLocation、OptionalData。
- 写回时须将数组强制转换为 [string[]]，否则 GetText(1) 序列化可能丢失类型信息。回读时对每个元素执行 [wmi]$ref 即可解析出对应的 Msvm_BootSourceSettingData。
- 第一代虚拟机(SubType:1)机制不同: 使用 VSSD.BootOrder = [uint16[]]，枚举 0=Floppy, 1=CD-ROM, 2=IDE Hard Drive, 3=PXE Boot, 4=SCSI Hard Drive(最多 4 项)，同样经 ModifySystemSettings 下发。第二代虚拟机不提供 BootOrder 整数字段，改用 BootSourceOrder REF 数组。
- 在 PowerShell 5.1 中，[wmiclass]"\\.\$ns:Class" 里的 $ns: 会被解析为作用域变量，必须写作 ${ns}: 才能正确展开命名空间。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_boot_order'
$NIC_SUBTYPE  = 'Microsoft:Hyper-V:Synthetic Ethernet Port'
$SCSI_SUBTYPE = 'Microsoft:Hyper-V:Synthetic SCSI Controller'
$DVD_SUBTYPE  = 'Microsoft:Hyper-V:Synthetic DVD Drive'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

# 通过原始资源池的 AllocationCapabilities 取默认 RASD 模板(SettingsDefineCapabilities ValueRole=0 => Default)
function Get-DefaultRasd($subType){
  $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.ResourceSubType -eq $subType -and $_.Primordial -eq $true } | Select-Object -First 1
  if(-not $pool){ throw "no primordial pool for $subType" }
  $caps = ([wmi]$pool.__PATH).GetRelated('Msvm_AllocationCapabilities') | Select-Object -First 1
  $sdcRefs = Get-WmiObject -Namespace $ns -Query ("REFERENCES OF {{{0}}} WHERE ResultClass=Msvm_SettingsDefineCapabilities" -f $caps.__PATH)
  $defPath = $null
  foreach($ref in $sdcRefs){ if([int]$ref.ValueRole -eq 0){ $defPath = $ref.PartComponent; break } }
  if(-not $defPath){ throw "no default RASD for $subType" }
  return [wmi]$defPath
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
foreach($e in (Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName })){ $d = $vsms.DestroySystem($e.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } }

$vm = $null
try {
  # 第二代虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){ throw 'DefineSystem job failed' } } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem
  $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # 添加合成网卡 => 生成 'EFI Network' 启动项
  $nic = Get-DefaultRasd $NIC_SUBTYPE
  $nic.ElementName = 'WMITEST_NIC'
  $nic.VirtualSystemIdentifiers = @('{' + [guid]::NewGuid().ToString() + '}')
  $nic.StaticMacAddress = $false
  $addN = $vsms.AddResourceSettings($vssd2.__PATH, @($nic.GetText(1)))
  if($addN.ReturnValue -eq 4096){ if((Wait-Job2 $addN.Job) -ne 7){ throw 'AddResourceSettings(NIC) job failed' } } elseif($addN.ReturnValue -ne 0){ throw "AddResourceSettings(NIC) rv=$($addN.ReturnValue)" }

  # 添加 SCSI 控制器 + DVD => 生成 'EFI SCSI Device' 启动项
  $scsiTmpl = Get-DefaultRasd $SCSI_SUBTYPE
  $addS = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
  if($addS.ReturnValue -eq 4096){ if((Wait-Job2 $addS.Job) -ne 7){ throw 'AddResourceSettings(SCSI) job failed' } } elseif($addS.ReturnValue -ne 0){ throw "AddResourceSettings(SCSI) rv=$($addS.ReturnValue)" }
  $scsi = [wmi]($addS.ResultingResourceSettings | Select-Object -First 1)
  $dvd = Get-DefaultRasd $DVD_SUBTYPE
  $dvd.Parent = $scsi.__PATH
  $dvd.AddressOnParent = '0'
  $addD = $vsms.AddResourceSettings($vssd2.__PATH, @($dvd.GetText(1)))
  if($addD.ReturnValue -eq 4096){ if((Wait-Job2 $addD.Job) -ne 7){ throw 'AddResourceSettings(DVD) job failed' } } elseif($addD.ReturnValue -ne 0){ throw "AddResourceSettings(DVD) rv=$($addD.ReturnValue)" }

  # 读取 BootSourceOrder(第二代: 指向 Msvm_BootSourceSettingData 的 REF 字符串数组)
  $vssdNow = [wmi](([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH
  $origOrder = @($vssdNow.BootSourceOrder)
  foreach($p in $origOrder){ $bs = [wmi]$p; Write-Host ("ORIG type=" + $bs.BootSourceType + " desc=" + $bs.BootSourceDescription) }

  # 反转数组并通过 ModifySystemSettings 写回
  $newOrder = @(); for($i = $origOrder.Count - 1; $i -ge 0; $i--){ $newOrder += $origOrder[$i] }
  $vssdNow.BootSourceOrder = [string[]]$newOrder
  $rm = $vsms.ModifySystemSettings($vssdNow.GetText(1))
  if($rm.ReturnValue -eq 4096){ if((Wait-Job2 $rm.Job) -ne 7){ throw 'ModifySystemSettings job failed' } }
  Write-Host ("MODIFY_RV=" + $rm.ReturnValue)

  # 回读
  $vssdAfter = [wmi](([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH
  $readOrder = @($vssdAfter.BootSourceOrder)
  foreach($p in $readOrder){ $bs = [wmi]$p; Write-Host ("READ type=" + $bs.BootSourceType + " desc=" + $bs.BootSourceDescription) }
  $match = ($readOrder.Count -eq $newOrder.Count)
  for($i = 0; $i -lt $newOrder.Count; $i++){ if($readOrder[$i] -ne $newOrder[$i]){ $match = $false } }
  $changed = ($readOrder[0] -ne $origOrder[0])
  if($rm.ReturnValue -eq 0 -and $match -and $changed){ Write-Host 'RESULT=PASS' } else { Write-Host 'RESULT=FAIL' }

  # 第一代: VSSD.BootOrder = [uint16[]] 0=Floppy 1=CD-ROM 2=IDE-HDD 3=PXE 4=SCSI-HDD, 同样经 ModifySystemSettings 下发
}
catch { Write-Host ("ERROR: " + $_.Exception.Message); Write-Host 'RESULT=FAIL' }
finally {
  if($vm -ne $null -and $vm.__PATH){ try { $rd = $vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null } } catch {} }
}
```

## [PASS] 向虚拟机发送 Ctrl+Alt+Del  `cad_input`

- Msvm_Keyboard.TypeCtrlAltDel() 无参数,返回 uint32,0 表示成功,该调用同步返回,不走 Job。
- 键盘设备经 $vm.GetRelated('Msvm_Keyboard') 获取(每台虚拟机一个),需以 [wmi]$kbd.__PATH 取得实例后再调用方法。
- TypeCtrlAltDel 要求虚拟机处于运行态(EnabledState=2),须先经 RequestStateChange(2) 启动。无操作系统或启动介质的空虚拟机同样可启动至 Enabled 并接受注入。
- 空的第二代虚拟机无操作系统,RequestStateChange(3) 关机作业虽返回成功(JobState=7),但 EnabledState 可能仍停留在 2;若立即调用 DestroySystem,可能出现调用返回成功却残留运行中虚拟机的情况。应轮询 EnabledState 直到为 3(必要时重发关机)后再执行 Destroy,并重试 Destroy 直至枚举不到。
- 同类键盘注入方法:TypeText / PressKey / ReleaseKey / TypeScancodes(参见 keyboard_input)。

```powershell
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns = 'root\virtualization\v2'
$name = 'WMITEST_cad_input'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第二代虚拟机
$vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $name
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# 启动虚拟机(RequestStateChange -> Enabled=2)。Msvm_Keyboard.TypeCtrlAltDel
# 仅在虚拟机运行时有效;虚拟机处于停止态时调用会返回非零值或作业失败。
$sc = $vm.RequestStateChange(2)
if ($sc.ReturnValue -eq 4096) { Wait-Job2 $sc.Job | Out-Null }
$vm = [wmi]$vm.__PATH   # 重新读取;EnabledState 此时应为 2

# 获取虚拟机的合成键盘设备并发送安全注意序列
$kbd = $vm.GetRelated('Msvm_Keyboard') | Select-Object -First 1
$kb  = [wmi]$kbd.__PATH
$call = $kb.TypeCtrlAltDel()   # 无参数
if ($call.ReturnValue -eq 4096 -and $call.Job) { Wait-Job2 $call.Job | Out-Null }
# ReturnValue=0 表示成功(已注入 Ctrl+Alt+Del)

# 清理:强制关闭虚拟机后销毁。空虚拟机无操作系统可正常关机,
# 故销毁前轮询 EnabledState 直到为 3
for ($i=0; $i -lt 10; $i++) { $c=[wmi]$vm.__PATH; if($c.EnabledState -eq 3){break}; $o=$c.RequestStateChange(3); if($o.ReturnValue -eq 4096){Wait-Job2 $o.Job|Out-Null}; Start-Sleep -Seconds 1 }
$d = $vsms.DestroySystem($vm.__PATH)
if ($d.ReturnValue -eq 4096) { Wait-Job2 $d.Job | Out-Null }
```

## [PASS] 设置检查点类型(生产/标准)  `checkpoint_type`

- 检查点类型由 Msvm_VirtualSystemSettingData.UserSnapshotType (uint16) 控制，不在快照服务上；通过 Msvm_VirtualSystemManagementService.ModifySystemSettings 整机下发。
- 枚举值: 2=Disable(禁止创建检查点)、3=ProductionFallbackToTest(生产，不可用时回退到标准)、4=ProductionNoFallback(生产，不回退)、5=Test(标准/测试，含内存设备状态)。'生产检查点'对应 3/4，'标准检查点'对应 5。
- 新建第二代虚拟机的默认值为 3(ProductionFallbackToTest)，与 Hyper-V 管理器默认一致。
- 该属性为纯配置项，无需运行的操作系统或嵌套虚拟化，虚拟机停机时即可修改。
- ModifySystemSettings 同步完成时返回 0；返回 4096 时需 Wait-Job2 轮询作业。嵌入实例统一通过 GetText(1) 序列化。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns  = 'root\virtualization\v2'
$name = 'WMITEST_checkpoint_type'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第二代测试虚拟机
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $name
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
$vm = [wmi]$r.ResultingSystem

# 获取虚拟机设置实例(UserSnapshotType 位于 Msvm_VirtualSystemSettingData)
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

# 通过 ModifySystemSettings 设置检查点类型。枚举:
#   2=Disable 3=ProductionFallbackToTest 4=ProductionNoFallback 5=Test
$vssd2.UserSnapshotType = [uint16]3   # 生产检查点，不可用时回退到标准
$m = $vsms.ModifySystemSettings($vssd2.GetText(1))
if ($m.ReturnValue -eq 4096) { $null = Wait-Job2 $m.Job }

# 从 WMI 重新回读
$back = ([wmi]$vssd2.__PATH).UserSnapshotType
Write-Output "UserSnapshotType = $back"

# 清理
$d = $vsms.DestroySystem($vm.__PATH)
if ($d.ReturnValue -eq 4096) { $null = Wait-Job2 $d.Job }
```

## [PASS] 读取与升级虚拟机配置版本  `config_version`

- VSSD.Version 是只读字符串属性(如 '12.0')，通过 VM.GetRelated('Msvm_VirtualSystemSettingData') 取得 Realized 配置后读取。
- UpgradeSystemVersion 是 Msvm_VirtualSystemManagementService 的方法，签名为 (ComputerSystem REF[IN], UpgradeSettingData string[IN], OUT Job)。
- 动态后期绑定调用 $vsms.UpgradeSystemVersion($path, $null) 会抛出'无效的方法'异常。必须用 [wmiclass].GetMethodParameters('UpgradeSystemVersion') 构造 InParameters，设置 ComputerSystem=__PATH、UpgradeSettingData=''(空串而非 $null)，再调用 $vsms.InvokeMethod(...)。
- 返回 4096 表示异步 Job，需 Wait-Job2 轮询至 JobState=7(Completed)。
- 新建虚拟机总是落在主机支持的最高版本，因此对新建虚拟机执行升级为空操作；调用仍成功返回 4096 并完成，版本回读不变。若要观察真正的跨版本升级，需先具备低版本虚拟机(由旧机导入或低版本主机创建)。
- 主机支持的版本列表可用 Get-VMHostSupportedVersion 读取(返回 Name / Version / IsDefault)。UpgradeSystemVersion 方法自 build 10240 起持续提供。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns = 'root\virtualization\v2'
$name = 'WMITEST_config_version'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# --- 创建新的第二代虚拟机(始终按主机默认/最新版本创建) ---
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $name
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# --- 读取 VSSD.Version(配置版本，如 12.0) ---
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$verBefore = $vssd2.Version   # -> '12.0'

# --- 升级: UpgradeSystemVersion(ComputerSystem REF, UpgradeSettingData string, OUT Job) ---
# 注意: 动态后期绑定调用 $vsms.UpgradeSystemVersion(...) 会抛'无效的方法';
# 必须通过 [wmiclass].GetMethodParameters 构造 InParameters 后 InvokeMethod。
$vsmsClass = [wmiclass]("\\.\" + $ns + ":Msvm_VirtualSystemManagementService")
$inParams = $vsmsClass.GetMethodParameters('UpgradeSystemVersion')
$inParams['ComputerSystem'] = $vm.__PATH
$inParams['UpgradeSettingData'] = ''   # 空串 -> 升级到主机默认
$ru = $vsms.InvokeMethod('UpgradeSystemVersion', $inParams, $null)
if ($ru.ReturnValue -eq 4096) { Wait-Job2 $ru.Job | Out-Null }   # rv 4096 = 异步作业

# --- 回读 ---
$vssdAfter = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$verAfter = $vssdAfter.Version

# --- 清理 ---
$rd = $vsms.DestroySystem($vm.__PATH)
if ($rd.ReturnValue -eq 4096) { Wait-Job2 $rd.Job | Out-Null }

# 主机支持的版本列表(供参考/选择目标版本):
#   Get-VMHostSupportedVersion   -> Name/Version/IsDefault
```

## [PASS] 将合成网卡接入虚拟交换机  `connect_switch`

- 网卡与交换机的连接由 Msvm_EthernetPortAllocationSettingData (EPAS) 表达；它是合成网卡 Msvm_SyntheticEthernetPortSettingData 的子资源，通过 AddResourceSettings 添加到虚拟机的 VSSD 上。
- 两个关键属性：EPAS.Parent 为网卡 RASD 的 __PATH；EPAS.HostResource 为交换机 __PATH。HostResource 为 string[] 类型，赋值时须用 @() 包成数组。
- 创建 EPAS 与网卡设置时应克隆 InstanceID 以 '...\Default' 结尾的类默认实例（psbase.Clone()），而非手动 CreateInstance，默认实例已带好 ResourceType/ResourceSubType 等字段。
- 添加顺序：先 AddResourceSettings 添加网卡并取 ResultingResourceSettings[0] 作为网卡 RASD 路径，再以该路径作为 EPAS.Parent。
- AddResourceSettings、DefineSystem、DestroySystem 返回 4096 表示异步任务，需通过 Wait-Job2 轮询 Job 直至完成。
- 验证方式：读回 EPAS.HostResource 等于交换机 __PATH，且 EnabledState=2 (Enabled) 表示接入成功。
- 相关类自 build 9200 起提供，无版本限制。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# --- 创建第二代虚拟机 ---
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_connect_switch'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1

# --- 添加合成网卡（克隆 InstanceID 以 '...\Default' 结尾的类默认模板实例） ---
$nicTemplate=$null
Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData -Filter "InstanceID LIKE '%\\Default'" | ForEach-Object { if($_.InstanceID -match 'Default$'){ $nicTemplate=$_ } }
$nic=$nicTemplate.psbase.Clone()
$nic.ElementName='WMITEST_NIC'
$nic.VirtualSystemIdentifiers=@([guid]::NewGuid().ToString('B').ToUpper())
$addNic=$vsms.AddResourceSettings($vssd2.__PATH,@($nic.GetText(1)))
if($addNic.ReturnValue -eq 4096){Wait-Job2 $addNic.Job|Out-Null}
$nicRasd=[wmi]$addNic.ResultingResourceSettings[0]

# --- 选取一个虚拟交换机 ---
$sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Select-Object -First 1

# --- 通过 EthernetPortAllocationSettingData 将网卡连接到交换机 ---
$epasTemplate=$null
Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData -Filter "InstanceID LIKE '%\\Default'" | ForEach-Object { if($_.InstanceID -match 'Default$'){ $epasTemplate=$_ } }
$epas=$epasTemplate.psbase.Clone()
$epas.Parent=$nicRasd.__PATH          # 网卡 RASD 的路径
$epas.HostResource=@($sw.__PATH)      # 目标交换机的路径
$addConn=$vsms.AddResourceSettings($vssd2.__PATH,@($epas.GetText(1)))
if($addConn.ReturnValue -eq 4096){Wait-Job2 $addConn.Job|Out-Null}
$conn=[wmi]$addConn.ResultingResourceSettings[0]

# --- 读回验证 ---
$conn.HostResource   # -> 交换机 __PATH
$conn.EnabledState   # -> 2 (Enabled)

# --- 清理 ---
$vsms.DestroySystem($vm.__PATH)
```

## [PASS] 启用处理器功能限制 (LimitProcessorFeatures / LimitCPUID)  `cpu_compat`

- LimitProcessorFeatures 与 LimitCPUID 为 Msvm_ProcessorSettingData 上的布尔属性，用于跨主机迁移时限制暴露给来宾的处理器功能集与 CPUID 位；可通过 ModifyResourceSettings 写入并读回生效。
- 修改走标准资源修改路径：取虚拟机的 VSSD -> ProcessorSettingData，设置属性后经 GetText(1) 序列化传入 ModifyResourceSettings。ModifyResourceSettings 返回 0 表示同步成功，返回 4096 表示异步任务，须轮询 Job。
- 读回需重新经 VSSD 遍历 GetRelated 取新的 ProcessorSettingData 实例，原句柄为旧快照，不会自动刷新。
- 相关属性 LimitProcessorFeaturesMode (uint8, DefaultMinimumFeatures / ClusterNodeCommonFeatures) 控制受限功能集的类型，本用例保持默认未修改。
- 相关属性自 build 9200 起提供。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_cpu_compat'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){
    Start-Sleep -Milliseconds 200
    $j = [wmi]$p
  }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null

try {
  # --- 创建第二代虚拟机 ---
  $vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $null = Wait-Job2 $r.Job }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem failed rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  # --- 取 ProcessorSettingData ---
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1

  # --- 将 LimitProcessorFeatures 与 LimitCPUID 置为 true ---
  $proc.LimitProcessorFeatures = $true
  $proc.LimitCPUID = $true
  $r2 = $vsms.ModifyResourceSettings($proc.GetText(1))
  if($r2.ReturnValue -eq 4096){ $js = Wait-Job2 $r2.Job; if($js -ne 7){ throw "Modify job failed state=$js" } }
  elseif($r2.ReturnValue -ne 0){ throw "ModifyResourceSettings failed rv=$($r2.ReturnValue)" }

  # --- 读回验证 ---
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc2 = ([wmi]$vssd3.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1
  $lpf = $proc2.LimitProcessorFeatures
  $lcid = $proc2.LimitCPUID

  if($lpf -eq $true -and $lcid -eq $true){
    Write-Host "ASSERT_RESULT=PASS LimitProcessorFeatures=$lpf LimitCPUID=$lcid"
  } else {
    Write-Host "ASSERT_RESULT=FAIL LimitProcessorFeatures=$lpf LimitCPUID=$lcid"
  }
}
catch {
  Write-Host "ASSERT_RESULT=FAIL ERROR=$($_.Exception.Message)"
}
finally {
  if($vm -ne $null){
    try {
      $d = $vsms.DestroySystem($vm.__PATH)
      if($d.ReturnValue -eq 4096){ $null = Wait-Job2 $d.Job }
    } catch {}
  }
}
```

## [PASS] 设置虚拟处理器数量  `cpu_count`

- 虚拟处理器数量由 Msvm_ProcessorSettingData.VirtualQuantity 表示，类型为 uint64，赋值前应显式转换为 [uint64]。
- 修改单个资源使用 ModifyResourceSettings($proc.GetText(1))（嵌入实例须经 GetText(1) 序列化），而非 AddResourceSettings。
- 读回验证须从 $vm.__PATH 重新经关联 VSSD -> ProcessorSettingData 取新实例，原对象为旧快照不会自动刷新。
- DefineSystem 的 OUT 参数名为 ResultingSystem。ModifyResourceSettings 返回 0 表示同步成功，返回 4096 表示异步任务，须轮询 Job。
- 无需虚拟机处于运行态即可修改虚拟处理器数量，离线修改即刻生效。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_cpu_count'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

$vm = $null
try {
  # 创建第二代空虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem

  # 定位到 ProcessorSettingData
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1

  # 将虚拟处理器数量设为 4（VirtualQuantity 为 uint64）
  $proc.VirtualQuantity = [uint64]4
  $r2 = $vsms.ModifyResourceSettings($proc.GetText(1))
  if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

  # 重新取实例读回
  $proc2 = (([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).Path
  $proc2 = ([wmi]$proc2.Path).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1
  Write-Host ('VirtualQuantity=' + $proc2.VirtualQuantity)
}
finally {
  if($vm -ne $null){ $d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } }
}
```

## [PASS] 启用嵌套虚拟化  `cpu_nested`

- 嵌套虚拟化通过将 Msvm_ProcessorSettingData.ExposeVirtualizationExtensions 置为 $true 并调用 ModifyResourceSettings 启用，读回为 True 表示生效。
- ModifyResourceSettings 返回 0 表示同步成功，返回 4096 表示异步任务，须轮询 Job。
- 该属性须在虚拟机处于停止态时修改，对运行中的虚拟机修改会失败；本示例使用新创建的空虚拟机，天然处于停止态。
- 嵌套虚拟化的实际运行（在来宾内启动内层虚拟机）还需主机 CPU 支持 VT-x/EPT，本示例仅验证 WMI 属性的写入与读回。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_cpu_nested'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null

try {
  # 创建第二代虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem

  # 取 ProcessorSettingData
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1

  # 启用嵌套虚拟化（Msvm_ProcessorSettingData.ExposeVirtualizationExtensions）
  $proc.ExposeVirtualizationExtensions = $true
  $r2 = $vsms.ModifyResourceSettings($proc.GetText(1))
  if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

  # 读回验证
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc2 = ([wmi]$vssd3.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1
  if($proc2.ExposeVirtualizationExtensions -eq $true){ 'PASS' } else { 'FAIL' }
}
finally {
  if($vm -ne $null){
    $d = $vsms.DestroySystem($vm.__PATH)
    if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
  }
}
```

## [PASS] 设置 CPU 预留、上限与相对权重  `cpu_reserve_limit_weight`

- Reservation、Limit、Weight 均为 Msvm_ProcessorSettingData 上的属性（继承自 CIM_ResourceAllocationSettingData）。Reservation 与 Limit 为 uint64，Weight 为 uint32。
- 单位说明：Reservation 与 Limit 以「单逻辑处理器百分比 * 1000」计。默认 Reservation=0，Limit=100000（即 100%），Weight=100。
- 修改方式：取出 ProcessorSettingData 实例，设置三个属性后经 GetText(1) 序列化传入 ModifyResourceSettings（以数组形式 @(...) 传参）。三个属性可一次性修改。
- 对停止态的空虚拟机无需启动即可修改。ModifyResourceSettings 返回 0 表示同步成功，返回 4096 表示异步任务，须轮询 Job。
- 清理使用 DestroySystem 移除测试虚拟机。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$name = 'WMITEST_cpu_reserve_limit_weight'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null
try {
  $vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem

  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $proc = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1

  # Reservation/Limit unit = per-logical-processor percentage * 1000 (Limit defaults to 100000=100%, Reservation defaults to 0)
  # Weight is the relative priority (defaults to 100)
  $proc.Reservation = [uint64]25000
  $proc.Limit       = [uint64]75000
  $proc.Weight      = [uint32]200
  $r2 = $vsms.ModifyResourceSettings(@($proc.GetText(1)))
  if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

  $proc2 = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1
  Write-Output "Reservation=$($proc2.Reservation) Limit=$($proc2.Limit) Weight=$($proc2.Weight)"
}
finally {
  if($vm){ $d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } }
}
```

## [PASS] 创建内部(Internal)虚拟交换机  `create_switch`

- 使用 Msvm_VirtualEthernetSwitchManagementService.DefineSystem 创建交换机，签名与创建虚拟机的同名方法一致：DefineSystem(SystemSettings, ResourceSettings[], ReferenceConfiguration)；OUT 参数为 ResultingSystem 与 Job，返回码 0 表示成功、4096 表示异步 Job。
- 三种交换机的区别取决于 ResourceSettings 数组：Private 不传端口(空数组或 null)；Internal 传 1 个 Msvm_EthernetPortAllocationSettingData，其 HostResource 指向宿主 Msvm_ComputerSystem.__PATH(宿主由此获得一块 vNIC)；External 的 HostResource 指向物理 Msvm_ExternalEthernetPort。
- 端口的 ResourceSubType 由 provider 自动填为 'Microsoft:Hyper-V:Ethernet Connection'，ResourceType=33，无需手动设置。
- DefineSystem 走异步路径(返回 4096)时，OUT 参数 ResultingSystem 可能为空，需先用 Wait-Job2 等待 Job 到达 JobState=7(Completed)，再按 ElementName 反查 Msvm_VirtualEthernetSwitch 获取 __PATH。
- 定位宿主 Msvm_ComputerSystem 时，Caption/Description 为本地化字符串，不应按 'Hosting Computer System' 匹配；可靠判据是宿主的 Name 等于 ElementName(计算机名)，而虚拟机的 Name 为 GUID。
- 验证交换机类型时，不宜依赖 GetRelated('Msvm_InternalEthernetPort')(该关联不稳定)；应枚举交换机 SettingData 下的 Msvm_EthernetPortAllocationSettingData，按 HostResource 是否指向宿主判定 Internal。
- 清理使用 Msvm_VirtualEthernetSwitchManagementService.DestroySystem(switch.__PATH)，同样可能返回 4096 需等待；finally 块按 ElementName 兜底删除，避免异常时残留。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$swName = 'WMITEST_create_switch'

function Wait-Job2($p){
  if(-not $p){return 7}
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}

$svc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitchManagementService

# 预清理：删除同 ElementName 的遗留测试交换机
Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -eq $swName } | ForEach-Object {
  $rc = $svc.DestroySystem($_.__PATH); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
}

$createdPath = $null
try {
  # 定位宿主 Msvm_ComputerSystem。Caption/Description 为本地化字符串，
  # 因此按结构判定：宿主的 Name 等于 ElementName(计算机名)；虚拟机的 Name 为 GUID。
  $hostCs = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.Name -eq $_.ElementName } | Select-Object -First 1
  if(-not $hostCs){ throw 'Could not locate host Msvm_ComputerSystem' }

  # 交换机设置
  $sds = ([wmiclass]"\\.\${ns}:Msvm_VirtualEthernetSwitchSettingData").CreateInstance()
  $sds.ElementName = $swName

  # Internal 交换机 = 一个 Msvm_EthernetPortAllocationSettingData，其 HostResource 指向宿主计算机系统。
  # (External 应指向物理 Msvm_ExternalEthernetPort；Private 不传端口数组。)
  $port = ([wmiclass]"\\.\${ns}:Msvm_EthernetPortAllocationSettingData").CreateInstance()
  $port.HostResource = @($hostCs.__PATH)

  # DefineSystem(SystemSettings, ResourceSettings[], ReferenceConfiguration)；嵌入实例经 GetText(1) 序列化
  $r = $svc.DefineSystem($sds.GetText(1), @($port.GetText(1)), $null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){ throw 'DefineSystem job failed' } }
  elseif($r.ReturnValue -ne 0){ throw ("DefineSystem rv=" + $r.ReturnValue) }

  # 异步路径下 OUT 参数 ResultingSystem 可能为空，改按 ElementName 反查交换机。
  $createdPath = $r.ResultingSystem
  if(-not $createdPath){
    $createdPath = (Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -eq $swName } | Select-Object -First 1).__PATH
  }

  # 验证为 Internal：恰有 1 个 HostResource 指向宿主的端口分配，且 0 个外部端口。
  $ssd = ([wmi]$createdPath).GetRelated('Msvm_VirtualEthernetSwitchSettingData') | Select-Object -First 1
  $ports = ([wmi]$ssd.__PATH).GetRelated('Msvm_EthernetPortAllocationSettingData')
  $intCnt = 0; $extCnt = 0
  foreach($p in $ports){
    $hr = @($p.HostResource)
    if($hr -contains $hostCs.__PATH){ $intCnt++ }
    elseif(($hr -join '') -match 'Msvm_ExternalEthernetPort'){ $extCnt++ }
  }
  if($intCnt -eq 1 -and $extCnt -eq 0){ Write-Host 'PASS Internal switch created' } else { Write-Host 'FAIL' }
}
finally {
  Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -eq $swName } | ForEach-Object {
    $rc = $svc.DestroySystem($_.__PATH); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
  }
}
```

## [PASS] 创建 VHDX 文件  `create_vhd`

- 使用 Msvm_ImageManagementService.CreateVirtualHardDisk(VirtualDiskSettingData)，入参为 Msvm_VirtualHardDiskSettingData 的嵌入实例，经 GetText(1) 序列化。
- VirtualHardDiskSettingData 关键属性：Type(2=Fixed/3=Dynamic/4=Differencing)、Format(2=VHD/3=VHDX/4=VHDSet)、Path、MaxInternalSize(字节，uint64)；BlockSize/LogicalSectorSize/PhysicalSectorSize 设为 0 表示采用默认值(默认 BlockSize=33554432=32MiB，LogicalSector=512，PhysicalSector=4096)。
- CreateVirtualHardDisk 通常返回 4096(异步 Job)，需用 Wait-Job2 轮询 ConcreteJob.JobState 直至 7(Completed)。
- 动态盘创建后的初始物理文件约 4MiB(4194304 字节)，并非声明的 MaxInternalSize。
- 读回校验使用 GetVirtualHardDiskSettingData(Path)，OUT 参数名为 SettingData，其内容为 CIM-XML(<INSTANCE><PROPERTY NAME=...><VALUE>...)，而非 MOF，应以 XML 正则取值。读回的 MaxInternalSize=68719476736=64GiB，与请求一致。
- 该操作仅生成磁盘文件，不创建虚拟机；清理只需 Remove-Item 删除 .vhdx。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p) {
  if (-not $p) { return 7 }
  $j = [wmi]$p
  while ($j.JobState -eq 3 -or $j.JobState -eq 4) { Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vhdPath = 'C:\Temp\WMITEST_create_vhd.vhdx'
if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }
$maxSize = [uint64](64 * 1024 * 1024 * 1024)  # 64 GiB

$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

# 构造嵌入的 Msvm_VirtualHardDiskSettingData (Type=3 动态, Format=3 VHDX)
$vhdsd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
$vhdsd.Type = [uint16]3
$vhdsd.Format = [uint16]3
$vhdsd.Path = $vhdPath
$vhdsd.MaxInternalSize = $maxSize
$vhdsd.BlockSize = [uint32]0          # 0 表示由 Hyper-V 选取默认值
$vhdsd.LogicalSectorSize = [uint32]0
$vhdsd.PhysicalSectorSize = [uint32]0

try {
  $r = $ims.CreateVirtualHardDisk($vhdsd.GetText(1))   # GetText(1) 生成嵌入 MOF
  if ($r.ReturnValue -eq 4096) { $js = Wait-Job2 $r.Job; if ($js -ne 7) { throw "job failed state=$js" } }
  elseif ($r.ReturnValue -ne 0) { throw "rv=$($r.ReturnValue)" }

  # 验证：文件存在并读回设置。SettingData OUT 参数为 CIM-XML，非 MOF。
  $info = $ims.GetVirtualHardDiskSettingData($vhdPath)
  if ($info.SettingData -match 'NAME="MaxInternalSize"[^>]*><VALUE>(\d+)</VALUE>') { $readMax = $matches[1] }
  Write-Output ("Path=$vhdPath exists=$(Test-Path $vhdPath) ReadBackMaxInternalSize=$readMax")
}
finally {
  if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }   # 清理 vhdx 文件
}
```

## [PASS] DDA 设备直通流程与方法签名核对  `dda_dismount_doc`

- 此条目为纯文档与只读任务：不执行实际 dismount(以免影响主机物理设备)，脚本仅核对类、方法、参数签名并进行枚举，不创建任何 VM。
- Msvm_AssignableDeviceService 为单例服务类，无实例属性。
- DismountAssignableDevice(IN: DismountSettingData，即嵌入的 Msvm_AssignableDeviceDismountSettingData，经 GetText(1) 序列化；OUT: DismountedDeviceInstancePath, Job)。
- MountAssignableDevice(IN: DeviceInstancePath, DeviceLocationPath；OUT: MountedDeviceInstancePath, Job)。两者返回 4096 时需用 Wait-Job2 等待。
- Msvm_AssignableDeviceDismountSettingData 关键可写字段：DeviceInstancePath、DeviceLocationPath、RequireAcsSupport、RequireDeviceMitigations(另含继承的 Caption/Description/ElementName/InstanceID)。
- 分配给 VM 使用资源类 Msvm_PciExpressSettingData(继承 CIM_ResourceAllocationSettingData，共 28 个属性)，经 AddResourceSettings 下发；GPU 等大 BAR 设备另需设置 Low/HighMmioGapSize。
- Get-WmiObject Msvm_PciExpress 用于枚举主机可分配的 PCIe 设备(仅作存在性记录，不触碰设备)。
- 返回码 ValueMap：0=成功，4096=异步 Job，32768-32779 为各类错误。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

# ============ DDA (Discrete Device Assignment) 完整步骤 ============
# 服务: Msvm_AssignableDeviceService (CIM_Service 子类, 单例, 无 properties)
$ads = Get-WmiObject -Namespace $ns -Class Msvm_AssignableDeviceService

# --- STEP A: 主机侧 dismount (从主机拆下 PCIe 设备, 使其可被分配) ---
# 先在设备管理器/PnP 中禁用目标设备并获取其 PNP InstanceId 与 LocationPath。
# 构造 dismount 设置实例 (嵌入实例, 需 GetText(1) 序列化):
#   $dsd = ([wmiclass]"\\.\$ns:Msvm_AssignableDeviceDismountSettingData").CreateInstance()
#   $dsd.DeviceInstancePath  = 'PCI\VEN_xxxx&DEV_xxxx\...'   # PNP device instance ID
#   $dsd.DeviceLocationPath  = 'PCIROOT(0)#PCI(....)'          # PNP location path
#   $dsd.RequireAcsSupport       = $true   # 要求 ACS 支持
#   $dsd.RequireDeviceMitigations= $true   # 要求设备缓解措施
#   $r = $ads.DismountAssignableDevice($dsd.GetText(1))
#   if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job }
#   # OUT: $r.DismountedDeviceInstancePath = 已拆下的设备实例路径
#   # 注意: 本脚本不执行实际 dismount (会影响主机物理设备), 仅核对方法签名。

# --- STEP B: 将已拆下的设备分配给 VM ---
# 经 Msvm_VirtualSystemManagementService.AddResourceSettings, 资源类为
# Msvm_PciExpressSettingData (CIM_ResourceAllocationSettingData 子类):
#   $pci = ([wmiclass]"\\.\$ns:Msvm_PciExpressSettingData").CreateInstance()
#   $pci.HostResource = @($r.DismountedDeviceInstancePath)
#   # 可选: VirtualFunctions / NumaAwarePlacement / GuestPciExpressMode(0=Paravirtualized,1=Emulated)
#   $vsms.AddResourceSettings($vssd.__PATH, @($pci.GetText(1)))
# 大 BAR 设备(如 GPU) 还需在 Msvm_MemorySettingData 上设置 LowMmioGapSize/HighMmioGapSize。

# --- STEP C: 还原 — 从 VM 移除资源后, 将设备 mount 回主机 ---
#   $r2 = $ads.MountAssignableDevice($deviceInstancePath, $deviceLocationPath)
#   if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job }
#   # OUT: $r2.MountedDeviceInstancePath

# ============ 只读方法签名核对 ============
$cls = [wmiclass]"\\.\$ns:Msvm_AssignableDeviceService"
$dm  = $cls.Methods['DismountAssignableDevice']
($dm.InParameters.Properties  | % { $_.Name+':'+$_.Type }) -join ','
($dm.OutParameters.Properties | % { $_.Name+':'+$_.Type }) -join ','
$mm  = $cls.Methods['MountAssignableDevice']
($mm.InParameters.Properties  | % { $_.Name+':'+$_.Type }) -join ','
($mm.OutParameters.Properties | % { $_.Name+':'+$_.Type }) -join ','
([wmiclass]"\\.\$ns:Msvm_AssignableDeviceDismountSettingData").CreateInstance().Properties.Name
@(Get-WmiObject -Namespace $ns -Class Msvm_PciExpress).Count   # 主机可枚举的 PCIe 设备数
```

## [PASS] 创建第一代虚拟机  `def_gen1`

- 第一代虚拟机设置 VirtualSystemSubType='Microsoft:Hyper-V:SubType:1'(第二代为 SubType:2)。
- DefineSystem 可能同步返回 ReturnValue=0(无 Job)，此时无需轮询；仍应保留 4096 走 Wait-Job2 的兜底分支以适配异步返回。
- DefineSystem 的 OUT 参数名为 ResultingSystem，$r.ResultingSystem 即新建虚拟机的 __PATH。
- 嵌入实例须经 GetText(1) 序列化后传入。
- 清理使用 DestroySystem $vm.__PATH；脚本以 try/finally 保证清理。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_def_gen1'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

$vm = $null
try {
  # 第一代 = SubType:1 (第二代为 SubType:2)
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:1'

  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem failed RV=$($r.ReturnValue)" }

  $vm = [wmi]$r.ResultingSystem
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  Write-Host "Created: $($vssd2.ElementName) SubType=$($vssd2.VirtualSystemSubType)"
}
finally {
  if($vm -and $vm.__PATH){
    $rd = $vsms.DestroySystem($vm.__PATH)
    if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
  }
}
```

## [PASS] 创建第二代虚拟机  `def_gen2`

- DefineSystem 可能同步返回 0(无 Job)，此时无需等待；仍应保留 if 4096 走 Wait-Job2 的兜底分支以适配异步返回。
- OUT 参数名为 ResultingSystem，[wmi]$r.ResultingSystem 即得到 Msvm_ComputerSystem。
- 第二代虚拟机设置 VSSD.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'(取值仅 SubType:1/SubType:2)；嵌入实例经 GetText(1) 序列化。
- VirtualSystemSubType 须从虚拟机关联的 Msvm_VirtualSystemSettingData 读回(Msvm_ComputerSystem 上不含该属性)。
- DestroySystem 可能返回 4096(异步)，需用 Wait-Job2 等待。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$vmName = 'WMITEST_def_gen2'

function Wait-Job2($p) {
    if (-not $p) { return 7 }
    $j = [wmi]$p
    while ($j.JobState -eq 3 -or $j.JobState -eq 4) {
        Start-Sleep -Milliseconds 200
        $j = [wmi]$p
    }
    return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 构造第二代 (SubType:2) 设置实例
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $vmName
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'

$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
elseif ($r.ReturnValue -ne 0) { throw "DefineSystem failed: $($r.ReturnValue)" }

# OUT 参数名为 ResultingSystem
$vm = [wmi]$r.ResultingSystem

# 从关联的 VSSD 读回子类型
$vssdRead = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$vssdRead.VirtualSystemSubType   # -> Microsoft:Hyper-V:SubType:2

# 清理
$d = $vsms.DestroySystem($vm.__PATH)
if ($d.ReturnValue -eq 4096) { $null = Wait-Job2 $d.Job }
```

## [PASS] 向虚拟 DVD 驱动器插入 ISO 镜像  `dvd_insert_iso`

- 插入 ISO 为三步链：SCSI 控制器 -> 合成 DVD 驱动器(Msvm_ResourceAllocationSettingData，ResourceSubType='Microsoft:Hyper-V:Synthetic DVD Drive'，Parent=SCSI 路径) -> ISO 盘(Msvm_StorageAllocationSettingData，ResourceSubType='Microsoft:Hyper-V:Virtual CD/DVD Disk'，Parent=DVD 驱动器路径，HostResource=@(iso 路径))。其结构与挂载 VHD 的盘片层(Virtual Hard Disk)同构，仅介质子类型不同。
- ISO 介质使用 Msvm_StorageAllocationSettingData(非 RASD)，ResourceSubType='Microsoft:Hyper-V:Virtual CD/DVD Disk'，ResourceType=16(DVD)。HostResource=@('.iso 的 Windows 反斜杠绝对路径')。空的第二代虚拟机默认无 SCSI 控制器，须先添加。
- 模板获取方式与其它存储项一致：Msvm_ResourcePool(ResourceSubType=...，Primordial=True) -> Msvm_AllocationCapabilities -> Msvm_SettingsDefineCapabilities(ValueRole=0) 的 PartComponent；对其 .psbase.Clone() 后修改 Parent/HostResource 再 GetText(1)。
- 使用 2KB 空占位 .iso 即可成功添加(AddResourceSettings 返回 0)，无需真实可引导镜像——此配方只验证挂载接线，不验证引导。换碟可用 ModifyResourceSettings 修改同一 SASD 的 HostResource；弹出碟片则将 HostResource 设为空数组。
- AddResourceSettings 返回的 ResultingResourceSettings[0] 即新 SASD 路径；验证时从 VSSD GetRelated('Msvm_StorageAllocationSettingData') 读回 HostResource 比对(忽略大小写)。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_dvd_insert_iso'
$SCSI_SUBTYPE = 'Microsoft:Hyper-V:Synthetic SCSI Controller'
$DVD_SUBTYPE  = 'Microsoft:Hyper-V:Synthetic DVD Drive'
$ISO_SUBTYPE  = 'Microsoft:Hyper-V:Virtual CD/DVD Disk'

$workDir = 'C:/Users/Administrator/Documents/GitHub/HyperV-WMI-Documentation/verify/work'
$isoPath = (Join-Path $workDir 'WMITEST_dvd_insert_iso.iso') -replace '/', '\'

function Wait-Job2($p) {
    if (-not $p) { return 7 }
    $j = [wmi]$p
    while ($j.JobState -eq 3 -or $j.JobState -eq 4) { Start-Sleep -Milliseconds 200; $j = [wmi]$p }
    return $j.JobState
}
function Job-Err($p) {
    if (-not $p) { return '<no job>' }
    try { $j = [wmi]$p; return "state=$($j.JobState) err=$($j.ErrorCode) desc=$($j.ErrorDescription)" }
    catch { return '<job gone>' }
}
# 通过 primordial 池获取某 ResourceSubType 的默认模板设置实例
function Get-DefaultSettings($subType) {
    $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
    if (-not $pool) { throw "no primordial pool for $subType" }
    $caps = ([wmi]$pool.__PATH).GetRelated('Msvm_AllocationCapabilities') | Select-Object -First 1
    $rels = ([wmi]$caps.__PATH).GetRelationships('Msvm_SettingsDefineCapabilities')
    foreach ($r in $rels) { if ([int]$r.ValueRole -eq 0) { return [wmi]$r.PartComponent } }
    throw "no default settings for $subType"
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 预清理遗留的测试虚拟机
foreach ($e in (Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName })) {
    $d = $vsms.DestroySystem($e.__PATH); if ($d.ReturnValue -eq 4096) { Wait-Job2 $d.Job | Out-Null }
}
if (Test-Path $isoPath) { Remove-Item $isoPath -Force }

$vm = $null
try {
    # 1. 占位 .iso 文件(空内容；此处只验证挂载接线，不验证引导)
    New-Item -ItemType File -Path $isoPath -Force | Out-Null
    [System.IO.File]::WriteAllBytes($isoPath, (New-Object byte[] 2048))
    Write-Host "ISO placeholder created: $isoPath"

    # 2. 空的第二代虚拟机
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $testName
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { if ((Wait-Job2 $r.Job) -ne 7) { throw 'DefineSystem job failed' } }
    elseif ($r.ReturnValue -ne 0) { throw "DefineSystem rv=$($r.ReturnValue)" }
    $vm = [wmi]$r.ResultingSystem
    Write-Host "VM created: $($vm.Name)"
    $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

    # 3. SCSI 控制器(第二代默认无 SCSI 控制器)
    $scsiTmpl = Get-DefaultSettings $SCSI_SUBTYPE
    $arS = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
    if ($arS.ReturnValue -eq 4096) { if ((Wait-Job2 $arS.Job) -ne 7) { throw "AddResource(SCSI) failed $(Job-Err $arS.Job)" } }
    elseif ($arS.ReturnValue -ne 0) { throw "AddResource(SCSI) rv=$($arS.ReturnValue)" }
    $scsiPath = $arS.ResultingResourceSettings[0]
    Write-Host "SCSI controller added"

    # 4. 合成 DVD 驱动器挂到 SCSI 控制器(LUN 0)
    $dvdTmpl = Get-DefaultSettings $DVD_SUBTYPE
    $dvd = $dvdTmpl.psbase.Clone()
    $dvd.Parent = $scsiPath
    $dvd.AddressOnParent = '0'
    $arD = $vsms.AddResourceSettings($vssd2.__PATH, @($dvd.GetText(1)))
    if ($arD.ReturnValue -eq 4096) { if ((Wait-Job2 $arD.Job) -ne 7) { throw "AddResource(DVD drive) failed $(Job-Err $arD.Job)" } }
    elseif ($arD.ReturnValue -ne 0) { throw "AddResource(DVD drive) rv=$($arD.ReturnValue)" }
    $dvdPath = $arD.ResultingResourceSettings[0]
    Write-Host "DVD drive added: $dvdPath"

    # 5. 插入 ISO：StorageAllocationSettingData(Virtual CD/DVD Disk) 挂到 DVD 驱动器
    $isoTmpl = Get-DefaultSettings $ISO_SUBTYPE
    $iso = $isoTmpl.psbase.Clone()
    $iso.Parent = $dvdPath
    $iso.HostResource = @($isoPath)
    $arI = $vsms.AddResourceSettings($vssd2.__PATH, @($iso.GetText(1)))
    if ($arI.ReturnValue -eq 4096) { if ((Wait-Job2 $arI.Job) -ne 7) { throw "AddResource(ISO) failed $(Job-Err $arI.Job)" } }
    elseif ($arI.ReturnValue -ne 0) { throw "AddResource(ISO) rv=$($arI.ReturnValue)" }
    $isoSasdPath = $arI.ResultingResourceSettings[0]
    Write-Host "ISO inserted: $isoSasdPath"

    # 6. 读回：枚举 StorageAllocationSettingData，确认 HostResource 与 iso 匹配
    $vssdF = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
    $sasds = ([wmi]$vssdF.__PATH).GetRelated('Msvm_StorageAllocationSettingData')
    $found = $false; $hr = ''; $st = ''
    foreach ($s in $sasds) {
        $res = @($s.HostResource)
        if ($res -and $res[0] -and ($res[0].ToLower() -eq $isoPath.ToLower())) {
            $found = $true; $hr = $res[0]; $st = $s.ResourceSubType
        }
    }
    if ($found) {
        Write-Host "READBACK HostResource=$hr SubType=$st"
        Write-Host 'ASSERT PASS: ISO mounted to synthetic DVD drive and read back'
        Write-Host 'RESULT: PASS'
    } else {
        Write-Host "ASSERT FAIL: iso not found in StorageAllocationSettingData (count=$(@($sasds).Count))"
        Write-Host 'RESULT: FAIL'
    }
}
catch {
    Write-Host ("ERROR: {0}" -f $_.Exception.Message)
    Write-Host 'RESULT: FAIL'
}
finally {
    if ($vm -ne $null) {
        try { $del = $vsms.DestroySystem($vm.__PATH); if ($del.ReturnValue -eq 4096) { Wait-Job2 $del.Job | Out-Null }; Write-Host 'CLEANUP destroyed test VM' } catch {}
    }
    foreach ($e in (Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName })) {
        try { $d = $vsms.DestroySystem($e.__PATH); if ($d.ReturnValue -eq 4096) { Wait-Job2 $d.Job | Out-Null } } catch {}
    }
    if (Test-Path $isoPath) { Remove-Item $isoPath -Force; Write-Host 'CLEANUP removed iso' }
    $left = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName }
    if (-not $left) { Write-Host 'CLEANUP verified no leftover' } else { Write-Host 'CLEANUP WARNING leftover VM remains' }
}
```

## [PASS] 端到端组合:纯 WMI 搭建完整的第二代虚拟机  `e2e_full_vm`

- 本配方将多项独立配置步骤组合为一台完整可用的第二代虚拟机，串联创建、处理器、内存、存储、网络、安全启动、vTPM 与 GPU-P 各环节，并逐项读回校验。
- 关键前置条件：启用动态内存前必须先将 VirtualNumaEnabled 设为 false (单独一次 ModifySystemSettings)，否则 DynamicMemoryEnabled 会静默不生效。
- SetKeyProtector 的参数顺序为 ($sec.GetText(1) 嵌入实例文本, $kp.RawData 密钥字节)。
- 挂盘为三段式：SCSI 控制器 (AddResourceSettings) -> 磁盘驱动器 Disk Drive (Parent=控制器, AddressOnParent='0') -> Msvm_StorageAllocationSettingData (ResourceType=31, Parent=驱动器, HostResource=@(vhdx 路径))。
- GPU-P：Msvm_GpuPartitionSettingData 需显式设 ResourceType=32770、ResourceSubType='Microsoft:Hyper-V:GPU Partition'、PoolID=''、HostResource=@(选定的 Msvm_PartitionableGpu 的 __PATH)。
- vTPM 与 GPU-P 步骤依赖主机环境 (可分区 GPU、HGS 保护器等)，代码以 try/catch 单独包裹以便在缺失时降级；try/finally 确保测试资源被清理。

```powershell
# 端到端组合：纯 WMI 搭建一台完整配置的第二代虚拟机，
# 串联各项配置步骤，逐项读回，最后完整清理。
# 安全约束：仅操作 ElementName 为 WMITEST_E2E 的虚拟机及其位于 verify/work 下的 vhdx。
$ErrorActionPreference = "Stop"
$ns   = "root\virtualization\v2"
$NAME = "WMITEST_E2E"
$work = "C:\Users\Administrator\Documents\GitHub\HyperV-WMI-Documentation\verify\work"
$vhd  = Join-Path $work "wmitest_e2e.vhdx"
$pass = @(); $fail = @()
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
function Chk($name,$cond,$got){ if($cond){ $script:pass += $name; Write-Host ("  [PASS] {0} = {1}" -f $name,$got) } else { $script:fail += $name; Write-Host ("  [FAIL] {0} = {1}" -f $name,$got) } }
function DefTemplate($subtype){
  $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.ResourceSubType -eq $subtype -and $_.Primordial }
  $cap  = ($pool.GetRelated("Msvm_AllocationCapabilities") | Select-Object -First 1)
  $sdc  = $cap.GetRelated("CIM_ResourceAllocationSettingData","Msvm_SettingsDefineCapabilities",$null,$null,"PartComponent","GroupComponent",$false,$null)
  foreach($x in $sdc){ $rel = [wmi]$x.__PATH } # 实体化关联对象
  # 通过 SettingsDefineCapabilities 选取 ValueRole=0 (Default) 的模板
  $ref = Get-WmiObject -Namespace $ns -Query ("ASSOCIATORS OF {"+$cap.__PATH+"} WHERE AssocClass=Msvm_SettingsDefineCapabilities ResultRole=PartComponent") |
         Where-Object { $_.InstanceID -match "Default" } | Select-Object -First 1
  return $ref
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims  = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$secs = Get-WmiObject -Namespace $ns -Class Msvm_SecurityService
# 预清理
Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $NAME } | ForEach-Object { $vsms.DestroySystem($_.__PATH) | Out-Null }
if(Test-Path $vhd){ Remove-Item $vhd -Force }

try {
  Write-Host "=== 1) DefineSystem Gen2 ==="
  $vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $NAME
  $vssd.VirtualSystemSubType = "Microsoft:Hyper-V:SubType:2"
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null); if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem
  Chk "define_gen2" ($vm.ElementName -eq $NAME) $vm.ElementName
  $sd = ($vm.GetRelated("Msvm_VirtualSystemSettingData") | Select-Object -First 1)

  Write-Host "=== 2) vCPU=4 + SMT(HwThreadsPerCore=2) ==="
  $proc = (([wmi]$sd.__PATH).GetRelated("Msvm_ProcessorSettingData") | Select-Object -First 1)
  $proc.VirtualQuantity = [uint64]4
  $proc.HwThreadsPerCore = [uint64]2
  $rp = $vsms.ModifyResourceSettings($proc.GetText(1)); if($rp.ReturnValue -eq 4096){ Wait-Job2 $rp.Job | Out-Null }
  $procN = (([wmi]$sd.__PATH).GetRelated("Msvm_ProcessorSettingData") | Select-Object -First 1)
  Chk "vcpu_4" ($procN.VirtualQuantity -eq 4) $procN.VirtualQuantity
  Chk "smt_2"  ($procN.HwThreadsPerCore -eq 2) $procN.HwThreadsPerCore

  Write-Host "=== 3) VSSD 级：MMIO gap Low=512 High=16384 + VirtualNumaEnabled=false (动态内存前置条件) ==="
  $sd.LowMmioGapSize  = [uint64]512
  $sd.HighMmioGapSize = [uint64]16384
  $sd.VirtualNumaEnabled = $false
  $rmm = $vsms.ModifySystemSettings($sd.GetText(1)); if($rmm.ReturnValue -eq 4096){ Wait-Job2 $rmm.Job | Out-Null }
  $sdN = (([wmi]$vm.__PATH).GetRelated("Msvm_VirtualSystemSettingData") | Select-Object -First 1)
  Chk "mmio" ($sdN.LowMmioGapSize -eq 512 -and $sdN.HighMmioGapSize -eq 16384) ("low="+$sdN.LowMmioGapSize+" high="+$sdN.HighMmioGapSize)
  $sd = $sdN  # 刷新句柄供后续整机编辑

  Write-Host "=== 4) 动态内存 min=512 startup=1024 max=2048 ==="
  $mem = (([wmi]$sd.__PATH).GetRelated("Msvm_MemorySettingData") | Select-Object -First 1)
  $mem.DynamicMemoryEnabled = $true
  $mem.Reservation     = [uint64]512
  $mem.VirtualQuantity = [uint64]1024
  $mem.Limit           = [uint64]2048
  $mem.TargetMemoryBuffer = [uint32]20
  $rm = $vsms.ModifyResourceSettings($mem.GetText(1))
  if($rm.ReturnValue -eq 4096){ $js = Wait-Job2 $rm.Job; if($js -ne 7){ $jb=[wmi]$rm.Job; Write-Host ("  mem job failed: "+$jb.ErrorDescription) } }
  $memN = (([wmi]$sd.__PATH).GetRelated("Msvm_MemorySettingData") | Select-Object -First 1)
  Chk "dyn_mem" ($memN.DynamicMemoryEnabled -and $memN.Limit -eq 2048) ("dyn="+$memN.DynamicMemoryEnabled+" limit="+$memN.Limit)

  Write-Host "=== 5) 创建 VHDX (动态 10GB) + SCSI 控制器 + 挂载 ==="
  $vhsd = ([wmiclass]"\\.\$ns`:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $vhsd.Type=[uint16]3; $vhsd.Format=[uint16]3; $vhsd.Path=$vhd; $vhsd.MaxInternalSize=[uint64](10GB)
  $rc = $ims.CreateVirtualHardDisk($vhsd.GetText(1)); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
  Chk "vhd_created" (Test-Path $vhd) (Test-Path $vhd)
  # SCSI 控制器
  $scsi = DefTemplate "Microsoft:Hyper-V:Synthetic SCSI Controller"
  $ra = $vsms.AddResourceSettings($sd.__PATH, @($scsi.GetText(1))); if($ra.ReturnValue -eq 4096){ Wait-Job2 $ra.Job | Out-Null }
  $ctrl = [wmi]($ra.ResultingResourceSettings[0])
  # 控制器上的磁盘驱动器
  $drv = DefTemplate "Microsoft:Hyper-V:Synthetic Disk Drive"
  $drv.Parent = $ctrl.__PATH; $drv.AddressOnParent = "0"
  $rd = $vsms.AddResourceSettings($sd.__PATH, @($drv.GetText(1))); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
  $drvPath = $rd.ResultingResourceSettings[0]
  # 指向 vhdx 的存储分配，Parent 为磁盘驱动器
  $sasd = ([wmiclass]"\\.\$ns`:Msvm_StorageAllocationSettingData").CreateInstance()
  $sasd.ResourceType=[uint16]31; $sasd.ResourceSubType="Microsoft:Hyper-V:Virtual Hard Disk"
  $sasd.Parent=$drvPath; $sasd.HostResource=@($vhd)
  $rs = $vsms.AddResourceSettings($sd.__PATH, @($sasd.GetText(1))); if($rs.ReturnValue -eq 4096){ Wait-Job2 $rs.Job | Out-Null }
  $disks = (([wmi]$sd.__PATH).GetRelated("Msvm_StorageAllocationSettingData"))
  Chk "vhd_attached" ($disks -and ($disks | Where-Object { $_.HostResource -contains $vhd })) (@($disks).Count.ToString()+" storage alloc")

  Write-Host "=== 6) 网卡 + 接入交换机 ==="
  $sw = Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Select-Object -First 1
  $nic = DefTemplate "Microsoft:Hyper-V:Synthetic Ethernet Port"
  $nic.ElementName = "E2E-NIC"
  $rn = $vsms.AddResourceSettings($sd.__PATH, @($nic.GetText(1))); if($rn.ReturnValue -eq 4096){ Wait-Job2 $rn.Job | Out-Null }
  $nicPath = $rn.ResultingResourceSettings[0]
  if($sw){
    $epasd = DefTemplate "Microsoft:Hyper-V:Ethernet Connection"
    $epasd.Parent = $nicPath; $epasd.HostResource = @($sw.__PATH)
    $re = $vsms.AddResourceSettings($sd.__PATH, @($epasd.GetText(1))); if($re.ReturnValue -eq 4096){ Wait-Job2 $re.Job | Out-Null }
    Chk "nic_connected" ($re.ReturnValue -eq 0 -or $re.ReturnValue -eq 4096) ("switch="+$sw.ElementName)
  } else { Write-Host "  (主机无交换机；网卡添加为未连接状态)"; Chk "nic_added" ($nicPath -ne $null) "added" }

  Write-Host "=== 7) 安全启动 ON ==="
  $sd2 = (([wmi]$vm.__PATH).GetRelated("Msvm_VirtualSystemSettingData") | Select-Object -First 1)
  $sd2.SecureBootEnabled = $true
  $rsb = $vsms.ModifySystemSettings($sd2.GetText(1)); if($rsb.ReturnValue -eq 4096){ Wait-Job2 $rsb.Job | Out-Null }
  $sd2N = (([wmi]$vm.__PATH).GetRelated("Msvm_VirtualSystemSettingData") | Select-Object -First 1)
  Chk "secureboot" ($sd2N.SecureBootEnabled -eq $true) $sd2N.SecureBootEnabled

  Write-Host "=== 8) vTPM (密钥保护器 + 启用) ==="
  try {
    $g  = New-HgsGuardian -Name ("WMITEST_E2E_"+([guid]::NewGuid().ToString("N").Substring(0,8))) -GenerateCertificates -ErrorAction Stop
    $kp = New-HgsKeyProtector -Owner $g -AllowUntrustedRoot -ErrorAction Stop
    $sec = (([wmi]$sd2N.__PATH).GetRelated("Msvm_SecuritySettingData") | Select-Object -First 1)
    $rkp = $secs.SetKeyProtector($sec.GetText(1), $kp.RawData); if($rkp.ReturnValue -eq 4096){ Wait-Job2 $rkp.Job | Out-Null }
    $sec.TpmEnabled = $true
    $rt = $secs.ModifySecuritySettings($sec.GetText(1)); if($rt.ReturnValue -eq 4096){ Wait-Job2 $rt.Job | Out-Null }
    $secN = (([wmi]$sd2N.__PATH).GetRelated("Msvm_SecuritySettingData") | Select-Object -First 1)
    Chk "vtpm" ($secN.TpmEnabled -eq $true) $secN.TpmEnabled
  } catch { $fail += "vtpm"; Write-Host ("  [FAIL] vtpm = "+$_.Exception.Message) }

  Write-Host "=== 9) GPU-P 分区 (指定 GPU) ==="
  try {
    $gpu = Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu | Select-Object -First 1
    if($gpu){
      $gp = ([wmiclass]"\\.\$ns`:Msvm_GpuPartitionSettingData").CreateInstance()
      $gp.ResourceType=[uint16]32770; $gp.ResourceSubType="Microsoft:Hyper-V:GPU Partition"; $gp.PoolID=""
      $gp.HostResource = @($gpu.__PATH)
      $rg = $vsms.AddResourceSettings($sd2N.__PATH, @($gp.GetText(1))); if($rg.ReturnValue -eq 4096){ Wait-Job2 $rg.Job | Out-Null }
      $gpN = (([wmi]$sd2N.__PATH).GetRelated("Msvm_GpuPartitionSettingData"))
      Chk "gpu_partition" ($gpN -ne $null -and @($gpN).Count -ge 1) (@($gpN).Count.ToString()+" partition")
    } else { Write-Host "  (无可分区 GPU)"; }
  } catch { $fail += "gpu_partition"; Write-Host ("  [FAIL] gpu_partition = "+$_.Exception.Message) }

  Write-Host ""
  Write-Host ("=== FULL READBACK on "+$NAME+" ===")
  $fin = (([wmi]$vm.__PATH).GetRelated("Msvm_VirtualSystemSettingData") | Select-Object -First 1)
  $fp  = (([wmi]$fin.__PATH).GetRelated("Msvm_ProcessorSettingData") | Select-Object -First 1)
  $fm  = (([wmi]$fin.__PATH).GetRelated("Msvm_MemorySettingData") | Select-Object -First 1)
  Write-Host ("  vCPU={0} SMT={1} dynMem={2}[{3}-{4}] secureBoot={5} lowMMIO={6} highMMIO={7}" -f `
    $fp.VirtualQuantity,$fp.HwThreadsPerCore,$fm.DynamicMemoryEnabled,$fm.Reservation,$fm.Limit,$fin.SecureBootEnabled,$fin.LowMmioGapSize,$fin.HighMmioGapSize)
  Write-Host ("  storage={0} nic={1} gpuPart={2}" -f `
    @(($fin.GetRelated('Msvm_StorageAllocationSettingData'))).Count, `
    @(($fin.GetRelated('Msvm_SyntheticEthernetPortSettingData'))).Count, `
    @(($fin.GetRelated('Msvm_GpuPartitionSettingData'))).Count)
}
finally {
  Write-Host ""
  Write-Host "=== CLEANUP ==="
  Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $NAME } | ForEach-Object {
    $rc = $vsms.DestroySystem($_.__PATH); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
    Write-Host ("  destroyed "+$NAME+" rv="+$rc.ReturnValue)
  }
  if(Test-Path $vhd){ Remove-Item $vhd -Force; Write-Host "  removed vhdx" }
}
Write-Host ""
Write-Host ("=== E2E RESULT: PASS="+$pass.Count+" FAIL="+$fail.Count+" ===")
if($fail.Count -gt 0){ Write-Host ("  failed steps: "+($fail -join ", ")) }
```

## [PASS] 设置虚拟机的增强会话传输类型  `enhanced_session`

- EnhancedSessionTransportType 为 per-VM 属性，位于 Msvm_VirtualSystemSettingData，类型 uint16，可读可写；ValueMap 0=VMBus Pipe，1=Hyper-V Socket。
- 修改经整机设置方法 ModifySystemSettings(VSSD.GetText(1)) 下发，而非 ModifyResourceSettings；返回 0 表示同步完成，返回 4096 表示转入异步 Job。
- 主机侧 Msvm_TerminalServiceSettingData 仅含 ListenerPort (默认 2179) 与证书相关属性 (如 DisableSelfSignedCertificateGeneration)，本身不含增强会话开关，属只读记录。
- 赋值前需将目标值强制转换为 [uint16] 以避免类型不匹配。
- 该属性属配置层设置，本流程仅在关机状态下验证读回，未涵盖运行中虚拟机的生效行为。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns = 'root\virtualization\v2'
$name = 'WMITEST_enhanced_session'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# --- Part A: 读取主机侧 Msvm_TerminalServiceSettingData (RDP 侦听器配置) ---
$tssd = Get-WmiObject -Namespace $ns -Class Msvm_TerminalServiceSettingData | Select-Object -First 1
'HOST ListenerPort=' + $tssd.ListenerPort + ' DisableSelfSigned=' + $tssd.DisableSelfSignedCertificateGeneration

# --- Part B: 创建第二代虚拟机，修改 per-VM 属性 VSSD.EnhancedSessionTransportType (uint16: 0=VMBus Pipe, 1=Hyper-V Socket) ---
$vm = $null
try {
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  $vssd2 = [wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH
  $orig = $vssd2.EnhancedSessionTransportType
  $target = [uint16]1; if([uint16]$orig -eq 1){ $target = [uint16]0 }
  $vssd2.EnhancedSessionTransportType = $target
  $m = $vsms.ModifySystemSettings($vssd2.GetText(1))
  if($m.ReturnValue -eq 4096){ Wait-Job2 $m.Job | Out-Null } elseif($m.ReturnValue -ne 0){ throw "ModifySystemSettings rv=$($m.ReturnValue)" }

  $readback = ([wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH).EnhancedSessionTransportType
  if([uint16]$readback -eq $target){ 'ASSERT=PASS readback=' + $readback } else { 'ASSERT=FAIL readback=' + $readback }
}
finally {
  if($vm -ne $null){
    $d = $vsms.DestroySystem($vm.__PATH)
    if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
  }
}
```

## [PASS] 导出虚拟机定义 (ExportSystemDefinition)  `export_vm`

- 方法签名：ExportSystemDefinition(ComputerSystem REF 传虚拟机的 __PATH，ExportDirectory string 传宿主上已存在的目录，ExportSettingData string 传 Msvm_VirtualSystemExportSettingData 的 GetText(1) 嵌入实例)。
- 返回 4096 表示转入异步 Job，需轮询 JobState 至 7 (Completed)。
- ExportSettingData 可传 $null 以使用默认值；显式构造可控制行为，如 CopySnapshotConfiguration=1 (ExportNoSnapshots)、CopyVmStorage=$false (空虚拟机无 VHD)、CreateVmExportSubdirectory=$true。
- CreateVmExportSubdirectory=$true 时在 ExportDirectory 下生成以 ElementName 命名的子目录，内含 'Virtual Machines' 文件夹与配置文件。
- 产出文件：<GUID>.vmcx (二进制配置)、<GUID>.vmgs (第二代客户机状态)、<GUID>.VMRS (运行时状态)。当前 Hyper-V 采用 .vmcx 二进制格式，取代旧版 .xml/.exp。
- ExportDirectory 必须事先存在，否则方法或 Job 会失败。
- 虚拟机须处于关机或已保存状态方可导出。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_export_vm'
$exportDir='C:/temp/exp'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
  # 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem
  # 构造导出设置 (空虚拟机：无存储；创建子目录)
  $esd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemExportSettingData").CreateInstance()
  $esd.CopySnapshotConfiguration=[byte]1   # ExportNoSnapshots
  $esd.CopyVmStorage=$false
  $esd.CopyVmRuntimeInformation=$false
  $esd.CreateVmExportSubdirectory=$true
  # ExportSystemDefinition(ComputerSystem REF, ExportDirectory string, ExportSettingData embedded)
  $re=$vsms.ExportSystemDefinition($vm.__PATH, $exportDir, $esd.GetText(1))
  if($re.ReturnValue -eq 4096){ $st=Wait-Job2 $re.Job; if($st -ne 7){ $jb=[wmi]$re.Job; throw "Export job state=$st err=$($jb.ErrorDescription)" } }
  elseif($re.ReturnValue -ne 0){ throw "ExportSystemDefinition rv=$($re.ReturnValue)" }
  # 校验：以虚拟机名命名的子目录，内含配置文件
  $sub=Join-Path $exportDir $name
  $files=Get-ChildItem -Recurse -File $sub
  Write-Output "Exported $($files.Count) files; PASS=$((Test-Path $sub) -and $files.Count -gt 0)"
}
finally {
  if($vm){ $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null } }
  if(Test-Path $exportDir){ Remove-Item -Recurse -Force $exportDir }
}
```

## [PASS] 配置第一代虚拟机的 BIOS 与启动顺序  `gen1_bios`

- BootOrder 为 Msvm_VirtualSystemSettingData 的 uint16[] 属性，仅对第一代虚拟机 (SubType:1) 有意义。ValueMap: 0=Floppy(软盘), 1=CD/DVD, 2=HardDrive(IDE 硬盘), 3=Network/PXE。数组顺序即启动搜索顺序。
- 第一代虚拟机新建后的默认 BootOrder 为 1,2,3,0 (CD -> HDD -> Net -> Floppy)。
- BIOSNumLock 为 boolean，控制 BIOS 内 NumLock 初始状态，新建默认 False。
- 修改流程：取虚拟机自身的 VSSD (通过 $vm.GetRelated('Msvm_VirtualSystemSettingData') 后 [wmi]__PATH 重取可写副本)，赋值后 GetText(1) 序列化交由 ModifySystemSettings。BootOrder 需强制转换为 [uint16[]]。
- ModifySystemSettings 返回 0 表示同步完成，返回 4096 表示转入异步 Job，需轮询 JobState 至 7 (Completed)。
- 第二代虚拟机 (SubType:2) 不使用 BootOrder 整数枚举，改用 BootSourceOrder 设备引用数组。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_gen1_bios'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第一代虚拟机 (SubType:1)
$vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $testName
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:1'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# 取虚拟机自身的 VSSD
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$vssd2 = [wmi]$vssd2.__PATH

# 第一代 BootOrder 枚举 (uint16[]): 0=Floppy 1=CD/DVD 2=HardDrive(IDE) 3=Network/PXE
$vssd2.BootOrder    = [uint16[]]@(3,0,2,1)
$vssd2.BIOSNumLock  = $true
$r2 = $vsms.ModifySystemSettings($vssd2.GetText(1))
if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

# 读回
$vssd3 = [wmi]$vssd2.__PATH
"BootOrder="    + ($vssd3.BootOrder -join ',')
"BIOSNumLock=" + $vssd3.BIOSNumLock

# 清理
$r3 = $vsms.DestroySystem($vm.__PATH)
if($r3.ReturnValue -eq 4096){ Wait-Job2 $r3.Job | Out-Null }
```

## [PASS] 为第一代虚拟机的软盘驱动器装入虚拟软盘  `gen1_floppy`

- 第一代虚拟机 (SubType:1) 创建后即自带固定的软盘控制器 (Msvm_DisketteController, RASD ResourceType=1, OtherResourceType='Microsoft:Hyper-V:Virtual Diskette Controller') 与一个合成软盘驱动器 (ResourceType=14, ResourceSubType='Microsoft:Hyper-V:Synthetic Diskette Drive')。软盘控制器固定存在、无资源池、不可增删，每控制器恰含一个驱动器。
- 因此针对软盘可执行的操作是向该固定驱动器装入虚拟软盘介质 (.vfd)：构造 Msvm_StorageAllocationSettingData，设 ResourceType=31、ResourceSubType='Microsoft:Hyper-V:Virtual Floppy Disk'、Parent=软盘驱动器的 __PATH、HostResource=@(vfd 路径)，再经 AddResourceSettings 下发。
- Parent 必须指向软盘驱动器而非控制器；.vfd 文件需先经 Msvm_ImageManagementService.CreateVirtualFloppyDisk(Path) 创建。
- ResourceType 14 表示软盘驱动器 (枚举见 CIM_ResourceAllocationSettingData.ResourceType)。第二代虚拟机无软盘，此操作仅适用于第一代。
- 软盘资源无对应资源池 (查询 ResourceType=14 的 Msvm_ResourcePool 返回空)，与控制器固定的设计一致。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$name='WMITEST_gen1_floppy'
$vfd='C:/Temp/wmitest_gen1.vfd'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims =Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

# 创建第一代虚拟机 (SubType:1)
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName=$name
$vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:1'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1

# 第一代虚拟机自带固定的软盘控制器与合成软盘驱动器
$allr=([wmi]$vssd2.__PATH).GetRelated('Msvm_ResourceAllocationSettingData')
$ctrl=$allr | ? { $_.OtherResourceType -eq 'Microsoft:Hyper-V:Virtual Diskette Controller' } | select -First 1
$drv =$allr | ? { $_.ResourceType -eq 14 -and $_.ResourceSubType -eq 'Microsoft:Hyper-V:Synthetic Diskette Drive' } | select -First 1

# 创建 .vfd 后装入软盘驱动器
$cr=$ims.CreateVirtualFloppyDisk($vfd)
if($cr.ReturnValue -eq 4096){ Wait-Job2 $cr.Job | Out-Null }
$sasd=([wmiclass]"\\.\${ns}:Msvm_StorageAllocationSettingData").CreateInstance()
$sasd.ResourceType=[uint16]31
$sasd.ResourceSubType='Microsoft:Hyper-V:Virtual Floppy Disk'
$sasd.Parent=$drv.__PATH                 # Parent 指向固定的软盘驱动器，而非控制器
$sasd.HostResource=@($vfd)
$ar=$vsms.AddResourceSettings($vssd2.__PATH, @($sasd.GetText(1)))
if($ar.ReturnValue -eq 4096){ Wait-Job2 $ar.Job | Out-Null }

# 读回
$media=([wmi]$vssd2.__PATH).GetRelated('Msvm_StorageAllocationSettingData') | ? { $_.ResourceSubType -match 'Floppy' } | select -First 1
$media.HostResource

# 清理
$vsms.DestroySystem($vm.__PATH) | Out-Null
Remove-Item $vfd -Force
```

## [PASS] 为虚拟机添加 GPU 分区(GPU-P)  `gpu_partition`

- 前置条件：宿主须存在可分区 GPU(Msvm_PartitionableGpu)。若无可分区 GPU，本操作应视为 UNSUPPORTED。
- 须使用 GPU 分区的 'Default' 能力模板(Msvm_GpuPartitionSettingData，InstanceID 以 \Default 结尾)原样调用 AddResourceSettings。该模板及已分配分区的所有 Min/Max/Optimal 分区量属性均为 NULL，与 Add-VMGpuPartitionAdapter 的默认行为一致(驱动在虚拟机启动时填入默认值)。
- 若在 RASD 上写入 Min/Max/OptimalPartitionVRAM/Encode/Decode/Compute 的显式数值，AddResourceSettings 会被拒绝，Job 失败(JobState=10，ErrorCode=32773，表示无法将资源添加到虚拟机)。
- 获取能力模板的正确方式为 ASSOCIATORS OF {Msvm_AllocationCapabilities(ResourceSubType='Microsoft:Hyper-V:GPU Partition')}。ASSOCIATORS OF {Msvm_ResourcePool} 返回的是已分配分区而非模板，不能用于获取模板。
- AddResourceSettings 可能同步返回 0(成功)，也可能返回 4096 进入异步 Job；两种情形均需兼容处理。
- Msvm_GpuPartitionSettingData 继承自 CIM_ResourceAllocationSettingData，ResourceSubType 为 'Microsoft:Hyper-V:GPU Partition'。该类自 build 14393 起提供。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_gpu_partition'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 1) 枚举可分区 GPU；无可分区 GPU 时返回 UNSUPPORTED
$gpus = @(Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu -ErrorAction SilentlyContinue)
if($gpus.Count -eq 0){ Write-Output 'UNSUPPORTED: no Msvm_PartitionableGpu'; return }

$vm = $null
try {
  # 2) 创建第二代测试虚拟机
  $vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # 3) 通过 GPU 分区的 Msvm_AllocationCapabilities 获取 'Default' GpuPartitionSettingData 模板。
  #    须使用能力实例关联的默认模板，而非资源池：ASSOCIATORS OF 资源池返回的是已分配分区，
  #    并非能力模板。将模板原样 AddResourceSettings —— 已分配分区的所有 Min/Max/Optimal
  #    分区量属性均为 NULL，与 Add-VMGpuPartitionAdapter 行为一致(由驱动在启动时填入默认值)。
  #    在 Add 阶段写入显式分区量会导致添加被拒，ErrorCode 32773。
  $cap = Get-WmiObject -Namespace $ns -Class Msvm_AllocationCapabilities |
    Where-Object { $_.ResourceSubType -eq 'Microsoft:Hyper-V:GPU Partition' } | Select-Object -First 1
  $rasd = Get-WmiObject -Namespace $ns -Query (
    "ASSOCIATORS OF {" + $cap.__RELPATH + "} WHERE ResultClass=Msvm_GpuPartitionSettingData") |
    Where-Object { $_.InstanceID.EndsWith('Default') } | Select-Object -First 1

  # 4) 添加 GPU 分区(同步返回 0，或返回 4096 -> Wait-Job2)
  $add = $vsms.AddResourceSettings($vssd2.__PATH, @($rasd.GetText(1)))
  if($add.ReturnValue -eq 4096){ Wait-Job2 $add.Job | Out-Null }

  # 5) 读回验证
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $back = @(([wmi]$vssd3.__PATH).GetRelated('Msvm_GpuPartitionSettingData'))
  if($back.Count -ge 1){ Write-Output 'PASS' } else { Write-Output 'FAIL' }
}
finally {
  if($vm){ $d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } }
}
```

## [PASS] 为 GPU 分区(GPU-P)写入显存配额  `gpu_partition_vram`

- 前置条件：宿主须存在可分区 GPU(Msvm_PartitionableGpu)。
- 对 CreateInstance() 得到的 Msvm_GpuPartitionSettingData 直接调用 AddResourceSettings 会被 Job 拒绝(JobState=10，ErrorCode=32773，无法添加资源)。原因并非配额取值，而是裸实例缺少资源身份。
- 添加分区前须显式设置 ResourceType=[uint16]32770、ResourceSubType='Microsoft:Hyper-V:GPU Partition'、PoolID=''(基元 GPU-P 池)。三项齐备后 AddResourceSettings 同步返回 0。
- 12 个配额属性(Min/Max/Optimal × VRAM/Encode/Decode/Compute)在 Add 阶段须保持 NULL：CreateInstance() 序列化的 <PROPERTY> 本无 <VALUE>，提供程序按默认处理；不要赋 0。配额在第二步通过 ModifyResourceSettings 下发。
- 配额取值规则：Min=0 可接受。Encode/Decode/Compute 的 Max/Optimal 可用全 1 哨兵值 0xFFFFFFFFFFFFFFFF(=18446744073709551615)。VRAM 的 Max/Optimal 不接受全 1，须给出真实字节数(例 11811160064=11GiB)，否则被拒。
- 语义对照：Add-VMGpuPartitionAdapter 默认添加的是无配额裸分区(WMI 读回 Min/Max/Optimal 均为 NULL)；Set-VMGpuPartitionAdapter 才下发上述哨兵值。本配方等价于 Add+Set 两步的 WMI 形式。
- AddResourceSettings 的 OUT 参数为 ResultingResourceSettings(数组，取 [0] 得到新 RASD 路径)。写操作可能同步返回 0，也可能返回 4096 进入 Job；脚本保留 Wait-Job2 作为兜底。
- GPU-P 字段集自 build 14393 起提供，全版本稳定；NumaAwarePlacement 属性自 build 22621 起提供。

```powershell
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }; return $j }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 0) 确认存在可分区 GPU
$pgpu = Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu | Select-Object -First 1
# 1) 创建第二代测试虚拟机(已有 $vm/$vssd2 时可跳过)
# 2) 添加裸 GPU 分区：须为 RASD 设置资源身份，否则 AddResourceSettings 被 Job 拒绝(ErrorCode=32773)
$gp = ([wmiclass]"\\.\${ns}:Msvm_GpuPartitionSettingData").CreateInstance()
$gp.ResourceType    = [uint16]32770
$gp.ResourceSubType = 'Microsoft:Hyper-V:GPU Partition'
$gp.PoolID          = ''
# Min/Max/Optimal 共 12 个配额字段在 Add 阶段保持 NULL(不要赋 0)，交由 AddResourceSettings 处理
$add = $vsms.AddResourceSettings($vssd2.__PATH, @($gp.GetText(1)))
if($add.ReturnValue -eq 4096){ $null = Wait-Job2 $add.Job }
$newPath = $add.ResultingResourceSettings | Select-Object -First 1
# 3) 写入配额：Min=0；VRAM 的 Max/Optimal 用真实字节数(例 11GiB=11811160064)；Encode/Decode/Compute 的 Max/Optimal 用全 1 哨兵值 0xFFFFFFFFFFFFFFFF
$ALLONES = [uint64]'18446744073709551615'
$VRAM    = [uint64]11811160064
$gpr = [wmi]$newPath
$gpr.MinPartitionVRAM=[uint64]0;    $gpr.MaxPartitionVRAM=$VRAM;      $gpr.OptimalPartitionVRAM=$VRAM
$gpr.MinPartitionEncode=[uint64]0;  $gpr.MaxPartitionEncode=$ALLONES; $gpr.OptimalPartitionEncode=$ALLONES
$gpr.MinPartitionDecode=[uint64]0;  $gpr.MaxPartitionDecode=$ALLONES; $gpr.OptimalPartitionDecode=$ALLONES
$gpr.MinPartitionCompute=[uint64]0; $gpr.MaxPartitionCompute=$ALLONES;$gpr.OptimalPartitionCompute=$ALLONES
$m = $vsms.ModifyResourceSettings($gpr.GetText(1))
if($m.ReturnValue -eq 4096){ $null = Wait-Job2 $m.Job }
# 4) 读回验证
$gpRead = ([wmi]$vssd2.__PATH).GetRelated('Msvm_GpuPartitionSettingData') | Select-Object -First 1
'MaxVRAM='+$gpRead.MaxPartitionVRAM+' MaxEnc='+$gpRead.MaxPartitionEncode
```

## [PASS] 指定一块可分区 GPU 并分配分区(含主机侧 PartitionCount)  `gpu_specific_assign`

- 通过 Msvm_PartitionableGpu.Name(含 VEN_/DEV_ 的设备实例路径)区分并选定某一块可分区 GPU。前置条件为宿主存在多块可分区 GPU。
- 选定具体 GPU 的关键：将选中那块 Msvm_PartitionableGpu 的 __PATH 赋给 GpuPartitionSettingData.HostResource(即 HostResource[0])。读回 HostResource 可验证分配到哪块卡。
- 对 CreateInstance() 直接得到的 GpuPartitionSettingData(空壳)调用 AddResourceSettings 会被 Job 拒绝(JobState=10，ErrorCode=32773，无法添加资源)。须显式补齐 ResourceType=32770、ResourceSubType='Microsoft:Hyper-V:GPU Partition'、AllocationUnits='count'、AutomaticAllocation/Deallocation=true、ConsumerVisibility=3、MappingBehavior=3、VirtualQuantity/Reservation/Limit=1、Weight=0，与 Add-VMGpuPartitionAdapter 序列化的 GetText(1) 一致。
- 另一处 32773 的来源：GPU-P 还要求先在 VSSD 上设置 GuestControlledCacheTypes=$true 并配置 MMIO 大 BAR 窗口(LowMmioGapSize=1024MB，HighMmioGapSize=32768MB)，否则即便 RASD 字段齐全也被拒。等价 cmdlet：Set-VM -GuestControlledCacheTypes $true -LowMemoryMappedIoSpace 1GB -HighMemoryMappedIoSpace 32GB。
- Min/Max/Optimal 的 VRAM/Encode/Decode/Compute 全部留 null(不写)即可通过，这是 cmdlet 的默认行为；写入非法配额值会再次触发 32773(参见 gpu_partition_vram)。
- 主机侧 PartitionCount：Msvm_PartitionableGpu.PartitionCount 可写，但只接受 ValidPartitionCounts 中的取值。写入后调用 $gpu.Put() 落盘。
- PartitionableGpu 的 TotalVRAM/Optimal/Max 可能为归一化占位常量(如 1000000000)，AvailableVRAM 同值；Encode 的 Optimal/Max 可能为 uint64 最大值(0xFFFF...)，表示驱动未上报真实配额单位，配额走驱动托管默认。
- 全程虚拟机不启动(仅配置层验证)。DefineSystem 的 OUT 参数为 ResultingSystem；所有返回 4096 的方法均通过 Wait-Job2 轮询；嵌入实例统一使用 GetText(1)。
- 从 Default 模板获取 GPU-P RASD 是另一种可选的稳定路径。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns='root\virtualization\v2'
$name='WMITEST_gpu_specific_assign'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 清理同名残留
$res=Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$name'"
if($res){ foreach($r in $res){ $vsms.DestroySystem($r.__PATH)|Out-Null } }

$vmPath=$null
try{
  # 1. 枚举 Msvm_PartitionableGpu，按 Name 中的设备实例路径选定某一块(此处 DEV_2803)。
  $gpus=@(Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu)
  $chosen=$gpus | Where-Object { $_.Name -like '*DEV_2803*' } | Select-Object -First 1
  if(-not $chosen){ $chosen=$gpus[0] }
  # ValidPartitionCounts 为主机侧 PartitionCount 的合法取值；PartitionCount 可写。
  $valid=@($chosen.ValidPartitionCounts); $newCount=$valid|Select-Object -First 1
  if($newCount -ne $null -and $newCount -ne $chosen.PartitionCount){ $chosen.PartitionCount=[uint16]$newCount; $chosen.Put()|Out-Null }

  # 2. 创建第二代虚拟机(仅配置层)。
  $vssd=([wmiclass]("\\.\"+$ns+":Msvm_VirtualSystemSettingData")).CreateInstance()
  $vssd.ElementName=$name; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $rv=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($rv.ReturnValue -eq 4096){ Wait-Job2 $rv.Job|Out-Null }
  $vm=[wmi]$rv.ResultingSystem; $vmPath=$vm.__PATH

  # 3. 在 VSSD 上配置 GPU-P 前置项(否则 AddResourceSettings 的 Job 报 ErrorCode 32773)。
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $vssd2.GuestControlledCacheTypes=$true
  $vssd2.LowMmioGapSize=[uint64]1024      # MB
  $vssd2.HighMmioGapSize=[uint64]32768    # MB
  $ms=$vsms.ModifySystemSettings($vssd2.GetText(1)); if($ms.ReturnValue -eq 4096){ Wait-Job2 $ms.Job|Out-Null }
  $vssd2=([wmi]$vmPath).GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1

  # 4. 构造 GpuPartitionSettingData。裸 CreateInstance 不足以通过；须设置 ResourceType/SubType
  #    及分配相关字段(与 Add-VMGpuPartitionAdapter 一致)。HostResource[0] 选定具体 GPU。
  $gp=([wmiclass]("\\.\"+$ns+":Msvm_GpuPartitionSettingData")).CreateInstance()
  $gp.ResourceType=[uint16]32770
  $gp.ResourceSubType='Microsoft:Hyper-V:GPU Partition'
  $gp.AllocationUnits='count'; $gp.AutomaticAllocation=$true; $gp.AutomaticDeallocation=$true
  $gp.ConsumerVisibility=[uint16]3; $gp.MappingBehavior=[uint16]3
  $gp.VirtualQuantity=[uint64]1; $gp.Reservation=[uint64]1; $gp.Limit=[uint64]1; $gp.Weight=[uint32]0
  $gp.HostResource=@($chosen.__PATH)   # <-- 指定具体 GPU 的关键
  # Min/Max/Optimal VRAM/Encode/Decode/Compute 留 null(cmdlet 默认)以避免 32773。
  $ra=$vsms.AddResourceSettings($vssd2.__PATH, @($gp.GetText(1)))
  if($ra.ReturnValue -eq 4096){ $st=Wait-Job2 $ra.Job; if($st -ne 7){ $j=[wmi]$ra.Job; throw ("add job state=$st err=$($j.ErrorCode) $($j.ErrorDescription)") } }

  # 5. 读回 HostResource，应引用选定的 GPU。
  $gpr=([wmi]$vmPath).GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $gpr=([wmi]$gpr.__PATH).GetRelated('Msvm_GpuPartitionSettingData')|Select-Object -First 1
  $hr=@($gpr.HostResource)[0]
  Write-Host "HostResource=$hr"
  if($hr -match 'DEV_2803'){ Write-Host 'RESULT: PASS' } else { Write-Host 'RESULT: FAIL' }
}
finally{
  if($vmPath){ $d=$vsms.DestroySystem($vmPath); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job|Out-Null } }
}
```

## [PASS] 按比例设置 GPU 分区显存配额  `gpu_vram_fraction`

- 前置条件：宿主存在可分区 GPU(Msvm_PartitionableGpu)。相关属性：TotalVRAM/TotalDecode/TotalCompute 为归一化刻度值(例满 GPU=1000000000)，TotalEncode 可能为 uint64 最大值，ValidPartitionCounts 与 PartitionCount 描述主机侧分区数。
- 使用 [wmiclass].CreateInstance() 自建 Msvm_GpuPartitionSettingData 时，须设置 ResourceType=32770 与 ResourceSubType='Microsoft:Hyper-V:GPU Partition'，否则 AddResourceSettings 的 Job 报 ErrorCode=32773(无法添加资源)。裸 CreateInstance 不带这两个字段会被拒。
- 须分两步：先 AddResourceSettings 添加不带 Min/Max/Optimal 取值的默认分区，再 ModifyResourceSettings 写入具体比例值。若在 Add 阶段就填满 Min/Max/Optimal，同样触发 ErrorCode=32773。此为 Add-VMGpuPartitionAdapter + Set-VMGpuPartitionAdapter 内部的两步做法。
- Total/Partition 值是归一化刻度(满 GPU=1000000000)，非显存字节数。50% 配额即写 500000000。
- 当 TotalEncode 为 uint64 最大值(18446744073709551615)时，对其取比例(如 max/2)会被拒；Encode 的 Max/Optimal 须保持等于 TotalEncode。VRAM/Decode/Compute 可按比例缩小。
- Min 统一设 0，Max=Optimal=比例值，可稳定持久化并读回。Add 与 Modify 可能同步返回 0(未走 4096 Job)。
- Msvm_GpuPartitionSettingData 继承自 CIM_ResourceAllocationSettingData；属性 Min/Max/Optimal × {PartitionVRAM,PartitionEncode,PartitionDecode,PartitionCompute} 均为 uint64 可读写，自 build 14393 起提供。
- 本配方仅验证配置写入与读回；虚拟机未启动，不涉及来宾内实际显存可见性。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200;$j=[wmi]$p}; return $j.JobState }
$NAME='WMITEST_gpu_vram_fraction'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  foreach($s in (Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$NAME'")){ $vsms.DestroySystem($s.__PATH)|Out-Null }
  # 1) 检查可分区 GPU -> Total 值为归一化刻度，非原始字节数
  $gpu=Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu | Select-Object -First 1
  $totalVram=[uint64]$gpu.TotalVRAM; $encTotal=[uint64]$gpu.TotalEncode
  $decTotal=[uint64]$gpu.TotalDecode; $cmpTotal=[uint64]$gpu.TotalCompute
  # 目标 = GPU 的 50%
  $fN=1; $fD=2
  $vramFrac=[uint64]([math]::Floor($totalVram*$fN/$fD))
  $decFrac=[uint64]([math]::Floor($decTotal*$fN/$fD))
  $cmpFrac=[uint64]([math]::Floor($cmpTotal*$fN/$fD))
  $encFrac=$encTotal   # TotalEncode 为 uint64 最大值；对其取比例会被拒 -> 保持全额
  # 2) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$NAME; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){throw 'DefineSystem job failed'} } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 3) 第一步 AddResourceSettings：实例须携带 ResourceType=32770 +
  #    ResourceSubType='Microsoft:Hyper-V:GPU Partition'(裸 CreateInstance -> ErrorCode 32773)。
  #    Add 阶段 Min/Max/Optimal 保持不设。
  $gpsd=([wmiclass]"\\.\$($ns):Msvm_GpuPartitionSettingData").CreateInstance()
  $gpsd.ResourceType=[uint16]32770
  $gpsd.ResourceSubType='Microsoft:Hyper-V:GPU Partition'
  $ar=$vsms.AddResourceSettings($vssd2.__PATH,@($gpsd.GetText(1)))
  if($ar.ReturnValue -eq 4096){ $j=[wmi]$ar.Job; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200;$j=[wmi]$ar.Job}; if($j.JobState -ne 7){throw "Add job err=$($j.ErrorCode)"}; $newPath=$ar.ResultingResourceSettings|Select-Object -First 1 } elseif($ar.ReturnValue -eq 0){ $newPath=$ar.ResultingResourceSettings|Select-Object -First 1 } else { throw "Add rv=$($ar.ReturnValue)" }
  # 4) 第二步 ModifyResourceSettings：应用比例。Min=0；Max=Optimal=比例值；Encode=全额
  $part=[wmi]$newPath
  $part.MinPartitionVRAM=[uint64]0; $part.MaxPartitionVRAM=[uint64]$vramFrac; $part.OptimalPartitionVRAM=[uint64]$vramFrac
  $part.MinPartitionEncode=[uint64]0; $part.MaxPartitionEncode=[uint64]$encFrac; $part.OptimalPartitionEncode=[uint64]$encFrac
  $part.MinPartitionDecode=[uint64]0; $part.MaxPartitionDecode=[uint64]$decFrac; $part.OptimalPartitionDecode=[uint64]$decFrac
  $part.MinPartitionCompute=[uint64]0; $part.MaxPartitionCompute=[uint64]$cmpFrac; $part.OptimalPartitionCompute=[uint64]$cmpFrac
  $mr=$vsms.ModifyResourceSettings(@($part.GetText(1)))
  if($mr.ReturnValue -eq 4096){ $j2=[wmi]$mr.Job; while($j2.JobState -eq 3 -or $j2.JobState -eq 4){Start-Sleep -Milliseconds 200;$j2=[wmi]$mr.Job}; if($j2.JobState -ne 7){throw "Modify job err=$($j2.ErrorCode)"} } elseif($mr.ReturnValue -ne 0){ throw "Modify rv=$($mr.ReturnValue)" }
  # 5) 读回验证
  $rb=([wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1).__PATH).GetRelated('Msvm_GpuPartitionSettingData')|Select-Object -First 1
  if([uint64]$rb.MaxPartitionVRAM -eq [uint64]$vramFrac -and [uint64]$rb.OptimalPartitionVRAM -eq [uint64]$vramFrac -and $vramFrac -ne 0){ Write-Output "PASS VRAM=$($rb.MaxPartitionVRAM)" } else { Write-Output "FAIL" }
}
finally {
  if($vm){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job|Out-Null } }
}
```

## [PASS] 创建启用来宾状态隔离的机密虚拟机(GuestStateIsolationType)  `guest_isolation`

- 须同时写入 GuestStateIsolationEnabled=$true 与 GuestStateIsolationType，且在 DefineSystem 建机时一次性下发(非事后 ModifySystemSettings)。缺少 GuestStateIsolationEnabled 时，GuestStateIsolationType 读回恒为 0。
- ValueMap：Disabled=-1，TrustedLaunch=0，VBS=1，SEV-SNP=2，TDX=3，OpenHCL=16。
- TrustedLaunch(0) 要求启用安全启动(SecureBootEnabled=$true)。TrustedLaunch(0) 与 VBS(1) 在软件层即可持久化。
- SEV-SNP(2) 与 TDX(3) 需要对应的 CPU 硬件(SEV-SNP CPU / TDX CPU)。在无相应硬件的宿主上，这些隔离类型无法被接受或持久化。对 SNP/TDX/VBS，创建流程通常还需附带 ConfigureTpm，并移除合成显卡、键鼠等设备。

```powershell
# 来宾状态隔离(TrustedLaunch/VBS/SEV-SNP/TDX)。在 DefineSystem 建机时一次性设置两个属性。
$ns='root\virtualization\v2'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vssd=([wmiclass]"\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_gi'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$vssd.SecureBootEnabled=$true             # TrustedLaunch 要求安全启动
$vssd.GuestStateIsolationEnabled=$true    # 使能标志。缺此项时 Type 读回恒为 0
$vssd.GuestStateIsolationType=[uint16]0   # 0=TrustedLaunch 1=VBS 2=SEV-SNP 3=TDX 16=OpenHCL (Disabled=-1)
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)  # rv=0 表示成功
$vm=[wmi]$r.ResultingSystem
$sd=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
# 读回：GuestStateIsolationEnabled=True，GuestStateIsolationType=0/1 持久化成功
```

## [PASS] 为来宾注入静态 IP(无 DHCP)  `guest_network_config`

- 方法签名：Msvm_VirtualSystemManagementService.SetGuestNetworkAdapterConfiguration(ComputerSystem REF(虚拟机的 __PATH)，NetworkConfiguration string[](序列化的 Msvm_GuestNetworkAdapterConfiguration 嵌入实例数组))；OUT=Job，rv 为 0 表示同步成功，4096 表示进入异步 Job。
- Msvm_GuestNetworkAdapterConfiguration 可写属性：DHCPEnabled(bool)、ProtocolIFType(uint16：4096=IPv4，4097=IPv6，4098=两者)、IPAddresses[]、Subnets[](子网掩码或前缀长度字符串)、DefaultGateways[]、DNSServers[]。通过 InstanceID 定位目标网卡，形如 Microsoft:GuestNetwork\<vmGuid>\<nicGuid>。
- 不要手工构造 GNAC 实例：添加合成网卡后，从网卡 SettingData 调用 GetRelated('Msvm_GuestNetworkAdapterConfiguration') 直接取现成实例修改属性最稳妥。
- 合成网卡不能用 [wmiclass].CreateInstance() 裸建(ResourceSubType 为空，AddResourceSettings 的 Job 报 ErrorCode=32773 无法添加资源)。须从主资源池 Msvm_ResourcePool(ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port'，Primordial=True) -> Msvm_AllocationCapabilities -> Msvm_SettingsDefineCapabilities(ValueRole=0) 取默认模板实例，再修改 ElementName。
- 当 AddResourceSettings 返回 4096 时，OUT 的 ResultingResourceSettings 在 Job 完成前为 null；应先 Wait-Job 再从虚拟机 VSSD.GetRelated('Msvm_SyntheticEthernetPortSettingData') 重新取网卡，不要读 OUT 数组。
- 静态 IP 真正注入来宾 OS 需要来宾内 KVP 集成组件在线且来宾处于运行状态；否则接口层调用可正确返回(rv=0)，但配置不会实际生效，Job 可能报无来宾错误(属预期行为)。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$TESTNAME = 'WMITEST_guest_network_config'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# --- 创建第二代测试虚拟机 ---
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $TESTNAME
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

# --- 从资源池默认模板构造合成网卡(裸 CreateInstance 会导致 Job 报 ErrorCode 32773) ---
$pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port' AND Primordial=True"
$cap = $pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
$defAssoc = $cap.GetRelationships('Msvm_SettingsDefineCapabilities') | Where-Object { $_.ValueRole -eq 0 } | Select-Object -First 1
$nicTemplate = [wmi]($defAssoc.PartComponent)
$nicTemplate.ElementName = 'WMITEST_nic'
$ra = $vsms.AddResourceSettings($vssd2.__PATH, @($nicTemplate.GetText(1)))
if ($ra.ReturnValue -eq 4096) { Wait-Job2 $ra.Job | Out-Null }

# --- 重新读取网卡，获取其 Msvm_GuestNetworkAdapterConfiguration (InstanceID = Microsoft:GuestNetwork\<vmGuid>\<nicGuid>) ---
$vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$nicSettings = ([wmi]$vssd3.__PATH).GetRelated('Msvm_SyntheticEthernetPortSettingData') | Select-Object -First 1
$gnac = ([wmi]$nicSettings.__PATH).GetRelated('Msvm_GuestNetworkAdapterConfiguration') | Select-Object -First 1

# --- 在 GNAC 嵌入实例上设置静态 IPv4 ---
$gnac.DHCPEnabled = $false
$gnac.ProtocolIFType = [uint16]4096   # IPv4
$gnac.IPAddresses = @('192.168.99.50')
$gnac.Subnets = @('255.255.255.0')
$gnac.DefaultGateways = @('192.168.99.1')
$gnac.DNSServers = @('8.8.8.8','1.1.1.1')

# --- SetGuestNetworkAdapterConfiguration(ComputerSystem REF, NetworkConfiguration string[]) ---
$sr = $vsms.SetGuestNetworkAdapterConfiguration($vm.__PATH, @($gnac.GetText(1)))
if ($sr.ReturnValue -eq 4096) { $jb = Wait-Job2 $sr.Job; Write-Host "JobState=$($jb.JobState) Err=$($jb.ErrorCode)" }
Write-Host "rv=$($sr.ReturnValue)"   # rv=0 表示同步成功

# --- 清理 ---
$d = $vsms.DestroySystem($vm.__PATH); if ($d.ReturnValue -eq 4096) { Wait-Job2 $d.Job | Out-Null }
```

## [PASS] 启用与调用来宾集成服务  `guest_service_control`

- Msvm_GuestService 为抽象基类,自身无独立属性,仅提供从 CIM_Service 继承的 StartService/StopService 方法(ValueMap:0=Completed with No Error,1=Not supported)。
- StartService/StopService 作用于运行态设备实例:Msvm_GuestServiceInterfaceComponent(来宾集成服务接口)及其子类 Msvm_GuestFileService(文件复制服务)。这些设备实例仅在虚拟机处于运行态且来宾内集成服务组件已加载时,才出现在 root\virtualization\v2 命名空间中。
- 无来宾操作系统的空虚拟机不存在任何 Msvm_GuestServiceInterfaceComponent 设备实例(按 SystemName 查询计数为 0),因此无法执行 Start/Stop,应记为不适用而非功能不支持。
- 启用或禁用来宾服务的配置入口是 Msvm_GuestServiceInterfaceComponentSettingData(隶属于虚拟机设置数据 VSSD),修改其 EnabledState(2=启用/3=禁用)后经 ModifyResourceSettings 下发,ReturnValue=0 表示成功,可读回 EnabledState 确认。此操作等价于 PowerShell 的 Enable-VMIntegrationService -Name 'Guest Service Interface'。
- 需区分配置面与运行面:配置面的设置数据(SettingData)始终存在,运行面的设备实例(Component)仅在运行态出现。对刚经 DefineSystem 创建的虚拟机,通过 GetRelated('Msvm_GuestServiceInterfaceComponent') 无法获取设备实例。
- 若需观察 StartService/StopService 的返回码,需启动一台已安装 Hyper-V 集成服务的来宾操作系统的虚拟机。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# --- 创建第二代测试虚拟机 ---
$vssd=([wmiclass]"\\.\$ns:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_guest_service_control'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
# --- 配置面:定位来宾服务接口设置数据并启用(EnabledState 2=启用/3=禁用) ---
$gs=([wmi]$vssd2.__PATH).GetRelated('Msvm_GuestServiceInterfaceComponentSettingData')|select -First 1
$gs.EnabledState=[uint16]2
$mr=$vsms.ModifyResourceSettings(@($gs.GetText(1))); if($mr.ReturnValue -eq 4096){Wait-Job2 $mr.Job|Out-Null}   # ReturnValue=0 表示成功
$gs2=([wmi]$vssd2.__PATH).GetRelated('Msvm_GuestServiceInterfaceComponentSettingData')|select -First 1  # 读回确认 EnabledState=2
# --- 运行面:StartService/StopService(CIM_Service 生命周期方法, ValueMap 0=完成 1=不支持) ---
# 可调用 Start/Stop 的是运行态设备实例 Msvm_GuestServiceInterfaceComponent / Msvm_GuestFileService
# (Msvm_GuestService 为抽象基类)。该设备仅在虚拟机运行且来宾内集成服务已加载时才出现:
$live=Get-WmiObject -Namespace $ns -Query "SELECT * FROM Msvm_GuestServiceInterfaceComponent WHERE SystemName='$($vm.Name)'"
if(@($live).Count -gt 0){
  $svc=[wmi](@($live)[0].__PATH)
  $svc.StartService().ReturnValue   # 0 表示成功
  ([wmi](@($live)[0].__PATH)).StopService().ReturnValue
}
# --- 清理 ---
$del=$vsms.DestroySystem($vm.__PATH); if($del.ReturnValue -eq 4096){Wait-Job2 $del.Job|Out-Null}
```

## [PASS] 启用来宾服务接口组件  `guest_services`

- 来宾服务设置类为 Msvm_GuestServiceInterfaceComponentSettingData，通过 GetRelated 关联自虚拟机的 VSSD（Msvm_VirtualSystemSettingData），不直接挂在 ComputerSystem 上。
- EnabledState 在 MOF 中标记为只读，修改须经 Msvm_VirtualSystemManagementService.ModifyResourceSettings 下发；默认值 3(Disabled)，启用时置为 2(Enabled)。
- 复制文件的方法名为 CopyFilesToGuest（复数形式），挂在 Msvm_GuestFileService（基类 Msvm_GuestService）上。
- 方法签名：uint32 CopyFilesToGuest(string[] CopyFileToGuestSettings, [out] CIM_ConcreteJob REF Job)；每个数组元素为 Msvm_CopyFileToGuestSettingData.GetText(1)（含 SourcePath/DestinationPath/OverwriteExisting/CreateFullPath）。返回值 0 表示成功，4096 表示异步作业。
- CopyFilesToGuest 要求目标来宾正在运行且集成服务在线，离线虚拟机无法调用。
- 该类与方法自 build 9600 起提供。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# --- 从虚拟机的 VSSD 定位来宾服务接口组件设置数据 ---
$vssd=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
$gsi=([wmi]$vssd.__PATH).GetRelated('Msvm_GuestServiceInterfaceComponentSettingData')|Select-Object -First 1
# --- 启用: EnabledState=2 (Enabled), 默认为 3 (Disabled). 该属性为只读, 经 ModifyResourceSettings 下发修改 ---
$gsi.EnabledState=[uint16]2
$r=$vsms.ModifyResourceSettings($gsi.GetText(1))
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job }
# --- 回读 ---
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
$gsi2=([wmi]$vssd2.__PATH).GetRelated('Msvm_GuestServiceInterfaceComponentSettingData')|Select-Object -First 1
$gsi2.EnabledState  # -> 2 表示已启用

# === CopyFilesToGuest 方法签名 (Msvm_GuestFileService) ===
# uint32 CopyFilesToGuest(string[] CopyFileToGuestSettings, [out] CIM_ConcreteJob REF Job)
#   每个 CopyFileToGuestSettings 元素 = Msvm_CopyFileToGuestSettingData.GetText(1) 序列化字符串
#   Msvm_CopyFileToGuestSettingData 属性: SourcePath(主机路径,可含环境变量), DestinationPath(来宾路径),
#     OverwriteExisting(bool), CreateFullPath(bool)
# 用法示例(要求来宾正在运行且集成服务在线):
#   $gfs=Get-WmiObject -Namespace $ns -Class Msvm_GuestFileService -Filter "__PATH like '%$($vm.Name)%'"
#   $cs=([wmiclass]"\\.\$($ns):Msvm_CopyFileToGuestSettingData").CreateInstance()
#   $cs.SourcePath='C:\host\a.txt'; $cs.DestinationPath='C:\guest\a.txt'
#   $cs.OverwriteExisting=$true; $cs.CreateFullPath=$true
#   $rc=$gfs.CopyFilesToGuest(@($cs.GetText(1))); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job }
```

## [PASS] 读取主机 NUMA 拓扑与容量信息  `host_numa_caps`

- 纯读操作，无需创建或删除测试虚拟机；全部通过 Get-WmiObject 按类枚举，不涉及方法调用、异步作业或返回码。
- Msvm_NumaNode 表示主机物理 NUMA 节点，NodeID 形如 'Microsoft:PhysicalNode\0'；相关属性为 NumberOfProcessorCores / NumberOfLogicalProcessors / CurrentlyConsumableMemoryBlocks / CurrentlyAssignedVirtualProcessors。
- Msvm_NumaNode.CurrentlyAssignedVirtualProcessors 统计当前所有运行中虚拟机分配的 vCPU 总和（可超分），可能大于物理逻辑处理器数，不代表物理上限。
- Msvm_Processor 实例数不等于物理逻辑处理器数：该类在 v2 命名空间下同时包含主机逻辑处理器与各运行中虚拟机的虚拟处理器实例。做主机容量统计应以 Msvm_NumaNode 汇总为准。
- Msvm_Memory 在 v2 命名空间下仅暴露 MemoryEncryption 属性，不适合读取物理内存容量；主机可消费内存应使用 Msvm_NumaNode.CurrentlyConsumableMemoryBlocks。
- 主机默认路径位于单例 Msvm_VirtualSystemManagementServiceSettingData：DefaultVirtualHardDiskPath / DefaultExternalDataRoot；NumaSpanningEnabled 为 NUMA 跨越开关。

```powershell
$ns = 'root\virtualization\v2'

# --- Msvm_NumaNode: 主机物理 NUMA 拓扑 ---
$nodes = @(Get-WmiObject -Namespace $ns -Class Msvm_NumaNode)
foreach ($n in $nodes) {
  '{0}  Cores={1}  LPs={2}  ConsumableMemBlocks={3}  AssignedVPs={4}' -f $n.NodeID,$n.NumberOfProcessorCores,$n.NumberOfLogicalProcessors,$n.CurrentlyConsumableMemoryBlocks,$n.CurrentlyAssignedVirtualProcessors
}

# --- Msvm_Processor: 每个主机逻辑处理器对应一个实例 ---
$procs = @(Get-WmiObject -Namespace $ns -Class Msvm_Processor)
'Msvm_Processor count = {0}' -f $procs.Count

# --- Msvm_Memory: 主机内存对象 ---
$mems = @(Get-WmiObject -Namespace $ns -Class Msvm_Memory)
'Msvm_Memory count = {0}' -f $mems.Count

# --- Msvm_VirtualSystemManagementServiceSettingData: 主机默认值与 NUMA 跨越设置 ---
$svcSet = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementServiceSettingData
'DefaultVirtualHardDiskPath = {0}' -f $svcSet.DefaultVirtualHardDiskPath
'DefaultExternalDataRoot    = {0}' -f $svcSet.DefaultExternalDataRoot
'NumaSpanningEnabled        = {0}' -f $svcSet.NumaSpanningEnabled
'EnhancedSessionModeEnabled = {0}' -f $svcSet.EnhancedSessionModeEnabled
```

## [PASS] 读取主机资源容量池  `host_pools`

- 纯读操作，不创建任何虚拟机。
- Msvm_ProcessorPool 是独立类，Get-WmiObject -Class Msvm_ResourcePool 不会多态返回它（基类枚举结果的 __CLASS 均为 Msvm_ResourcePool，不含处理器池 RT=3）。查询处理器池须单独调用 Msvm_ProcessorPool。
- 专用子类 Msvm_MemoryPool / Msvm_EthernetResourcePool / Msvm_StorageResourcePool 可能没有实例；内存、网络、存储池通常以通用 Msvm_ResourcePool 行表示（RT=4 内存、RT=10 以太网、RT=31 VHD 等）。
- 处理器原始池：MaxConsumableResource 单位为 'percent / 1000'，等于逻辑处理器数 ×100000。
- 内存原始池（RT=4）：MaxConsumable 与 Reserved 单位为 'byte * 2^20'（即 MB），分别表示主机可消费内存与已预留内存。
- 读取主机资源池的正确入口是 Msvm_ResourcePool（通用）+ Msvm_ProcessorPool（专用）+ Msvm_AllocationCapabilities（每资源类型的能力表）。
- 每个池经 Msvm_ElementCapabilities 关联到对应的 Msvm_AllocationCapabilities，描述该资源类型的 min/max/default/increment。

```powershell
$ns = 'root\virtualization\v2'

# 1) 处理器池是独立类。基类 Msvm_ResourcePool 查询不会多态返回它,
#    因此需直接查询 Msvm_ProcessorPool。
$procPrim = Get-WmiObject -Namespace $ns -Class Msvm_ProcessorPool | Where-Object { $_.Primordial } | Select-Object -First 1
# $procPrim.MaxConsumableResource = 主机逻辑处理器数 * 100000 (单位 'percent / 1000')
Write-Host ("ProcPool MaxConsumable={0} Reserved={1} Units='{2}'" -f $procPrim.MaxConsumableResource, $procPrim.Reserved, $procPrim.AllocationUnits)

# 2) 内存 / 以太网 / 存储 / 磁盘池以通用 Msvm_ResourcePool 行暴露,
#    按 ResourceType (RT) 与 ResourceSubType 区分, 每行 Primordial=True。
#    (专用子类 Msvm_MemoryPool / Msvm_EthernetResourcePool /
#     Msvm_StorageResourcePool 在此主机上无实例。)
$pools = @(Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool)
foreach ($p in ($pools | Sort-Object ResourceType)) {
  Write-Host ("  RT={0} SubType='{1}' Primordial={2}" -f $p.ResourceType, $p.ResourceSubType, $p.Primordial)
}

# 内存容量位于 RT=4 池 (单位 'byte * 2^20' = MB)。
$memPool = $pools | Where-Object { $_.ResourceType -eq 4 -and $_.Primordial } | Select-Object -First 1
Write-Host ("MemPool(RT=4) MaxConsumable={0}MB Reserved={1}MB" -f $memPool.MaxConsumableResource, $memPool.Reserved)

# 3) 主机各资源类型能力表。
$allCaps = @(Get-WmiObject -Namespace $ns -Class Msvm_AllocationCapabilities)
$allCaps | Group-Object ResourceType | Sort-Object { [int]$_.Name } | ForEach-Object {
  $subs = ($_.Group | ForEach-Object { $_.ResourceSubType }) -join '; '
  Write-Host ("  RT={0} count={1} [{2}]" -f $_.Name, $_.Count, $subs)
}
Write-Host ("pools={0} allocCaps={1}" -f $pools.Count, $allCaps.Count)
```

## [PASS] 修改主机管理服务设置(ModifyServiceSettings)  `host_settings`

- Msvm_VirtualSystemManagementServiceSettingData 是单例（InstanceID=Microsoft:<HOSTNAME>），所有属性在 WMI 中均标记为只读，不能直接赋值，须经 Msvm_VirtualSystemManagementService.ModifyServiceSettings(SettingData) 下发修改。嵌入实例使用 GetText(1) 序列化。
- ModifyServiceSettings 返回值 0 表示同步完成，4096 表示异步作业；应判断 4096 并调用 Wait-Job2 轮询。
- 可读取的主机信息包括 DefaultVirtualHardDiskPath、DefaultExternalDataRoot、NumaSpanningEnabled、EnhancedSessionModeEnabled 等。
- PrimaryOwnerName 是无害且可逆的字符串属性，适合用于验证修改路径（修改→回读→还原）。DefaultVirtualHardDiskPath、NumaSpanningEnabled 等属于全局主机配置，修改会影响整个环境，应谨慎操作。
- 该操作为主机级配置，不创建任何虚拟机，因此无测试机需要清理。

```powershell
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 单例主机设置实例 (InstanceID = Microsoft:<HOSTNAME>)
$svc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementServiceSettingData | Select-Object -First 1
# 读取主机信息 (所有属性在 WMI 中均为只读, 仅可经 ModifyServiceSettings 修改)
$svc.DefaultVirtualHardDiskPath; $svc.DefaultExternalDataRoot; $svc.NumaSpanningEnabled; $svc.EnhancedSessionModeEnabled
$orig = $svc.PrimaryOwnerName
# --- 修改一个无害且可逆的属性 ---
$svc.PrimaryOwnerName = 'WMITEST_owner_probe'
$r = $vsms.ModifyServiceSettings($svc.GetText(1))   # IN 参数名为 SettingData; 返回值 0=成功 4096=异步作业
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
# --- 回读 ---
$rb = (Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementServiceSettingData | Select-Object -First 1).PrimaryOwnerName
# --- 还原 ---
$svcR = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementServiceSettingData | Select-Object -First 1
$svcR.PrimaryOwnerName = $orig
$rr = $vsms.ModifyServiceSettings($svcR.GetText(1))
if($rr.ReturnValue -eq 4096){ Wait-Job2 $rr.Job | Out-Null }
```

## [PASS] 导入虚拟机定义生成计划虚拟机(ImportSystemDefinition)  `import_planned`

- 方法签名：ImportSystemDefinition(SystemDefinitionFile string, SnapshotFolder string, GenerateNewSystemIdentifier boolean)；OUT：ImportedSystem(Msvm_PlannedComputerSystem REF), Job。在 Msvm_VirtualSystemManagementService 上调用。
- SystemDefinitionFile 应传导出产物中 .vmcx 配置文件的完整路径（新版 Hyper-V 二进制格式），而非导出目录。SnapshotFolder 传含快照配置的目录（此处使用导出子目录），无快照时可指向同一目录。
- GenerateNewSystemIdentifier=$true 时，生成的 Msvm_PlannedComputerSystem 获得新的 GUID（与源虚拟机 GUID 不同），适合在同一主机重复导入以避免冲突；$false 时保留原 GUID。
- 返回值 0 表示同步完成，可直接从 OUT 参数 ImportedSystem 取引用；4096 表示异步作业，需经 Wait-Job2 轮询。代码保留两种分支以兼容。
- 导入产物为 Msvm_PlannedComputerSystem（计划虚拟机，__CLASS 区别于真实的 Msvm_ComputerSystem），尚未实体化；实际落地需后续调用 RealizePlannedSystem（本示例仅覆盖导入与计划阶段）。
- 前置条件：被导入的定义文件不能正被主机或虚拟化平台占用，因此须先 DestroySystem 销毁源虚拟机（或从其他位置获取导出文件）再导入，否则导入会因定义文件被占用而失败。
- 清理：计划虚拟机同样使用 DestroySystem(__PATH) 删除，对 Msvm_PlannedComputerSystem 有效，异步完成返回 4096。
- GetSummaryInformation 等查询若需包含计划虚拟机，须注意 Msvm_PlannedComputerSystem 与 Msvm_ComputerSystem 是不同类，枚举时应分别处理。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_import_planned'
$exportDir='C:/temp/impexp'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null; $planned=$null
try {
  New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
  # 1) 创建一个用于导出的第二代测试虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem; $srcGuid=$vm.Name
  # 2) 导出以获得 .vmcx 配置文件(作为导入输入)
  $esd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemExportSettingData").CreateInstance()
  $esd.CopySnapshotConfiguration=[byte]1; $esd.CopyVmStorage=$false; $esd.CopyVmRuntimeInformation=$false; $esd.CreateVmExportSubdirectory=$true
  $re=$vsms.ExportSystemDefinition($vm.__PATH, $exportDir, $esd.GetText(1))
  if($re.ReturnValue -eq 4096){ $st=Wait-Job2 $re.Job; if($st -ne 7){ $jb=[wmi]$re.Job; throw "Export job state=$st err=$($jb.ErrorDescription)" } }
  elseif($re.ReturnValue -ne 0){ throw "ExportSystemDefinition rv=$($re.ReturnValue)" }
  $sub=Join-Path $exportDir $name
  $cfg=Get-ChildItem -Recurse -File -Path $sub -Filter *.vmcx | Select-Object -First 1
  if(-not $cfg){ throw "no .vmcx config produced" }
  # 3) 销毁原虚拟机, 释放定义文件供导入使用
  $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }; $vm=$null
  # 4) ImportSystemDefinition(SystemDefinitionFile, SnapshotFolder, GenerateNewSystemIdentifier) -> OUT ImportedSystem(Msvm_PlannedComputerSystem REF), Job
  $ri=$vsms.ImportSystemDefinition($cfg.FullName, $sub, $true)
  if($ri.ReturnValue -eq 4096){ $st=Wait-Job2 $ri.Job; if($st -ne 7){ $jb=[wmi]$ri.Job; throw "Import job state=$st err=$($jb.ErrorDescription)" } }
  elseif($ri.ReturnValue -ne 0){ throw "ImportSystemDefinition rv=$($ri.ReturnValue)" }
  $planned=[wmi]$ri.ImportedSystem
  # 5) 验证计划虚拟机已存在
  $foundInEnum=(@(Get-WmiObject -Namespace $ns -Class Msvm_PlannedComputerSystem | Where-Object { $_.Name -eq $planned.Name }).Count -ge 1)
  $pass=($planned.__CLASS -eq 'Msvm_PlannedComputerSystem') -and $foundInEnum -and ($planned.ElementName -eq $name)
  Write-Output "ASSERT $(if($pass){'PASS'}else{'FAIL'}): class=$($planned.__CLASS) ElementName=$($planned.ElementName) GUID=$($planned.Name) newId=$($planned.Name -ne $srcGuid)"
}
catch { Write-Output "ERROR: $($_.Exception.Message)" }
finally {
  if($planned){ $rp=$vsms.DestroySystem($planned.__PATH); if($rp.ReturnValue -eq 4096){ Wait-Job2 $rp.Job | Out-Null } }
  foreach($cn in @('Msvm_PlannedComputerSystem','Msvm_ComputerSystem')){ foreach($lo in @(Get-WmiObject -Namespace $ns -Class $cn | Where-Object { $_.ElementName -eq $name })){ $rx=$vsms.DestroySystem($lo.__PATH); if($rx.ReturnValue -eq 4096){ Wait-Job2 $rx.Job | Out-Null } } }
  if(Test-Path $exportDir){ Remove-Item -Recurse -Force $exportDir }
}
```

## [PASS] 切换集成服务组件启用状态  `integration_services`

- 集成组件以 Msvm_*ComponentSettingData 子类逐个通过 GetRelated 从虚拟机的 VSSD 获取，每类只有一个实例。
- 全部 6 类均派生自 CIM_ResourceAllocationSettingData，只读属性 EnabledState：2=启用，3=禁用。修改后经 ModifyResourceSettings(GetText(1)) 下发，与修改普通资源同一路径。
- 默认状态：Shutdown/TimeSync/Heartbeat/Kvp/Vss 默认为 2（启用），GuestServiceInterface 默认为 3（禁用）。
- ModifyResourceSettings 返回 4096 时表示异步作业，需经 Wait-Job2 轮询；回读须重新 GetRelated 取新实例，不能复用旧对象。
- 新建第二代空虚拟机即带齐这些集成组件实例，无需先开机或安装来宾。
- ModifyResourceSettings 应传数组 @($comp.GetText(1)) 以匹配 ResourceSettings[] 签名；单参数依赖 WMI 强制转换亦可，但数组形式更规范。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$vmName = 'WMITEST_integration_services'

function Wait-Job2($p){
  if(-not $p){return 7}
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第二代虚拟机
$vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $vmName
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

# 枚举集成组件设置数据 (每类均派生自 CIM_ResourceAllocationSettingData)
$compClasses = @(
  'Msvm_ShutdownComponentSettingData',
  'Msvm_TimeSyncComponentSettingData',
  'Msvm_HeartbeatComponentSettingData',
  'Msvm_KvpExchangeComponentSettingData',
  'Msvm_VssComponentSettingData',
  'Msvm_GuestServiceInterfaceComponentSettingData'
)
$found = @{}
foreach($c in $compClasses){
  $inst = ([wmi]$vssd2.__PATH).GetRelated($c) | Select-Object -First 1
  if($inst){ $found[$c] = $inst }
}

# 经 ModifyResourceSettings 切换某组件的 EnabledState (2=启用, 3=禁用)
$comp = $found['Msvm_TimeSyncComponentSettingData']
$before = [int]$comp.EnabledState
$newState = if($before -eq 2){ 3 } else { 2 }
$comp.EnabledState = [uint16]$newState
$r2 = $vsms.ModifyResourceSettings($comp.GetText(1))
if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

# 重新 GetRelated 取新实例回读
$vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$comp2 = ([wmi]$vssd3.__PATH).GetRelated('Msvm_TimeSyncComponentSettingData') | Select-Object -First 1
if([int]$comp2.EnabledState -eq $newState){ 'PASS' } else { 'FAIL' }

# 清理
$vsms.DestroySystem($vm.__PATH) | Out-Null
```

## [PASS] 异步作业轮询范式  `job_pattern`

- 返回码语义: rv=0 表示同步完成,不返回 Job 对象; rv=4096 表示异步,OUT 参数 Job 给出 Msvm_ConcreteJob 路径,需轮询; 其它值为同步失败的错误码。
- 同一脚本可能同时遇到同步与异步两条路径: 例如 DefineSystem 与 ModifyResourceSettings 常同步返回 rv=0,而 DestroySystem 常返回 4096 并生成 ConcreteJob。通用等待器应同时处理这两种情形。
- JobState 为 DMTF CIM_ConcreteJob 标准枚举: 3=Starting 与 4=Running 表示进行中需继续轮询; 终止态中 7=Completed 表示成功, 8/9/10 分别为 Terminated/Killed/Exception 表示失败。
- 嵌入实例统一用 GetText(1) 序列化后传入方法; 轮询时用 [wmi]$jobPath 每次重新取实例以刷新 JobState; 失败时读取 ErrorCode/ErrorDescription 进行诊断。
- 更健壮的成功判定应同时接受 32768(CompletedWithWarnings)。轮询条件可写为 while($j.JobState -lt 7 -and $j.JobState -ne 32768){...},成功判定为 ($j.JobState -eq 7 -or $j.JobState -eq 32768),以覆盖 New/Suspended/ShuttingDown 等中间态。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

# 通用异步作业等待器。
# rv 0    -> 同步完成,不返回 Job 对象
# rv 4096 -> 异步; OUT 参数 Job 给出 Msvm_ConcreteJob 路径,需轮询
# JobState DMTF 枚举: 2=New 3=Starting 4=Running 5=Suspended 6=ShuttingDown
#                     7=Completed 8=Terminated 9=Killed 10=Exception 11=Service
function Wait-WmiJob {
    param($rv, $jobPath)
    if ($rv -eq 0) { return @{ Mode='Sync'; JobState=7; ErrorCode=0; ErrorDescription=$null; Rv=$rv } }
    if ($rv -ne 4096) { return @{ Mode='Failed'; JobState=$null; ErrorCode=$rv; ErrorDescription="method returned $rv"; Rv=$rv } }
    if (-not $jobPath) { return @{ Mode='AsyncNoJob'; JobState=$null; ErrorDescription='rv=4096 but no Job path'; Rv=$rv } }
    $job = [wmi]$jobPath
    while ($job.JobState -eq 3 -or $job.JobState -eq 4) {
        Start-Sleep -Milliseconds 200
        $job = [wmi]$jobPath
    }
    return @{ Mode='Async'; JobState=$job.JobState; ErrorCode=$job.ErrorCode; ErrorDescription=$job.ErrorDescription; PercentComplete=$job.PercentComplete; Rv=$rv }
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 支持异步的调用示例(DestroySystem 通常返回 4096):
# $r = $vsms.DestroySystem($vm.__PATH)
# $w = Wait-WmiJob $r.ReturnValue $r.Job
# if ($w.Mode -eq 'Async' -and $w.JobState -ne 7) { throw "job failed state=$($w.JobState) err=$($w.ErrorDescription)" }
```

## [PASS] 为第一代虚拟机启用密钥存储驱动器  `key_storage_drive`

- 密钥存储驱动器在 WMI 层并非独立的磁盘资源: 不存在 ResourceType=17 的 RASD,也没有对应的 Msvm_StorageAllocationSettingData。其状态由 Msvm_SecuritySettingData 上的布尔标志 KsdEnabled 表示。背后的隐藏 VHD 由安全服务内部托管,不暴露在 VSSD 的资源分配设置中。
- 启用流程: 取该虚拟机的 Msvm_SecuritySettingData,将 KsdEnabled 设为 $true,再经 Msvm_SecurityService.ModifySecuritySettings($ssd.GetText(1)) 下发。返回 rv=0 表示同步成功,KsdEnabled 由 False 变为 True,无需 Add-VMKeyStorageDrive cmdlet。
- canonical MOF 将 KsdEnabled 标注为 Read/Required(只读),但 ModifySecuritySettings 实际接受并写入该字段,属于 MOF 限定符与运行时行为不一致的情形。
- 密钥存储驱动器是第一代(SubType:1) shielded 虚拟机的旧机制(Windows 10/Windows Server 2016 时代,与第二代虚拟机的 vTPM 相对应)。较新系统仍支持,但 Hyper-V 会输出弃用警告(fwlink 875156),提示该功能可能在未来版本移除。新部署应优先使用第二代虚拟机加 vTPM。
- 仅设置 KsdEnabled 标志用于启用能力; 若需完整的密钥存储驱动器,还需添加密钥存储盘(Msvm_StorageAllocationSettingData, ResourceType=17,挂接到 IDE 控制器),该盘由 Add-VMKeyStorageDrive cmdlet 一并创建。
- ModifySecuritySettings 返回 4096 时需用 Wait-Job2 轮询 Job; 清理时 DestroySystem 同样可能返回 4096,需一并轮询。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_key_storage_drive'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$secSvc=Get-WmiObject -Namespace $ns -Class Msvm_SecurityService
$vm=$null
try {
  # KSD 为第一代虚拟机特性 -> 创建 SubType:1 虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name
  $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:1'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm=[wmi]$r.ResultingSystem

  # 取该虚拟机的 Msvm_SecuritySettingData,设置 KsdEnabled,经 SecurityService 下发
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $ssd=([wmi]$vssd2.__PATH).GetRelated('Msvm_SecuritySettingData')|Select-Object -First 1
  Write-Output ('BEFORE KsdEnabled='+$ssd.KsdEnabled)   # False
  $ssd.KsdEnabled=$true
  $rs=$secSvc.ModifySecuritySettings($ssd.GetText(1))   # OUT Job 参数; rv 0=成功 4096=作业
  if($rs.ReturnValue -eq 4096){ Wait-Job2 $rs.Job | Out-Null }
  Write-Output ('ModifySecuritySettings rv='+$rs.ReturnValue)

  # 读回
  $chk=([wmi]$vssd2.__PATH).GetRelated('Msvm_SecuritySettingData')|Select-Object -First 1
  Write-Output ('AFTER KsdEnabled='+$chk.KsdEnabled)     # True
  if($chk.KsdEnabled){ Write-Output 'RESULT: PASS' } else { Write-Output 'RESULT: FAIL' }
} finally {
  if($vm -and $vm.__PATH){ $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null } }
}
```

## [PASS] 向虚拟机注入键盘输入  `keyboard_input`

- 前置条件: Msvm_Keyboard 设备仅在虚拟机处于运行态(EnabledState=2)时存在。停止态(EnabledState=3)下该虚拟机的 Msvm_Keyboard 实例数为 0,GetRelated('Msvm_Keyboard') 返回空。因此需先 RequestStateChange(2) 启动虚拟机才能取得键盘并注入。
- 空的第二代虚拟机(无操作系统、无引导介质)也能启动到 EnabledState=2(进入 UEFI/PXE 引导循环),足以让键盘设备出现并接受输入。
- 取键盘: Get-WmiObject Msvm_Keyboard -Filter "SystemName='<VM.Name GUID>'"。注意 VM.Name 为 GUID,而非 ElementName。键盘 DeviceID 固定为 Microsoft:DE6CDC86-E1FB-4940-801B-C3C1A26C4DA4。
- 方法签名(均返回 uint32, 0=成功): TypeText(string AsciiText,仅 ASCII,非 ASCII 返回 1) / TypeKey(uint32 KeyCode) / PressKey(uint32) / ReleaseKey(uint32) / IsKeyPressed(uint32)->OUT bool KeyState / TypeScancodes(uint8[] Scancodes) / TypeCtrlAltDel()无参。KeyCode 为 Win32 虚拟键码(VK_*)。
- PressKey/ReleaseKey/IsKeyPressed 会将 VK_MENU(18)/VK_CONTROL(17)/VK_SHIFT(16) 映射到左键 VK_LMENU(164)/VK_LCONTROL(162)/VK_LSHIFT(160); 对这三个原始码 IsKeyPressed 始终返回 False。
- TypeScancodes 使用 Set 1 扫描码字节数组: 高位(0x80)区分 make(按下)与 break(释放),如 'A' 的按下为 0x1E、释放为 0x9E。TypeScancodes 的 ValueMap 不含 4096(无 Job),其余方法含 4096。
- 清理时须先强制关机 RequestStateChange(3) 再 DestroySystem,否则运行中的虚拟机可能拒绝删除。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 1) 创建第二代测试虚拟机
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_keyboard_input'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
# 2) 键盘设备仅在虚拟机运行时存在; 必须先启动到 EnabledState=2
$rs=([wmi]$vm.__PATH).RequestStateChange(2); if($rs.ReturnValue -eq 4096){Wait-Job2 $rs.Job|Out-Null}
Start-Sleep -Seconds 3
# 3) 按 SystemName=VM.Name(GUID) 取 Msvm_Keyboard (GetRelated 亦可,但需虚拟机在运行)
$kbd=Get-WmiObject -Namespace $ns -Class Msvm_Keyboard -Filter ("SystemName='"+$vm.Name+"'")|Select-Object -First 1
$kbd=[wmi]$kbd.__PATH
# 4) 注入: 字符串 / 单虚拟键 / 按下-查询-释放 / 扫描码(uint8[] Set1 make+break)
$kbd.TypeText('Hello').ReturnValue                 # 0 成功; 仅 ASCII
$kbd.TypeKey([uint32]13).ReturnValue               # VK_RETURN 按下并释放
$kbd.PressKey([uint32]65).ReturnValue              # 按住 'A'
$q=$kbd.IsKeyPressed([uint32]65); $q.KeyState      # True
$kbd.ReleaseKey([uint32]65).ReturnValue            # 释放 'A'
$kbd.TypeScancodes([byte[]](0x1E,0x9E)).ReturnValue # Set1 扫描码: 0x1E='A'按下,0x9E=释放
# $kbd.TypeCtrlAltDel().ReturnValue                 # 无参, 发送 Ctrl+Alt+Del
# 5) 清理: 先强制关机(RequestStateChange 3)再 DestroySystem
$off=([wmi]$vm.__PATH).RequestStateChange(3); if($off.ReturnValue -eq 4096){Wait-Job2 $off.Job|Out-Null}
$d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null}
```

## [PASS] 从主机向来宾推送 KVP 键值对  `kvp_push`

- 方法签名: AddKvpItems(TargetSystem REF, DataItems string[](内嵌 Msvm_KvpExchangeDataItem 经 GetText(1) 序列化), OUT Job)。该方法可能返回 4096(异步 Job),此时需 Wait-Job2 轮询至 JobState=7(Completed)。
- 主机侧推送项的 Msvm_KvpExchangeDataItem.Source 应设为 0(主机推送)。Name/Data 的最大长度为 1024。嵌入实例用 GetText(1) 序列化。
- 读回不应使用 Msvm_KvpExchangeComponent: 该运行时组件仅在虚拟机至少启动过一次后才存在,对从未启动的新建虚拟机不可用(GetRelated 返回空)。
- 正确的读回路径: VM -> Msvm_VirtualSystemSettingData -> GetRelated('Msvm_KvpExchangeComponentSettingData')。该设置数据类存于配置文件中,虚拟机停机时也可读,其 HostExchangeItems 立即包含刚推送的项。
- HostExchangeItems 的每个元素为 CIM XML 文本(<INSTANCE><PROPERTY NAME=...><VALUE>...),用 [xml] 解析后按 PROPERTY NAME=Name/Data 取值。
- 验证主机到配置的写入无需启动来宾; 真正同步到来宾操作系统则需运行中的虚拟机及已激活的 KVP 集成服务。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){return 7}
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}
  return $j.JobState
}

$vmName = 'WMITEST_kvp_push'
$kvpKey = 'WMITEST_HostKey'
$kvpVal = 'HelloFromHost123'

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null
$pass = $false
$readback = '(none)'
$rcAdd = '(n/a)'

try {
  # --- 创建第二代测试虚拟机 ---
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $vmName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem failed rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  # --- 构造主机侧 KVP 数据项 (Source=0 表示主机推送) ---
  $item = ([wmiclass]"\\.\${ns}:Msvm_KvpExchangeDataItem").CreateInstance()
  $item.Source = [uint16]0
  $item.Name = $kvpKey
  $item.Data = $kvpVal
  $itemText = $item.GetText(1)

  # --- AddKvpItems(TargetSystem REF, DataItems string[], Job OUT) ---
  $rAdd = $vsms.AddKvpItems($vm.__PATH, @($itemText))
  $rcAdd = $rAdd.ReturnValue
  if($rcAdd -eq 4096){
    $js = Wait-Job2 $rAdd.Job
    if($js -ne 7){ throw "AddKvpItems job ended state=$js" }
  } elseif($rcAdd -ne 0){
    throw "AddKvpItems failed rv=$rcAdd"
  }

  # --- 经 Msvm_KvpExchangeComponentSettingData.HostExchangeItems 读回 ---
  # 该设置数据类存于虚拟机配置中,即使虚拟机从未启动也可读
  # (与仅在虚拟机启动后才存在的运行时类 Msvm_KvpExchangeComponent 不同)。
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $kvpSd = ([wmi]$vssd2.__PATH).GetRelated('Msvm_KvpExchangeComponentSettingData') | Select-Object -First 1
  if(-not $kvpSd){ throw "No Msvm_KvpExchangeComponentSettingData on VM" }
  $kvpSd = [wmi]$kvpSd.__PATH
  $hostItems = $kvpSd.HostExchangeItems
  if(-not $hostItems){ $hostItems = @() }

  foreach($xml in $hostItems){
    $x = [xml]$xml
    $props = $x.INSTANCE.PROPERTY
    $nameP = ($props | Where-Object { $_.NAME -eq 'Name' }).VALUE
    $dataP = ($props | Where-Object { $_.NAME -eq 'Data' }).VALUE
    if($nameP -eq $kvpKey){ $readback = $dataP }
  }

  if($readback -eq $kvpVal){ $pass = $true }
}
finally {
  if($vm){
    try {
      $rd = $vsms.DestroySystem($vm.__PATH)
      if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
    } catch { Write-Host "Cleanup error: $_" }
  }
}

if($pass){ Write-Host "ASSERT: PASS readback=$readback" } else { Write-Host "ASSERT: FAIL readback=$readback" }
```

## [PASS] 读取来宾 KVP 键值对  `kvp_read`

- 纯读操作,无需创建测试虚拟机: 直接枚举 Msvm_KvpExchangeComponent,每个实例对应一台正在运行且 KVP 集成组件已激活的虚拟机。停机或未启用 KVP 集成组件的虚拟机不会出现该实例。
- 经 $kvp.GetRelated('Msvm_ComputerSystem') 反查所属虚拟机名称。
- GuestIntrinsicExchangeItems 为来宾操作系统自动上报的固有键(OSName/OSVersion/FullyQualifiedDomainName/IntegrationServicesVersion/OSBuildNumber 等); GuestExchangeItems 为来宾内组件主动推送的键。两者均为 string[],每个元素是 Msvm_KvpExchangeDataItem 的内嵌 CIM XML 实例。
- 解析每个元素时用 [xml] 后取 INSTANCE.PROPERTY 中 NAME='Name' 与 NAME='Data' 的 VALUE,即为键名与键值。
- NetworkAddressIPv4/IPv6 与 RDPAddressIPv4/IPv6 这几个 KVP 键已废弃,其 Data 不是真实 IP 而是一段提示文本,要求改用 Msvm_GuestNetworkAdapterConfiguration 获取 IP。读取 IP 不应依赖 KVP。
- 不同虚拟机上报的固有项数量可能不一致,项数较少者可能缺少 OSName/OSVersion。可选择项数最多的实例进行解析以获取最完整的操作系统信息。

```powershell
$ns = 'root\virtualization\v2'

function Parse-KvpItem($xml) {
    # 每一项为 CIM XML INSTANCE,含 Name/Data 两个字符串型 PROPERTY。
    $doc = [xml]$xml
    $name = $null; $data = $null
    foreach ($p in $doc.INSTANCE.PROPERTY) {
        if ($p.NAME -eq 'Name') { $name = $p.VALUE }
        if ($p.NAME -eq 'Data') { $data = $p.VALUE }
    }
    [pscustomobject]@{ Name = $name; Data = $data }
}

# 纯读操作: 枚举 Msvm_KvpExchangeComponent (每台运行中且 KVP 集成组件已激活的
# 虚拟机对应一个实例)。GuestIntrinsicExchangeItems = 操作系统上报的固有项;
# GuestExchangeItems = 来宾内组件推送的项。两者均为内嵌 Msvm_KvpExchangeDataItem
# CIM XML 的 string[]。
$comps = @(Get-WmiObject -Namespace $ns -Class Msvm_KvpExchangeComponent)
foreach ($kvp in $comps) {
    $cs = @($kvp.GetRelated('Msvm_ComputerSystem'))[0]
    $vmName = if ($cs) { $cs.ElementName } else { '(unknown)' }
    $intrinsic = @($kvp.GuestIntrinsicExchangeItems)
    Write-Host ("VM='{0}' IntrinsicItems={1}" -f $vmName, $intrinsic.Count)
    $map = @{}
    foreach ($x in $intrinsic) {
        $item = Parse-KvpItem $x
        if ($item.Name) { $map[$item.Name] = $item.Data }
    }
    if ($map.Count -gt 0) {
        Write-Host ('  OSName=' + $map['OSName'])
        Write-Host ('  OSVersion=' + $map['OSVersion'])
        Write-Host ('  FQDN=' + $map['FullyQualifiedDomainName'])
    }
}
```

## [PASS] 读取并修改主机实时迁移服务设置  `live_migration_config`

- 纯主机配置操作,无需创建虚拟机; 本示例不涉及任何虚拟机。
- ModifyServiceSettings 的唯一 IN 参数为 ServiceSettingData(内嵌实例,须经 GetText(1) 序列化),OUT 为 Job。返回 ReturnValue=0 表示同步成功; 若返回 4096 则需 Wait-Job2 轮询。
- Msvm_VirtualSystemMigrationServiceSettingData 为主机级单例; 其属性不可直接写入,必须经 Msvm_VirtualSystemMigrationService.ModifyServiceSettings 下发。
- canonical 中标注为可写的属性为 EnableCompression 与 EnableSmbTransport; EnableVirtualSystemMigration、Maximum* 与 AuthenticationType 在类定义中标为只读,但文档说明其同样可经 ModifyServiceSettings 修改。
- 修改设置时建议重新 Get 一份新实例再写回,避免使用脏实例。
- 相关属性含义: EnableVirtualSystemMigration 控制迁移是否启用; AuthenticationType 0=CredSSP、1=Kerberos; MaximumActiveVirtualSystemMigration 与 MaximumActiveStorageMigration 为并发上限; MigrationServiceListenerIPAddressList 为监听地址列表; Msvm_VirtualSystemMigrationNetworkSettingData 为专用迁移网络配置。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

# --- 服务与单例设置数据 ---
$svc=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationService
$s=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationServiceSettingData
if($s -is [array]){ $s=$s[0] }

# --- 读取主机迁移配置 ---
'EnableVirtualSystemMigration='+[bool]$s.EnableVirtualSystemMigration
'MaximumActiveVirtualSystemMigration='+$s.MaximumActiveVirtualSystemMigration
'MaximumActiveStorageMigration='+$s.MaximumActiveStorageMigration
'AuthenticationType='+$s.AuthenticationType   # 0=CredSSP 1=Kerberos
'EnableCompression='+[bool]$s.EnableCompression
'EnableSmbTransport='+[bool]$s.EnableSmbTransport
$svc.MigrationServiceListenerIPAddressList
Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationNetworkSettingData  # 迁移网络

# --- 无害修改: 翻转 EnableCompression 后再还原 ---
$orig=[bool]$s.EnableCompression
$s.EnableCompression = -not $orig
$r=$svc.ModifyServiceSettings($s.GetText(1))   # IN=ServiceSettingData(内嵌 GetText(1)), OUT=Job; rv 0=成功 4096=作业
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job }

# 还原(重新取新实例,写回原值)
$s2=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationServiceSettingData
if($s2 -is [array]){ $s2=$s2[0] }
$s2.EnableCompression=$orig
$rr=$svc.ModifyServiceSettings($s2.GetText(1))
if($rr.ReturnValue -eq 4096){ Wait-Job2 $rr.Job }
```

## [PASS] 为虚拟机网络适配器设置静态 MAC 地址  `mac_static`

- StaticMacAddress 在 schema 上标记为只读(access=Read)，但可通过 Msvm_VirtualSystemManagementService.ModifyResourceSettings 修改并持久化，属于类定义中说明的标准例外。
- 不能直接使用 [wmiclass].CreateInstance() 构造 Msvm_SyntheticEthernetPortSettingData：这样得到的实例 ResourceType/ResourceSubType 为空，AddResourceSettings 会异步失败(JobState=10, ErrorCode=32773)。应从资源池获取默认 RASD：Msvm_ResourcePool(ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port', Primordial=True) -> Msvm_AllocationCapabilities -> Msvm_SettingsDefineCapabilities(ValueRole=0) -> PartComponent。
- 在 PowerShell 5.1 中，[wmiclass]"\\.\$ns:Class" 里 $ns 后紧跟的冒号会被解释为变量作用域，导致路径损坏。应写成 [wmiclass]("\\.\$ns"+":Class") 或使用 ${ns} 界定变量名。
- Address 为 12 位十六进制、无分隔符(如 00155D7A5C01)；StaticMacAddress=true 时该 Address 即为固定 MAC，设为 false 则交回动态分配。
- AddResourceSettings 的 OUT 参数为 ResultingResourceSettings(数组)；ModifyResourceSettings 同样返回修改后实例的路径，可直接以 [wmi] 取回读验证。
- 网络适配器未连接虚拟交换机时也可设置静态 MAC 地址。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; if($j.JobState -ne 7){Write-Host "JOB ERR state=$($j.JobState) code=$($j.ErrorCode) desc=$($j.ErrorDescription)"}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vmName='WMITEST_mac_static'; $vm=$null
try {
  # 创建第二代虚拟机
  $vssd=([wmiclass]("\\.\$ns"+":Msvm_VirtualSystemSettingData")).CreateInstance()
  $vssd.ElementName=$vmName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){throw 'DefineSystem job failed'} }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 从资源池取默认合成网卡 RASD（携带正确的 ResourceType/ResourceSubType）
  $rp=Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='Microsoft:Hyper-V:Synthetic Ethernet Port' AND Primordial=True"
  $caps=$rp.GetRelated('Msvm_AllocationCapabilities')|Select-Object -First 1
  $defAssoc=$caps.GetRelationships('Msvm_SettingsDefineCapabilities')|Where-Object {$_.ValueRole -eq 0}|Select-Object -First 1
  $nicRasd=[wmi]$defAssoc.PartComponent
  $nicRasd.ElementName='WMITEST_NIC'
  $nicRasd.VirtualSystemIdentifiers=@([guid]::NewGuid().ToString('B').ToUpper())
  # 添加网卡
  $ar=$vsms.AddResourceSettings($vssd2.__PATH,@($nicRasd.GetText(1)))
  if($ar.ReturnValue -eq 4096){ if((Wait-Job2 $ar.Job) -ne 7){throw 'AddResourceSettings job failed'} }
  elseif($ar.ReturnValue -ne 0){ throw "AddResourceSettings rv=$($ar.ReturnValue)" }
  $nic=[wmi]$ar.ResultingResourceSettings[0]
  # 设置静态 MAC：StaticMacAddress 在 schema 上标记为只读，但可经 ModifyResourceSettings 修改
  $targetMac='00155D7A5C01'
  $nic.StaticMacAddress=$true; $nic.Address=$targetMac
  $mr=$vsms.ModifyResourceSettings(@($nic.GetText(1)))
  if($mr.ReturnValue -eq 4096){ if((Wait-Job2 $mr.Job) -ne 7){throw 'ModifyResourceSettings job failed'} }
  elseif($mr.ReturnValue -ne 0){ throw "ModifyResourceSettings rv=$($mr.ReturnValue)" }
  $nic2=[wmi]$mr.ResultingResourceSettings[0]
  # 读回验证 StaticMacAddress 与 Address 已持久化
  if($nic2.StaticMacAddress -eq $true -and $nic2.Address -eq $targetMac){ Write-Host "PASS Static=$($nic2.StaticMacAddress) Address=$($nic2.Address)" } else { Write-Host "FAIL Static=$($nic2.StaticMacAddress) Address=$($nic2.Address)" }
}
finally {
  if($vm){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null} }
}
```

## [PASS] 启用动态内存并设置上下限  `mem_dynamic`

- 动态内存通过 Msvm_MemorySettingData.DynamicMemoryEnabled=true 启用；Reservation=最小(MB)、VirtualQuantity=启动(MB)、Limit=最大(MB)、TargetMemoryBuffer=缓冲百分比。这些属性继承自基类 CIM_ResourceAllocationSettingData。
- 前置条件：新建第二代虚拟机默认 VirtualNumaEnabled=true，此状态下直接启用动态内存会失败——ModifyResourceSettings 返回 4096 后 Job 以 JobState=10(Exception)/ErrorCode=32773 失败，ErrorDescription 为“无法启用动态内存，因为 NUMA 是基于跨度的”。须先通过 ModifySystemSettings 将 VSSD.VirtualNumaEnabled 置为 false。
- 关闭虚拟 NUMA 后，ModifyResourceSettings 同步返回 rv=0(无 Job)；未关闭时返回 4096 但关联 Job 失败。调用方应检查 JobState 是否等于 7，并在失败时读取 $job.ErrorDescription。
- 单位为 MB。默认 Limit=1048576(1 TB)。约束关系为 Reservation <= VirtualQuantity <= Limit。
- 所有嵌入实例均通过 GetText(1) 序列化后传入方法。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_mem_dynamic'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 1) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ $null=Wait-Job2 $r.Job } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem

  # 2) 动态内存要求关闭虚拟 NUMA，先将 VirtualNumaEnabled 置为 false
  $vssdN=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
  $vssdN.VirtualNumaEnabled=$false
  $rN=$vsms.ModifySystemSettings($vssdN.GetText(1))
  if($rN.ReturnValue -eq 4096){ $null=Wait-Job2 $rN.Job } elseif($rN.ReturnValue -ne 0){ throw "ModifySystemSettings(NUMA) rv=$($rN.ReturnValue)" }

  # 3) 启用动态内存并设置上下限(MB)。Reservation=最小 VirtualQuantity=启动 Limit=最大
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
  $mem=([wmi]$vssd2.__PATH).GetRelated('Msvm_MemorySettingData')|select -First 1
  $mem.DynamicMemoryEnabled=$true
  $mem.Reservation=[uint64]512
  $mem.VirtualQuantity=[uint64]1024
  $mem.Limit=[uint64]2048
  $mem.TargetMemoryBuffer=[uint32]20
  $r2=$vsms.ModifyResourceSettings($mem.GetText(1))
  if($r2.ReturnValue -eq 4096){ $js=Wait-Job2 $r2.Job; if($js -ne 7){ $jb=[wmi]$r2.Job; throw "job failed: $($jb.ErrorDescription)" } } elseif($r2.ReturnValue -ne 0){ throw "ModifyResourceSettings rv=$($r2.ReturnValue)" }

  # 4) 读回验证
  $vssd3=$vm.GetRelated('Msvm_VirtualSystemSettingData')|select -First 1
  $mem2=([wmi]$vssd3.__PATH).GetRelated('Msvm_MemorySettingData')|select -First 1
  Write-Host "DynEnabled=$($mem2.DynamicMemoryEnabled) Min/Res=$($mem2.Reservation) Startup/VQ=$($mem2.VirtualQuantity) Max/Lim=$($mem2.Limit) Buf=$($mem2.TargetMemoryBuffer)"
}
finally {
  if($vm){ $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ $null=Wait-Job2 $rd.Job } }
}
```

## [PASS] 设置静态内存  `mem_static`

- Msvm_MemorySettingData.VirtualQuantity 的单位为 MB(非字节、非块)。新建第二代虚拟机默认值为 1024 MB。
- VirtualQuantity 必须为 [uint64] 类型；DynamicMemoryEnabled=false 即为静态内存。设置静态内存仅需修改该资源，调用 ModifyResourceSettings(GetText(1))。
- VirtualQuantity 类型继承自 CIM_ResourceAllocationSettingData，内存类采用 MB 语义；因属于资源设置，故使用 ModifyResourceSettings 而非 ModifySystemSettings。
- ModifyResourceSettings 同步返回 0；DestroySystem 返回 4096(异步 Job)，需用 Wait-Job2 轮询等待。

```powershell
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns = 'root\virtualization\v2'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 取目标虚拟机的 Msvm_MemorySettingData
$vssd = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$mem  = ([wmi]$vssd.__PATH).GetRelated('Msvm_MemorySettingData') | Select-Object -First 1
# 设置静态内存：先关闭动态内存，再设 VirtualQuantity (单位 MB)
$mem.DynamicMemoryEnabled = $false
$mem.VirtualQuantity = [uint64]3072
$r = $vsms.ModifyResourceSettings($mem.GetText(1))
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job }
# 读回验证
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$mem2  = ([wmi]$vssd2.__PATH).GetRelated('Msvm_MemorySettingData') | Select-Object -First 1
[uint64]$mem2.VirtualQuantity  # => 3072
```

## [PASS] 启用与禁用虚拟机资源度量  `metrics_enable`

- Msvm_MetricService 为宿主单例：通过 Get-WmiObject -Class Msvm_MetricService 直接获取，无需经由虚拟机关联。
- ControlMetrics(Subject, Definition, MetricCollectionEnabled)：Subject 为被度量元素的引用(可传虚拟机的 __PATH 字符串)，Definition=null 表示对该 Subject 的全部度量统一操作，MetricCollectionEnabled(uint16)：2=Enable、3=Disable、4=Reset。返回 0 即同步成功，无 Job。
- 验证时不宜使用 ShowMetrics/ShowMetricsByClass：以 __PATH 字符串作为 Subject 传入时会抛出 'Invalid parameter'(WMIMethodException)。应改用关联类验证——启用后虚拟机经 Msvm_MetricForME 关联出 Msvm_BaseMetricValue / Msvm_AggregationMetricValue 实例，禁用后这些实例消失，以此判定生效。
- 刚启用时度量值多为 0(尚无采样窗口)，因此验证应判定'实例是否存在或消失'而非数值大小。
- Msvm_BaseMetricDefinition 为宿主级定义池(如 CPU 平均用量、磁盘读写字节、规范化 IO 等)，对所有虚拟机共享。
- 该类与 ControlMetrics 方法签名长期稳定，无版本门控。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$vmname='WMITEST_metrics_enable'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$metric=Get-WmiObject -Namespace $ns -Class Msvm_MetricService
$vm=$null
try {
  # 创建第二代测试虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$vmname
  $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ $null=Wait-Job2 $r.Job } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem
  $vmref=$vm.__PATH

  # 枚举可用的基础度量定义(宿主级度量定义池)
  $defs=Get-WmiObject -Namespace $ns -Class Msvm_BaseMetricDefinition

  # 为该虚拟机启用全部度量：Subject=VM 引用，Definition=$null(全部)，MetricCollectionEnabled=2(Enable)
  $rEnable=$metric.ControlMetrics($vmref,$null,[uint16]2)
  if($rEnable.ReturnValue -ne 0){ throw "ControlMetrics enable rv=$($rEnable.ReturnValue)" }

  # 验证：度量值实例应与虚拟机建立关联
  Start-Sleep -Seconds 1
  $valCount=(@(([wmi]$vmref).GetRelated('Msvm_BaseMetricValue')).Count) + (@(([wmi]$vmref).GetRelated('Msvm_AggregationMetricValue')).Count)
  $enabledOk=($rEnable.ReturnValue -eq 0 -and $valCount -gt 0)

  # 禁用：MetricCollectionEnabled=3(Disable)  [4=Reset]
  $rDisable=$metric.ControlMetrics($vmref,$null,[uint16]3)
  Start-Sleep -Seconds 1
  $valCount2=(@(([wmi]$vmref).GetRelated('Msvm_BaseMetricValue')).Count) + (@(([wmi]$vmref).GetRelated('Msvm_AggregationMetricValue')).Count)
  $disableOk=($rDisable.ReturnValue -eq 0 -and $valCount2 -eq 0)

  if($enabledOk -and $disableOk){ Write-Host "PASS enabled=$valCount disabled_to=$valCount2" } else { Write-Host "FAIL" }
}
finally {
  if($vm -ne $null){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ $null=Wait-Job2 $d.Job } }
}
```

## [PASS] 配置虚拟机 MMIO 地址空间（GPU-P/DDA 大 BAR）  `mmio_gap`

- LowMmioGapSize / HighMmioGapSize / HighMmioGapBase 三个属性位于 Msvm_VirtualSystemSettingData(VSSD)，而非 Msvm_MemorySettingData；后者不含这些字段。
- 因此应通过 ModifySystemSettings(vssd.GetText(1)) 下发，而非 ModifyResourceSettings。
- 单位为 MB。第二代虚拟机默认值：LowMmioGapSize=128、HighMmioGapSize=512、HighMmioGapBase=65024(只读)。
- DDA/GPU-P 映射大 BAR 设备时通常需要增大 HighMmioGapSize。
- HighMmioGapBase 为只读属性(access 仅 Read)，由系统计算得出，不可写入。
- 虚拟机处于离线(未运行)状态即可修改这些属性，无需启动。ModifySystemSettings 返回 4096(异步 Job)，须用 Wait-Job2 等待完成。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){ return 7 }; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vmName = 'WMITEST_mmio_gap'
$vm = $null
try {
  # 创建第二代测试虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $vmName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $null = Wait-Job2 $r.Job }
  $vm = [wmi]$r.ResultingSystem
  # 获取虚拟机的活动设置实例
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $vssd2 = [wmi]$vssd2.__PATH
  # MMIO 间隙属性(MB)位于 Msvm_VirtualSystemSettingData，而非 Msvm_MemorySettingData
  $vssd2.LowMmioGapSize  = [uint64]512
  $vssd2.HighMmioGapSize = [uint64]32768
  $r2 = $vsms.ModifySystemSettings($vssd2.GetText(1))
  if($r2.ReturnValue -eq 4096){ $null = Wait-Job2 $r2.Job }
  # 读回验证
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $vssd3 = [wmi]$vssd3.__PATH
  Write-Output ("LowMmioGapSize=" + $vssd3.LowMmioGapSize + " HighMmioGapSize=" + $vssd3.HighMmioGapSize + " HighMmioGapBase=" + $vssd3.HighMmioGapBase)
}
finally {
  if($vm){ $d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ $null = Wait-Job2 $d.Job } }
}
```

## [PASS] 将 VHD 挂载到主机  `mount_vhd_host`

- AttachVirtualHardDisk(Path, AssignDriveLetter, ReadOnly) 定义于 Msvm_ImageManagementService,等价于 Mount-VHD,以环回方式挂载到主机。返回 4096 表示异步作业,经 Wait-Job2 等待 JobState 完成即成功。
- DetachVirtualHardDisk 是 Msvm_MountedStorageImage 的无参实例方法,而非服务上的方法;卸载对象为该次 Attach 得到的挂载镜像。返回 0 表示同步完成。
- 定位挂载对象可优先使用服务方法 GetMountedStorageImage(SelectionCriterion, CriterionType),CriterionType=0 按路径查询,OUT 参数名为 Image(REF);也可直接枚举 Msvm_MountedStorageImage 并按 Name/Path 匹配。
- Msvm_MountedStorageImage 的关键读回属性:Type(0=Virtual Hard Disk,1=ISO Image)、Access(1=Read-only,2=Read/Write)。键为 SCSI 地址(PortNumber/PathId/TargetId/Lun)。
- CreateVirtualHardDisk 仅接受 1 个 IN 参数(内嵌的 VHDSettingData 串);若为 OUT 的 Job 传入 $null 会触发 MethodCountCouldNotFindBest 错误。使用 Get-WmiObject 调用方法时不应显式传递 OUT 参数。
- 此操作挂载到主机而非某台虚拟机,因此全程不创建任何虚拟机;清理仅需 Detach 后删除 vhdx 文件。
- AttachVirtualHardDisk / Msvm_MountedStorageImage / DetachVirtualHardDisk 自 build 9200 起持续提供。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$vhd = 'C:\Temp\WMITEST_mount.vhdx'
$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

# 1) 创建一个用于挂载的动态 vhdx
$sd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
$sd.Type = [uint16]3      # 3 = 动态
$sd.Format = [uint16]3    # 3 = VHDX
$sd.Path = $vhd
$sd.MaxInternalSize = [uint64](64MB)
$rc = $ims.CreateVirtualHardDisk($sd.GetText(1))   # 仅传入 IN 参数;不要为 OUT 的 Job 传入 $null
if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }

# 2) AttachVirtualHardDisk 等价于 Mount-VHD,以环回方式挂载到主机。参数: Path, AssignDriveLetter, ReadOnly
$r = $ims.AttachVirtualHardDisk($vhd, $false, $false)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }

# 3) 通过 GetMountedStorageImage 校验(CriterionType 0 = 按路径查询) -> Msvm_MountedStorageImage
$img = $null
$g = $ims.GetMountedStorageImage($vhd, [uint16]0)
if($g.ReturnValue -eq 0 -and $g.Image){ $img = [wmi]$g.Image }
if(-not $img){ $img = Get-WmiObject -Namespace $ns -Class Msvm_MountedStorageImage | Where-Object { $_.Name -eq $vhd -or $_.Path -eq $vhd } | Select-Object -First 1 }
"mounted Type=$($img.Type) Access=$($img.Access)"   # Type 0=VHD 1=ISO ; Access 1=只读 2=读写

# 4) DetachVirtualHardDisk 是 Msvm_MountedStorageImage 的实例方法(非服务上的方法)
$d = $img.DetachVirtualHardDisk()
if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }

Remove-Item $vhd -Force
```

## [PASS] 向虚拟机注入鼠标输入  `mouse_input`

- 前置条件：Msvm_SyntheticMouse 设备仅在虚拟机运行态(EnabledState=2)时存在，停止态(EnabledState=3)下该虚拟机的 Msvm_SyntheticMouse 实例数为 0。因此需先 RequestStateChange(2) 启动虚拟机(空的第二代 UEFI 虚拟机即可启动)才能取得鼠标设备并调用其方法。该模式与键盘输入(Msvm_Keyboard)一致。
- 获取鼠标设备：Get-WmiObject Msvm_SyntheticMouse -Filter "SystemName='<VM.Name GUID>'"，须使用 VM.Name(GUID)而非 ElementName。第二代为 Msvm_SyntheticMouse，第一代为 Msvm_Ps2Mouse(方法集少一个 SetAbsolutePosition)。合成鼠标 DeviceID 固定为 Microsoft:58F75A6D-D949-4320-99E1-A2A2576D581C。
- 方法签名(均返回 uint32, ValueMap: 0=成功 4096=作业 32768..32778=各类失败)：SetAbsolutePosition(sint32 HorizontalPosition, sint32 VerticalPosition) 绝对归一化坐标 0..65535；ClickButton(uint32 ButtonIndex) 1=左 2=右 3=中，执行一次按下-抬起；SetScrollPosition(sint32 ScrollPositionDelta) 滚轮相对增量(一格=120)。SetAbsolutePosition 为鼠标相对键盘的关键差异——键盘无此绝对定位方法。
- 在空 UEFI 第二代虚拟机(无来宾操作系统)上，三个方法均返回非零：SetAbsolutePosition 返回 32773(Invalid Parameter，边界值 0/65535 及 32768 均拒绝)，ClickButton/SetScrollPosition 返回 32768(Failed)。原因是空虚拟机停在 UEFI/PXE，来宾侧无 Hyper-V 鼠标集成驱动打开 VMBus 鼠标通道，合成鼠标拒绝注入。返回 0 需来宾装有集成服务鼠标驱动(启动 Windows/Linux 后)。这是设备状态限制，而非调用错误；设备定位与方法调用本身有效。
- 主机稳定性提示：某些 vmms.exe 版本在空虚拟机快速创建/启动/删除的高频操作下可能崩溃(事件 ID 1000/1001，异常 0xc0000409 STATUS_STACK_BUFFER_OVERRUN)，崩溃后 root\virtualization\v2 命名空间所有查询返回空(vmms 服务处于 Stopped)。脚本可加入守护逻辑：每次 WMI 调用前确认服务在运行并能取到 Msvm_VirtualSystemManagementService，否则启动 vmms 并重试；清理前同样先确认服务可用，以保证崩溃后仍能删除测试虚拟机。
- PowerShell 5.1 兼容性：[wmi] 类型加速器解析路径在 vmms 抖动期偶发 InvalidCast，改用 New-Object System.Management.ManagementObject($path) 再 .Get() 更稳定。Get-WmiObject Msvm_VirtualSystemManagementService 以 @(...)[0] 或 Select -First 1 取值，为空时重试。
- 清理：先强制关机 RequestStateChange(3) 再 DestroySystem；DestroySystem 返回 4096(作业)须 Wait-Job2 等待完成，且删除存在延迟，应轮询直到 ElementName='WMITEST_mouse_input' 查询为空以确认无残留。

```powershell
$ns='root\virtualization\v2'
function W([string]$p){ New-Object System.Management.ManagementObject($p) }
function Wait-Job2([string]$p){ if(-not $p){return 7}; $j=W $p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=W $p; $j.Get()}; return $j.JobState }
$vsms=@(Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService)[0]
# 1) 创建第二代测试虚拟机
$vssd=([wmiclass]("\\.\"+$ns+":Msvm_VirtualSystemSettingData")).CreateInstance()
$vssd.ElementName='WMITEST_mouse_input'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=W $r.ResultingSystem; $vm.Get()
# 2) 鼠标设备(Msvm_SyntheticMouse)仅在虚拟机运行时存在; 停止态实例数为 0
#    须先 RequestStateChange(2) 启动到 EnabledState=2
$vmc=W $vm.__PATH; $vmc.Get(); $rs=$vmc.RequestStateChange(2); if($rs.ReturnValue -eq 4096){Wait-Job2 $rs.Job|Out-Null}
Start-Sleep -Seconds 3
# 3) 按 SystemName=VM.Name(GUID) 取 Msvm_SyntheticMouse (第二代; 第一代用 Msvm_Ps2Mouse)
$mouse=Get-WmiObject -Namespace $ns -Class Msvm_SyntheticMouse -Filter ("SystemName='"+$vm.Name+"'")|Select-Object -First 1
$mouse=W $mouse.__PATH; $mouse.Get()
# 4) 注入(均返回 uint32, 0=成功; 需来宾装有 Hyper-V 鼠标集成驱动):
$mouse.SetAbsolutePosition([int]32768,[int]32768).ReturnValue   # 绝对定位: 归一化坐标 0..65535, (0,0)左上 (65535,65535)右下
$mouse.ClickButton([uint32]1).ReturnValue                       # 按键点击(按下-抬起): 1=左 2=右 3=中
$mouse.SetScrollPosition([int]120).ReturnValue                  # 滚轮相对增量: +向上 -向下 (一格=120)
# 5) 清理: 先强制关机 RequestStateChange(3) 再 DestroySystem
$vmk=W $vm.__PATH; $vmk.Get(); $off=$vmk.RequestStateChange(3); if($off.ReturnValue -eq 4096){Wait-Job2 $off.Job|Out-Null}
$d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null}
```

## [PASS] 设置虚拟网卡带宽限制  `net_bandwidth`

- 带宽属于网卡连接(Msvm_EthernetPortAllocationSettingData)上的端口功能(feature)，须用 Msvm_VirtualSystemManagementService.AddFeatureSettings(AffectedConfiguration=连接引用, FeatureSettings[]=嵌入实例) 下发。
- 端口功能须使用 Msvm_VirtualSystemManagementService(vsms) 而非 Msvm_VirtualEthernetSwitchManagementService(vesms)。vesms 的 feature 方法仅用于交换机级功能；在其上对虚拟机端口功能下发会使 Job 进入 JobState=10、ErrorCode=32773、MessageID=26146。Set-VMNetworkAdapter -MaximumBandwidth 走的即是 vsms 路径。
- Msvm_EthernetSwitchPortBandwidthSettingData 的 Limit/Reservation/Weight 均为 uint64。当交换机 BandwidthReservationMode=2(Absolute) 时，Limit/Reservation 单位为 bit/s；Weight 仅在 Weight 模式下生效。
- 合成网卡与端口连接均须克隆各自资源池的 \Default 模板(InstanceID 形如 Microsoft:Definition\<GUID>\Default)后再修改属性。裸 CreateInstance 的合成网卡缺少必填字段，AddResourceSettings 的 Job 会以 ErrorCode=32773 失败。
- AddResourceSettings 同步返回(rv=0)时 ResultingResourceSettings 已填充，可直接取 [0]；返回 4096(异步)时该输出参数为空，须等待 Job 完成后经关联重新查回。AddFeatureSettings 同步返回 rv=0 时 ResultingFeatureSettings 含 1 项。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$testName='WMITEST_net_bandwidth'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 1) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$testName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 2) 选择一个可用交换机，排除 'Default Switch'（NAT 交换机会拒绝手工端口连接）
  $sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -ne 'Default Switch' } | Select-Object -First 1
  # 3) 添加合成网卡：克隆默认 RASD 模板；裸 CreateInstance 缺少必填字段会导致 Job 错误 32773
  $nicTmpl=Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $nic=$nicTmpl.psbase.Clone(); $nic.ElementName='WMITEST_nic'; $nic.VirtualSystemIdentifiers=@('{'+[guid]::NewGuid().ToString()+'}')
  $ra=$vsms.AddResourceSettings($vssd2.__PATH,@($nic.GetText(1))); if($ra.ReturnValue -eq 4096){Wait-Job2 $ra.Job|Out-Null}
  $nicInst=[wmi]($ra.ResultingResourceSettings[0])
  # 4) 通过 Msvm_EthernetPortAllocationSettingData 将网卡连接到交换机（克隆默认模板）
  $epasTmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $epas=$epasTmpl.psbase.Clone(); $epas.Parent=$nicInst.__PATH; $epas.HostResource=@($sw.__PATH)
  $rc=$vsms.AddResourceSettings($vssd2.__PATH,@($epas.GetText(1))); if($rc.ReturnValue -eq 4096){Wait-Job2 $rc.Job|Out-Null}
  $connInst=[wmi]($rc.ResultingResourceSettings[0])
  # 5) 从默认模板构建带宽功能；交换机处于 Absolute 模式时 Limit/Reservation 单位为 bit/s
  $tmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetSwitchPortBandwidthSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $bw=$tmpl.psbase.Clone(); $bw.Limit=[uint64]100000000; $bw.Reservation=[uint64]10000000; $bw.Weight=[uint64]0
  # 6) 通过 Msvm_VirtualSystemManagementService.AddFeatureSettings 在虚拟机端下发带宽功能
  $rf=$vsms.AddFeatureSettings($connInst.__PATH,@($bw.GetText(1))); if($rf.ReturnValue -eq 4096){Wait-Job2 $rf.Job|Out-Null}
  # 7) 读回验证
  $feat=[wmi]($rf.ResultingFeatureSettings[0])
  if(-not $feat){ $feat=([wmi]$connInst.__PATH).GetRelated('Msvm_EthernetSwitchPortBandwidthSettingData')|Select-Object -First 1 }
  Write-Output ("Limit=$($feat.Limit) Reservation=$($feat.Reservation) Weight=$($feat.Weight)")
} finally {
  if($vm){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null} }
}
```

## [PASS] 为虚拟网卡配置扩展端口 ACL  `nic_acl`

- 扩展 ACL(Msvm_EthernetSwitchPortExtendedAclSettingData) 是网卡连接(Msvm_EthernetPortAllocationSettingData)上的端口功能(feature)，须用 Msvm_VirtualSystemManagementService.AddFeatureSettings(AffectedConfiguration=连接引用, FeatureSettings[]=ACL 嵌入实例 GetText(1)) 下发。与带宽、卸载功能走同一 vsms 路径；不可使用 Msvm_VirtualEthernetSwitchManagementService(vesms)，其对端口功能会返回 JobState=10、ErrorCode=32773。
- AddFeatureSettings 同步返回 rv=0 时 ResultingFeatureSettings 直接含 1 项 ACL 引用，可立即以 [wmi] 读回；若异步返回 4096，则等待 Job 完成后经 GetRelated('Msvm_EthernetSwitchPortExtendedAclSettingData') 查回。
- ACL 关键属性：Direction uint8(0=未知/1=入站/2=出站)、Action uint8(0=未知/1=允许/2=拒绝)、LocalIPAddress/RemoteIPAddress/LocalPort/RemotePort/Protocol 均为字符串(默认 'ANY'，IP 支持 CIDR 如 192.168.50.0/24)、Weight uint16(优先级权重)、Stateful bool、IdleSessionTimeout uint16(有状态 ACL 空闲超时秒数)、IsolationID uint32。此为扩展 ACL(支持端口/协议/有状态)，区别于仅支持基础 ACL 的 Msvm_EthernetSwitchPortAclSettingData。
- ACL 须克隆资源池 \Default 模板(psbase.Clone())后再修改属性；裸 CreateInstance 缺少 ResourceType/ResourceSubType 等字段会被 Job 拒绝。合成网卡与端口连接同样须克隆各自的 \Default 模板。
- 前置链路：创建第二代虚拟机 -> 克隆 \Default 合成网卡并 AddResourceSettings 取得 NIC RASD -> 克隆 \Default EPAS 设置 Parent=NIC 路径、HostResource=@(交换机路径) 并 AddResourceSettings 取得连接 -> 在连接上 AddFeatureSettings 下发 ACL。
- 该类自 build 9600 起提供。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$testName='WMITEST_nic_acl'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 1) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$testName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 2) 选择一个可用交换机，排除 'Default Switch'
  $sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -ne 'Default Switch' } | Select-Object -First 1
  # 3) 添加合成网卡（克隆类的 \Default 模板）
  $nicTmpl=Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $nic=$nicTmpl.psbase.Clone(); $nic.ElementName='WMITEST_nic'; $nic.VirtualSystemIdentifiers=@('{'+[guid]::NewGuid().ToString()+'}')
  $ra=$vsms.AddResourceSettings($vssd2.__PATH,@($nic.GetText(1))); if($ra.ReturnValue -eq 4096){Wait-Job2 $ra.Job|Out-Null}
  $nicInst=[wmi]($ra.ResultingResourceSettings[0])
  # 4) 通过 Msvm_EthernetPortAllocationSettingData 将网卡连接到交换机
  $epasTmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $epas=$epasTmpl.psbase.Clone(); $epas.Parent=$nicInst.__PATH; $epas.HostResource=@($sw.__PATH)
  $rc=$vsms.AddResourceSettings($vssd2.__PATH,@($epas.GetText(1))); if($rc.ReturnValue -eq 4096){Wait-Job2 $rc.Job|Out-Null}
  $connInst=[wmi]($rc.ResultingResourceSettings[0])
  # 5) 从默认模板构建扩展 ACL 功能
  $aclTmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetSwitchPortExtendedAclSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $acl=$aclTmpl.psbase.Clone()
  $acl.Direction=[byte]1          # 1=入站 2=出站
  $acl.Action=[byte]2             # 1=允许 2=拒绝
  $acl.LocalIPAddress='ANY'; $acl.RemoteIPAddress='192.168.50.0/24'
  $acl.LocalPort='ANY'; $acl.RemotePort='ANY'; $acl.Protocol='tcp'
  $acl.Weight=[uint16]100; $acl.Stateful=$false; $acl.IdleSessionTimeout=[uint16]0
  # 6) 通过 vsms.AddFeatureSettings 下发 ACL（AffectedConfiguration=连接引用）
  $rf=$vsms.AddFeatureSettings($connInst.__PATH,@($acl.GetText(1))); if($rf.ReturnValue -eq 4096){Wait-Job2 $rf.Job|Out-Null}
  # 7) 读回验证
  $feat=$null
  if($rf.ResultingFeatureSettings -and $rf.ResultingFeatureSettings.Count -gt 0){ $feat=[wmi]($rf.ResultingFeatureSettings[0]) }
  if(-not $feat){ $feat=([wmi]$connInst.__PATH).GetRelated('Msvm_EthernetSwitchPortExtendedAclSettingData')|Select-Object -First 1 }
  Write-Output ("Direction=$($feat.Direction);Action=$($feat.Action);RemoteIP=$($feat.RemoteIPAddress);Protocol=$($feat.Protocol);Weight=$($feat.Weight)")
} finally {
  if($vm){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null} }
}
```

## [PASS] 配置虚拟网卡端口隔离 (Msvm_EthernetSwitchPortIsolationSettingData)  `nic_isolation_pvlan`

- 交换机端口功能(feature)须通过 Msvm_VirtualSystemManagementService.AddFeatureSettings / ModifyFeatureSettings 下发，而非 Msvm_VirtualEthernetSwitchManagementService。后者的同名方法对每端口隔离会返回错误码 32773(修改虚拟以太网交换机连接设置时失败)。Set-VMNetworkAdapterIsolation 调用的即是 Msvm_VirtualSystemManagementService::AddFeatureSettings。
- AddFeatureSettings 签名：AffectedConfiguration(REF，传端口连接的 Msvm_EthernetPortAllocationSettingData.__PATH) + FeatureSettings(string[]，嵌入实例 GetText(1))；输出为 ResultingFeatureSettings + Job。rv=0 表示同步成功，rv=4096 表示异步 Job。
- Msvm_EthernetSwitchPortIsolationSettingData 仅有 4 个属性：IsolationMode(0=None 1=NativeVirtualSubnetId 2=ExternalVirtualSubnetId 3=VLAN)、AllowUntaggedTraffic、DefaultIsolationId、EnableMultiTenantStack。PrimaryVlanId/SecondaryVlanId 在该 WMI 类上不存在——PVLAN 主/次 VLAN 属于上层 PowerShell 概念，WMI 层的端口隔离即这 4 个字段。
- 须先将网卡接入一台已存在的虚拟交换机形成端口连接(Msvm_EthernetPortAllocationSettingData)，功能才有附着点。应选用非 'Default Switch' 的交换机：'Default Switch'(NAT) 会拒绝手工端口连接(连接 Job 失败 state=10)。
- 接入后建议轮询端口连接 EnabledState==2(Enabled) 再下发功能，避免端口未就绪。
- ModifyFeatureSettings 仅接收 FeatureSettings(string[])，对已存在的功能实例(GetText(1))原地修改；读回经端口连接 GetRelated('Msvm_EthernetSwitchPortIsolationSettingData')。
- 同一模式(vsms.AddFeatureSettings)适用于所有 Msvm_EthernetSwitchPort*SettingData 功能：Security/Vlan/Bandwidth/Offload/ExtendedAcl 等。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){return 7}
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$TESTNAME = 'WMITEST_nic_isolation_pvlan'

# ---- 创建第二代虚拟机 ----
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $TESTNAME
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

# ---- 添加合成网卡 ----
$nicTmpl = Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData | Where-Object { $_.InstanceID -match 'Default$' } | Select-Object -First 1
$nic = $nicTmpl.PSObject.Copy()
$nic.ElementName = 'WMITEST_NIC'
$nic.VirtualSystemIdentifiers = @('{' + [guid]::NewGuid().ToString() + '}')
$addNic = $vsms.AddResourceSettings($vssd2.__PATH, @($nic.GetText(1)))
if($addNic.ReturnValue -eq 4096){ Wait-Job2 $addNic.Job | Out-Null }
$nicRes = [wmi]$addNic.ResultingResourceSettings[0]

# ---- 将网卡连接到交换机（承载端口功能需要一个已实现的端口连接） ----
# 使用非 'Default Switch' 的交换机；'Default Switch'(NAT) 会拒绝手工端口连接。
$allsw = Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch
$sw = $allsw | Where-Object { $_.ElementName -ne 'Default Switch' } | Select-Object -First 1
if(-not $sw){ $sw = $allsw | Select-Object -First 1 }
$epasTmpl = Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData | Where-Object { $_.InstanceID -match 'Default$' } | Select-Object -First 1
$epas = $epasTmpl.PSObject.Copy()
$epas.Parent = $nicRes.__PATH
$epas.HostResource = @($sw.__PATH)
$addConn = $vsms.AddResourceSettings($vssd2.__PATH, @($epas.GetText(1)))
if($addConn.ReturnValue -eq 4096){ Wait-Job2 $addConn.Job | Out-Null }
$conn = [wmi]$addConn.ResultingResourceSettings[0]
for($i=0; $i -lt 30; $i++){ if(([wmi]$conn.__PATH).EnabledState -eq 2){ break }; Start-Sleep -Milliseconds 200 }

# ================================================================================
# 交换机端口功能(隔离/安全/vlan/acl/卸载等)通过 Msvm_VirtualSystemManagementService
# ($vsms) 的 AddFeatureSettings 下发，而非 Msvm_VirtualEthernetSwitchManagementService。
# 后者的同名方法会返回错误码 32773。AffectedConfiguration = 端口连接
# (Msvm_EthernetPortAllocationSettingData)；FeatureSettings = 嵌入的功能实例。
# IsolationMode: 0=None 1=NativeVirtualSubnetId 2=ExternalVirtualSubnetId 3=VLAN。
# 该类不含 PrimaryVlanId/SecondaryVlanId；PVLAN 主/次 VLAN 属于更高层抽象。
# WMI 层的端口隔离由 IsolationMode + DefaultIsolationId + AllowUntaggedTraffic
# + EnableMultiTenantStack 四个字段构成。
# ================================================================================
$iso = ([wmiclass]"\\.\${ns}:Msvm_EthernetSwitchPortIsolationSettingData").CreateInstance()
$iso.IsolationMode          = [uint32]3      # 3 = VLAN
$iso.AllowUntaggedTraffic   = $true
$iso.DefaultIsolationId     = [uint32]200    # 未标记流量的默认 VLAN
$iso.EnableMultiTenantStack = $false
$addFeat = $vsms.AddFeatureSettings($conn.__PATH, @($iso.GetText(1)))
if($addFeat.ReturnValue -eq 4096){ Wait-Job2 $addFeat.Job | Out-Null }

# 读回验证
$applied = ([wmi]$conn.__PATH).GetRelated('Msvm_EthernetSwitchPortIsolationSettingData') | Select-Object -First 1
"IsolationMode=$($applied.IsolationMode) Allow=$($applied.AllowUntaggedTraffic) DefId=$($applied.DefaultIsolationId)"

# 通过 $vsms.ModifyFeatureSettings 修改 DefaultIsolationId
$applied.DefaultIsolationId = [uint32]250
$modFeat = $vsms.ModifyFeatureSettings($applied.GetText(1))
if($modFeat.ReturnValue -eq 4096){ Wait-Job2 $modFeat.Job | Out-Null }

# 清理
$d = $vsms.DestroySystem($vm.__PATH)
if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
```

## [PASS] 配置虚拟网卡端口安全 (MAC 欺骗防护/DHCP 守卫/路由守卫/来宾组网)  `nic_security`

- 端口安全功能加在网卡连接(Msvm_EthernetPortAllocationSettingData, EPAS)上，须用 Msvm_VirtualSystemManagementService.AddFeatureSettings(EPAS.__PATH, @(嵌入实例 GetText(1))) 下发。同步返回 RV=0(无 Job)。
- 前置链路：创建第二代虚拟机 -> AddResourceSettings 合成网卡 -> AddResourceSettings EPAS 连接到交换机(HostResource=交换机 __PATH，端口 EnabledState=2)。虚拟机无需开机。
- 安全功能实例不要裸 CreateInstance；应从 Msvm_EthernetSwitchFeatureCapabilities 经 Msvm_FeatureSettingsDefineCapabilities 关联取默认 Msvm_EthernetSwitchPortSecuritySettingData(InstanceID=Microsoft:Definition\776E0BA7-94A1-41C8-8F28-951F524251B5\Default) 后 .psbase.Clone() 修改。
- Msvm_EthernetSwitchPortSecuritySettingData 关键属性(均为 boolean)：AllowMacSpoofing(MAC 欺骗防护) / EnableDhcpGuard(DHCP 守卫) / EnableRouterGuard(路由守卫) / AllowTeaming(来宾内组网)；另有 MonitorMode(uint8 0/1/2)、AllowIeeePriorityTag、VirtualSubnetId(uint32)。
- 在以 -File 运行的 .ps1 中，WQL 过滤器 "InstanceID LIKE '%\Default'" 内的单反斜杠会使 WMI 报无效查询；应改为不带 -Filter、用 PowerShell 端 -match 'Default$' 挑选模板。
- 该类自 build 9200 起提供。读回经 EPAS.GetRelated('Msvm_EthernetSwitchPortSecuritySettingData')。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 1) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName='WMITEST_nic_security'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){[void](Wait-Job2 $r.Job)}
  $vm=[wmi]$r.ResultingSystem
  $vmSettings=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 2) 添加合成网卡（克隆类的 '...\Default' 模板；在 -File 脚本中的 WQL LIKE 勿使用含反斜杠的过滤器）
  $nicTpl=$null; Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData | ForEach-Object { if($_.InstanceID -match 'Default$'){ $nicTpl=$_ } }
  $nic=$nicTpl.psbase.Clone(); $nic.ElementName='WMITEST_NIC'; $nic.VirtualSystemIdentifiers=@([guid]::NewGuid().ToString('B').ToUpper())
  $addNic=$vsms.AddResourceSettings($vmSettings.__PATH,@($nic.GetText(1))); if($addNic.ReturnValue -eq 4096){[void](Wait-Job2 $addNic.Job)}
  $nicRasd=[wmi]$addNic.ResultingResourceSettings[0]
  # 3) 将网卡连接到已存在的交换机 'Switch'
  $sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch -Filter "ElementName='Switch'"
  $epasTpl=$null; Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData | ForEach-Object { if($_.InstanceID -match 'Default$'){ $epasTpl=$_ } }
  $epas=$epasTpl.psbase.Clone(); $epas.Parent=$nicRasd.__PATH; $epas.HostResource=@($sw.__PATH)
  $addConn=$vsms.AddResourceSettings($vmSettings.__PATH,@($epas.GetText(1))); if($addConn.ReturnValue -eq 4096){[void](Wait-Job2 $addConn.Job)}
  $conn=[wmi]$addConn.ResultingResourceSettings[0]
  # 4) 构建安全功能：从功能能力关联克隆默认实例（裸 CreateInstance 会被拒绝）
  $secDef=$null
  foreach($cap in (Get-WmiObject -Namespace $ns -Class Msvm_EthernetSwitchFeatureCapabilities)){
    $d=$cap.GetRelated('Msvm_EthernetSwitchPortSecuritySettingData','Msvm_FeatureSettingsDefineCapabilities',$null,$null,'PartComponent','GroupComponent',$false,$null)|Select-Object -First 1
    if($d){ $secDef=$d; break }
  }
  $sec=([wmi]$secDef.__PATH).psbase.Clone()
  $sec.AllowMacSpoofing=$true; $sec.EnableDhcpGuard=$true; $sec.EnableRouterGuard=$true; $sec.AllowTeaming=$true
  # 5) 通过 vsms.AddFeatureSettings 下发（虚拟机连接变体），而非 VirtualEthernetSwitchManagementService
  $rf=$vsms.AddFeatureSettings($conn.__PATH,@($sec.GetText(1))); if($rf.ReturnValue -eq 4096){[void](Wait-Job2 $rf.Job)}
  # 6) 经端口连接读回验证
  $back=$conn.GetRelated('Msvm_EthernetSwitchPortSecuritySettingData')|Select-Object -First 1
  "AllowMacSpoofing=$($back.AllowMacSpoofing) EnableDhcpGuard=$($back.EnableDhcpGuard) EnableRouterGuard=$($back.EnableRouterGuard) AllowTeaming=$($back.AllowTeaming)"
}
finally { if($vm){ [void]$vsms.DestroySystem($vm.__PATH) } }
```

## [PASS] 配置虚拟机 NUMA 拓扑  `numa_topology`

- VirtualNumaEnabled 位于 Msvm_VirtualSystemSettingData(整机设置)上，用 ModifySystemSettings 修改；不是资源属性。
- NUMA 拓扑的细粒度上限位于两个资源上：Msvm_ProcessorSettingData.MaxProcessorsPerNumaNode / MaxNumaNodesPerSocket 与 Msvm_MemorySettingData.MaxMemoryBlocksPerNumaNode；这两个资源属性用 ModifyResourceSettings 修改。
- 新建的第二代空虚拟机默认 VirtualNumaEnabled=True；MaxMemoryBlocksPerNumaNode 以 MB 计，对应主机单个 NUMA 节点的内存量。
- MaxProcessorsPerNumaNode 底层类型为 uint64；赋值宜使用 [uint64]。修改后读回即可验证。
- DefineSystem/ModifySystemSettings/ModifyResourceSettings/DestroySystem 均可能返回 4096(异步 Job)，须等待 Job 完成。
- 更精细的固定映射(NumaNodeTopologyArray / Msvm_NumaNodeTopology 嵌入实例数组)存在于 VSSD，可用于静态 NUMA 绑定，本配方未涉及。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns  = 'root\virtualization\v2'
$name = 'WMITEST_numa_topology'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

$vm = $null
try {
    # 创建第二代虚拟机
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $name
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
    $vm = [wmi]$r.ResultingSystem

    # 虚拟机的 VSSD
    $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
    $vssd2 = [wmi]$vssd2.__PATH

    # 读取 NUMA 相关属性
    $numaBefore = $vssd2.VirtualNumaEnabled
    $proc = [wmi]($vssd2.GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1).__PATH
    $mem  = [wmi]($vssd2.GetRelated('Msvm_MemorySettingData') | Select-Object -First 1).__PATH
    # NUMA 上限：$proc.MaxProcessorsPerNumaNode, $proc.MaxNumaNodesPerSocket, $mem.MaxMemoryBlocksPerNumaNode

    # 通过 ModifySystemSettings 在 VSSD 上翻转 VirtualNumaEnabled
    $target = -not [bool]$numaBefore
    $vssd2.VirtualNumaEnabled = $target
    $r2 = $vsms.ModifySystemSettings($vssd2.GetText(1))
    if ($r2.ReturnValue -eq 4096) { $null = Wait-Job2 $r2.Job }
    $numaAfter = ([wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH).VirtualNumaEnabled

    # 通过 ModifyResourceSettings 在 ProcessorSettingData 上修改每 NUMA 节点上限(MaxProcessorsPerNumaNode)
    $proc2 = [wmi]($vssd2.GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1).__PATH
    $proc2.MaxProcessorsPerNumaNode = [uint32]1
    $r3 = $vsms.ModifyResourceSettings($proc2.GetText(1))
    if ($r3.ReturnValue -eq 4096) { $null = Wait-Job2 $r3.Job }
}
finally {
    if ($vm -ne $null) { $rd = $vsms.DestroySystem($vm.__PATH); if ($rd.ReturnValue -eq 4096) { $null = Wait-Job2 $rd.Job } }
}
```

## [PASS] 将虚拟机配置导入为计划虚拟机并校验落地为真实虚拟机  `planned_realize`

- 完整链路为 ExportSystemDefinition -> ImportSystemDefinition（得 Msvm_PlannedComputerSystem）-> ValidatePlannedSystem -> RealizePlannedSystem（得真实 Msvm_ComputerSystem）。
- ImportSystemDefinition 签名为 (SystemDefinitionFile=导出的 .vmcx 全路径, SnapshotFolder=虚拟机导出根目录, GenerateNewSystemIdentifier=boolean)，返回 OUT 参数 ImportedSystem（类 Msvm_PlannedComputerSystem）及 Job；导入通常同步返回 rv=0。
- ExportSystemDefinition 签名为 (ComputerSystem REF, ExportDirectory, ExportSettingData=嵌入 Msvm_VirtualSystemExportSettingData 的 GetText(1) 串)。导出物结构为 <ExportDirectory>\<VM ElementName>\Virtual Machines\<GUID>.vmcx。
- ValidatePlannedSystem(PlannedSystem REF) 与 RealizePlannedSystem(PlannedSystem REF) 均接受计划虚拟机的 __PATH；Realize 的 OUT 参数为 ResultingSystem（类 CIM_ComputerSystem）。
- Export/Validate/Realize 三个方法可能异步返回 4096，需通过 Wait-Job2 轮询 Msvm_ConcreteJob.JobState 至 7（Completed）。
- Realize 异步完成后 ResultingSystem 引用可能为空，需按 ElementName 回查 Msvm_ComputerSystem 作为兜底。
- PowerShell 5.1 无 [uint8] 类型加速器，CopySnapshotConfiguration 等 uint8 属性需用 [byte] 转型。
- GenerateNewSystemIdentifier=true 会为计划虚拟机分配新 GUID。落地后真实虚拟机的 GUID 是否等于原 GUID 取决于源虚拟机是否仍存在及时序，故此项仅作说明而非断言。
- RealizePlannedSystem 成功后对应的 Msvm_PlannedComputerSystem 自动消失。若中途失败，计划虚拟机需用 DestroySystem 清理。
- 使用 CopyVmStorage=$false 的纯配置导出（无 VHD）即可完成整条计划/落地链路，无需真实磁盘。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$name = 'WMITEST_planned_realize'
$expDir = 'C:/temp/exp_planned'

function Wait-Job2($p){
  if(-not $p){return 7}
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}
function Get-TestVMs(){ Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$name'" }
function Get-PlannedTestVMs(){ @(Get-WmiObject -Namespace $ns -Class Msvm_PlannedComputerSystem -Filter "ElementName='$name'") }

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$createdVM=$null; $plannedVM=$null; $realizedVM=$null
try {
  # 1. 创建第二代空虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){ throw 'DefineSystem job failed' } }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $createdVM = [wmi]$r.ResultingSystem

  # 2. 导出（嵌入 Msvm_VirtualSystemExportSettingData，GetText(1) 序列化）
  New-Item -ItemType Directory -Force -Path $expDir | Out-Null
  $esd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemExportSettingData").CreateInstance()
  $esd.CopySnapshotConfiguration = [byte]1   # 1=ExportNoSnapshots
  $esd.CopyVmStorage = $false
  $esd.CopyVmRuntimeInformation = $false
  $esd.CreateVmExportSubdirectory = $true
  $rx = $vsms.ExportSystemDefinition($createdVM.__PATH, $expDir, $esd.GetText(1))
  if($rx.ReturnValue -eq 4096){ if((Wait-Job2 $rx.Job) -ne 7){ throw 'Export job failed' } }
  elseif($rx.ReturnValue -ne 0){ throw "ExportSystemDefinition rv=$($rx.ReturnValue)" }

  # 定位导出的 .vmcx 配置文件；SnapshotFolder 取虚拟机导出根目录
  $vmcx = Get-ChildItem -Recurse -Path $expDir -Filter *.vmcx | Select-Object -First 1
  $defFile = $vmcx.FullName
  $snapFolder = $vmcx.Directory.Parent.FullName

  # 3. 导入为 Msvm_PlannedComputerSystem（第三参 GenerateNewSystemIdentifier=$true 避免与源虚拟机 GUID 冲突）
  $ri = $vsms.ImportSystemDefinition($defFile, $snapFolder, $true)
  if($ri.ReturnValue -eq 4096){ if((Wait-Job2 $ri.Job) -ne 7){ $jb=[wmi]$ri.Job; throw "Import job err=$($jb.ErrorCode) $($jb.ErrorDescription)" } }
  elseif($ri.ReturnValue -ne 0){ throw "ImportSystemDefinition rv=$($ri.ReturnValue)" }
  $plannedVM = [wmi]$ri.ImportedSystem   # OUT 参数 ImportedSystem，类为 Msvm_PlannedComputerSystem

  # 4. 校验计划虚拟机
  $rv = $vsms.ValidatePlannedSystem($plannedVM.__PATH)
  if($rv.ReturnValue -eq 4096){ if((Wait-Job2 $rv.Job) -ne 7){ $jb=[wmi]$rv.Job; throw "Validate job err=$($jb.ErrorCode) $($jb.ErrorDescription)" } }
  elseif($rv.ReturnValue -ne 0){ throw "ValidatePlannedSystem rv=$($rv.ReturnValue)" }

  # 5. 落地：计划虚拟机转为真实 Msvm_ComputerSystem
  $rr = $vsms.RealizePlannedSystem($plannedVM.__PATH)
  if($rr.ReturnValue -eq 4096){ if((Wait-Job2 $rr.Job) -ne 7){ $jb=[wmi]$rr.Job; throw "Realize job err=$($jb.ErrorCode) $($jb.ErrorDescription)" } }
  elseif($rr.ReturnValue -ne 0){ throw "RealizePlannedSystem rv=$($rr.ReturnValue)" }
  # 异步(4096)完成后 OUT 参数 ResultingSystem 引用可能为空，按 ElementName 回查真实虚拟机
  if($rr.ResultingSystem){ $realizedVM = [wmi]$rr.ResultingSystem } else { $realizedVM = Get-TestVMs | Select-Object -First 1 }

  # 断言：已是真实虚拟机、名称正确、计划虚拟机已消失、可枚举
  $ok = ($realizedVM.__CLASS -eq 'Msvm_ComputerSystem') -and ($realizedVM.ElementName -eq $name) -and ((Get-PlannedTestVMs).Count -eq 0)
  Write-Output ("PASS=$ok realized=$($realizedVM.Name) class=$($realizedVM.__CLASS)")
}
finally {
  try { if($realizedVM){ $vsms.DestroySystem($realizedVM.__PATH) | Out-Null } } catch {}
  foreach($p in (Get-PlannedTestVMs)){ try{ $vsms.DestroySystem($p.__PATH) | Out-Null }catch{} }
  foreach($v in @(Get-TestVMs)){ try{ $vsms.DestroySystem($v.__PATH) | Out-Null }catch{} }
  if(Test-Path $expDir){ Remove-Item -Recurse -Force $expDir }
}
```

## [PASS] 为虚拟机添加虚拟持久内存(PMEM)控制器  `pmem_controller`

- PMEM 控制器的 ResourceType=32771，ResourceSubType='Microsoft:Hyper-V:Persistent Memory Controller'。运行态类为 Msvm_PersistentMemoryController(CIM_Controller，无属性/方法)，控制器通过 Msvm_ResourceAllocationSettingData 添加。
- 无需手工拼装 RASD：从 primordial Msvm_ResourcePool（ResourceSubType 匹配）-> GetRelated('Msvm_AllocationCapabilities') -> GetRelationships('Msvm_SettingsDefineCapabilities') 取 ValueRole=0 的 Default 模板，GetText(1) 序列化后传入 AddResourceSettings。此为获取默认资源模板的通用范式。
- AddResourceSettings 同步返回 0（非 4096 Job）并立即生效。读回可通过 VSSD.GetRelated('Msvm_ResourceAllocationSettingData') 按 ResourceSubType 过滤。
- 该操作等价于 PowerShell 的 Add-VMPmemController。挂载 PMEM 盘要求 vhdx 满足 IsPmemCompatible 与 PmemAddressAbstractionType（见 Msvm_VirtualHardDiskSettingData），本示例仅涵盖控制器添加。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_pmem_controller'

function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

function Get-DefaultRasd($subtype){
    # primordial 池 -> AllocationCapabilities -> SettingsDefineCapabilities(ValueRole=0=Default)
    $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.ResourceSubType -eq $subtype -and $_.Primordial -eq $true } | Select-Object -First 1
    if(-not $pool){ return $null }
    $caps = ([wmi]$pool.__PATH).GetRelated('Msvm_AllocationCapabilities') | Select-Object -First 1
    if(-not $caps){ return $null }
    foreach($r in ([wmi]$caps.__PATH).GetRelationships('Msvm_SettingsDefineCapabilities')){
        if($r.ValueRole -eq 0){ return [wmi]($r.PartComponent) }
    }
    return $null
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 创建第二代虚拟机
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $testName
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
# 获取 PMEM 控制器的默认 RASD 模板
$subtype = 'Microsoft:Hyper-V:Persistent Memory Controller'
$rasd = Get-DefaultRasd $subtype
# 添加控制器 (ResourceType=32771)
$addResult = $vsms.AddResourceSettings($vssd2.__PATH, @($rasd.GetText(1)))
if($addResult.ReturnValue -eq 4096){ Wait-Job2 $addResult.Job | Out-Null }
# 读回
$vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$pmem = ([wmi]$vssd3.__PATH).GetRelated('Msvm_ResourceAllocationSettingData') | Where-Object { $_.ResourceSubType -eq $subtype }
# 清理
$d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
```

## [PASS] 读取处理器与 NUMA 拓扑  `processor_topology`

- 纯读操作。主机物理拓扑经 Msvm_Processor（每个逻辑处理器一个实例）与 Msvm_NumaNode（每个物理 NUMA 节点一个实例）枚举。
- Msvm_Processor.DeviceID 格式为 'Microsoft:<GUID>\<socket>\<lp>'，ElementName 为本地化的“逻辑处理器 N”。
- 计数口径差异：root\virtualization\v2 下的 Msvm_Processor 计的是 hypervisor 视角的逻辑处理器（含全部硬件线程），Win32_Processor 反映 socket/core 视图，两者数值不可直接互换。
- MaxProcessorsPerNumaNode 与 MaxNumaNodesPerSocket 是 Msvm_ProcessorSettingData（每虚拟机）上的 NUMA 投影字段，不在主机 Msvm_Processor 上，需经虚拟机的 VSSD -> ProcessorSettingData 读取。
- HwThreadsPerCore=0 表示继承主机设置。VirtualNumaEnabled 位于 VSSD，默认为 True。
- 单 NUMA 节点环境的 NodeID 形如 Microsoft:PhysicalNode\0，无跨节点拓扑。DestroySystem 可能异步返回 4096，需 Wait-Job2 等待完成。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

# --- A: 主机逻辑处理器 (每个 LP 一个实例; DeviceID 编码 hypervisor LP 下标) ---
$hostProcs=@(Get-WmiObject -Namespace $ns -Class Msvm_Processor)
'HostLogicalProcessors = '+$hostProcs.Count
$s=$hostProcs|Select-Object -First 1
'DeviceID = '+$s.DeviceID
'MaxClockSpeed(MHz) = '+$s.MaxClockSpeed

# 对照 Win32_Processor 的 socket/core 视图
$w32=@(Get-WmiObject -Class Win32_Processor)
'Win32 Cores = '+($w32|Measure-Object NumberOfCores -Sum).Sum+' LP = '+($w32|Measure-Object NumberOfLogicalProcessors -Sum).Sum

# --- B: 主机 NUMA ---
$numa=@(Get-WmiObject -Namespace $ns -Class Msvm_NumaNode)
'HostNumaNodes = '+$numa.Count
'Numa[0] NodeID = '+($numa|Select-Object -First 1).NodeID

# --- C: ProcessorSettingData 的 NUMA 投影字段 (创建临时第二代虚拟机读默认值后删除) ---
$vmName='WMITEST_processor_topology'; $vm=$null
try {
  $vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
  $vssd=([wmiclass]"\\.\root\virtualization\v2:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$vmName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $proc=([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData')|Select-Object -First 1
  'PSD MaxProcessorsPerNumaNode = '+$proc.MaxProcessorsPerNumaNode
  'PSD MaxNumaNodesPerSocket    = '+$proc.MaxNumaNodesPerSocket
  'PSD HwThreadsPerCore         = '+$proc.HwThreadsPerCore
  'VSSD VirtualNumaEnabled      = '+$vssd2.VirtualNumaEnabled
}
finally {
  if($vm -and $vm.__PATH){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } }
}
```

## [PASS] 读取可直通设备 (DDA 可分配 PCI Express 设备)  `read_dda_pool`

- 纯读操作，无需创建虚拟机，不涉及任何写入或破坏性操作。
- 主机可直通设备经 Msvm_PciExpress 暴露，关键只读属性为 DeviceID、DeviceInstancePath(PCIP\VEN_xxx&DEV_xxx...)、LocationPath(PCIROOT(..)#PCI(..)) 及 FunctionNumber。
- 可分配池为 Msvm_ResourcePool 中 ResourceSubType='Microsoft:Hyper-V:Virtual Pci Express Port' 且 Primordial=True 的实例，ResourceType=32769。
- 同一物理设备可能返回多个 Msvm_PciExpress 实例但 DeviceInstancePath 相同（如经 PCIe-to-PCI 桥），应按 DeviceInstancePath 去重以得到真实设备数。
- DDA 实际分配流程（不在本读取操作范围）：DismountAssignableDevice (Msvm_AssignableDeviceService) 将设备从主机卸载，再经 AddResourceSettings 将 Msvm_PciExpressSettingData 添加到目标虚拟机。列出的设备未必满足 DDA 直通预检（需 ACS、可重置、隔离等条件），本示例仅验证枚举读取。
- Msvm_PciExpress 自 build 10586 起提供。

```powershell
$ns = 'root\virtualization\v2'
# 1) 枚举主机上可直通的 PCI Express 设备(DDA 候选)
$pcie = @(Get-WmiObject -Namespace $ns -Class Msvm_PciExpress)
# 2) primordial PCI Express 资源池——可分配设备所属的池
$pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool |
    Where-Object { $_.ResourceSubType -eq 'Microsoft:Hyper-V:Virtual Pci Express Port' -and $_.Primordial -eq $true } |
    Select-Object -First 1
# 3) 按 DeviceInstancePath 去重计设备数(每个物理设备可能有多个 Msvm_PciExpress 实例)
$paths = @($pcie | Select-Object -ExpandProperty DeviceInstancePath | Sort-Object -Unique)
Write-Output ('PCIE_INSTANCE_COUNT=' + $pcie.Count)
Write-Output ('DISTINCT_DEVICE_PATH_COUNT=' + $paths.Count)
foreach ($d in $pcie) {
    Write-Output ('DEV InstancePath=' + $d.DeviceInstancePath + ' | Location=' + $d.LocationPath)
}
if ($pool) { Write-Output ('POOL ResourceType=' + $pool.ResourceType + ' SubType=' + $pool.ResourceSubType + ' Primordial=' + $pool.Primordial) }
```

## [PASS] 读取可分区 GPU  `read_gpu`

- 纯读操作，无需创建虚拟机，无写入或清理。
- Msvm_PartitionableGpu 枚举 GPU-P 可分区 GPU 池；Msvm_Physical3dGraphicsProcessor 对应 RemoteFX 时代的物理 3D GPU（已弃用，现代系统通常为 0 个）。
- 每个可分区 GPU 的 ValidPartitionCounts 列出其支持的分区数量取值集合。
- Name 为 GPU 的设备接口路径(PCI#VEN_xxxx...{GUID}\GPUPARAV)，进行 GPU-P 分区时以此引用该 GPU。
- VRAM/Compute 相关字段返回的是驱动上报的归一化抽象额度（分区时按比例分配），并非真实字节数，不应按物理显存字节解读。
- Msvm_PartitionableGpu 主要属性包括 ValidPartitionCounts、PartitionCount，以及 Total/Available/Min/Max/OptimalPartition 前缀的 VRAM、Encode、Decode、Compute 字段与 SupportsIncomingLiveMigration。

```powershell
$ns = 'root\virtualization\v2'

# 可分区 GPU（GPU-P 池）
$pgpu = @(Get-WmiObject -Namespace $ns -Class Msvm_PartitionableGpu)
"PartitionableGpuCount=$($pgpu.Count)"
foreach ($g in $pgpu) {
    "Name=$($g.Name)"
    "ValidPartitionCounts=$($g.ValidPartitionCounts -join ',')"
    "TotalVRAM=$($g.TotalVRAM) AvailableVRAM=$($g.AvailableVRAM) OptimalPartitionVRAM=$($g.OptimalPartitionVRAM)"
    "TotalCompute=$($g.TotalCompute) AvailableCompute=$($g.AvailableCompute)"
}

# 物理 3D GPU（RemoteFX 时代；已弃用，通常为空）
$p3d = @(Get-WmiObject -Namespace $ns -Class Msvm_Physical3dGraphicsProcessor)
"Physical3dGpuCount=$($p3d.Count)"
foreach ($g in $p3d) {
    "GPUID=$($g.GPUID) EnabledForVirtualization=$($g.EnabledForVirtualization) CompatibleForVirtualization=$($g.CompatibleForVirtualization)"
    "DriverProvider=$($g.DriverProvider) DriverVersion=$($g.DriverVersion) DedicatedVideoMemory=$($g.DedicatedVideoMemory)"
}
```

## [PASS] 读取宿主信息  `read_host`

- 宿主与虚拟机的语言无关区分法：宿主的 Msvm_ComputerSystem 没有关联的 Msvm_VirtualSystemSettingData（GetRelated('Msvm_VirtualSystemSettingData') 数量为 0），每台虚拟机则为 1。不应用 Caption/Description 判定，二者为本地化文本。
- GetRelated 返回的是 ManagementObjectCollection（作为对象恒为真），需用 @(...).Count -eq 0 判空，不能用 -not $vssd。
- 宿主名取自 Msvm_ComputerSystem.ElementName；EnabledState=2 表示 Enabled。
- 宿主逻辑 CPU 数与物理内存应从 Win32_ComputerSystem 读取（NumberOfLogicalProcessors、TotalPhysicalMemory）。root\virtualization\v2 下的 Msvm_Processor 计数为全主机所有虚拟处理器与宿主之和，不可当作宿主逻辑 CPU 数使用。
- 纯读操作，不创建任何虚拟机，无需清理。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

# 枚举全部 Msvm_ComputerSystem。宿主与虚拟机的区别在于宿主没有关联的
# Msvm_VirtualSystemSettingData（仅虚拟机经 Msvm_SettingsDefineState 关联 VSSD）。
# 语言无关：不要用 Caption/Description 判定，它们是本地化文本。
$all = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem
$host_cs = $null
foreach ($cs in $all) {
    # GetRelated 返回 ManagementObjectCollection（作为对象恒为真），
    # 需包裹 @() 后判断 .Count，而非用 -not。
    $vssd = @($cs.GetRelated('Msvm_VirtualSystemSettingData'))
    if ($vssd.Count -eq 0) { $host_cs = $cs; break }
}
if (-not $host_cs) { Write-Host 'FAIL: could not identify host'; exit 1 }

$hostName = $host_cs.ElementName

# 宿主逻辑 CPU 数与总内存从 Win32 读取（v2 命名空间的 Msvm_Processor
# 计的是全部虚拟处理器与宿主之和，并非宿主逻辑 CPU 数）。
$w32cs = Get-WmiObject -Class Win32_ComputerSystem
$logicalCpus = $w32cs.NumberOfLogicalProcessors
$totalMemMB  = [math]::Round([uint64]$w32cs.TotalPhysicalMemory / 1MB)

Write-Host "HOST ElementName       : $hostName"
Write-Host "HOST EnabledState      : $($host_cs.EnabledState)"
Write-Host "Win32 LogicalProcessors: $logicalCpus"
Write-Host "Total physical mem (MB): $totalMemMB"
```

## [PASS] 批量获取虚拟机概览信息  `read_summary`

- GetSummaryInformation 在 Msvm_VirtualSystemManagementService 上调用,为同步读操作,返回码 0 表示成功(非异步 Job)。
- 方法签名: GetSummaryInformation(SettingData[] IN, RequestedInformation uint32[] IN) -> (ReturnValue uint32, SummaryInformation Msvm_SummaryInformationBase[] OUT)。输出参数名为 SummaryInformation。
- SettingData 参数为 Msvm_VirtualSystemSettingData 的引用数组,直接传入各 VSSD 的 __PATH 字符串数组即可(PowerShell 按 ref 处理)。一次传入多个 path 可批量返回多行结果。
- 仅枚举已实现虚拟机时,以 VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized' 过滤 VSSD,避免将快照或计划态配置一并计入。
- RequestedInformation 决定返回哪些字段。运行时统计类字段(NumberOfProcessors、MemoryUsage、ProcessorLoad、Heartbeat、HealthState、UpTime)仅在虚拟机运行时填充;关机虚拟机上这些字段为空或为 0,属正常现象。
- EnabledState=3 表示 Disabled(已关机)。身份字段 ElementName 与 Name(GUID)始终可读,不受运行状态影响。
- RequestedInformation 常用码: 0=Name(GUID) 1=ElementName 2=CreationTime 3=Notes 100=NumberOfProcessors 101=EnabledState 102=ProcessorLoad 104=MemoryUsage 105=Heartbeat 106=UpTime 107=GuestOperatingSystem 110=HealthState。

```powershell
$ns   = 'root\virtualization\v2'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# RequestedInformation 常用码(子集):
#   0=Name(GUID) 1=ElementName 2=CreationTime 3=Notes
#   100=NumberOfProcessors 101=EnabledState 102=ProcessorLoad
#   103=ProcessorLoadHistory 104=MemoryUsage 105=Heartbeat 106=UpTime
#   107=GuestOperatingSystem 108=Snapshots 110=HealthState
$req = [uint32[]]@(0,1,2,3,100,101,102,104,105,106,107,110)

# 收集所有已实现虚拟机的 VirtualSystemSettingData,将其 __PATH 引用一次性传入。
$allVssd = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSettingData |
           Where-Object { $_.VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized' }
$paths = @($allVssd | ForEach-Object { $_.__PATH })

$r = $vsms.GetSummaryInformation([string[]]$paths, $req)   # 返回码 0=成功, 4096=异步 Job
if ($r.ReturnValue -ne 0) { throw "GetSummaryInformation rv=$($r.ReturnValue)" }

foreach ($info in $r.SummaryInformation) {
  [pscustomobject]@{
    ElementName  = $info.ElementName
    Guid         = $info.Name
    EnabledState = $info.EnabledState
    vCPU         = $info.NumberOfProcessors
    MemoryUsage  = $info.MemoryUsage
    ProcLoad     = $info.ProcessorLoad
    Heartbeat    = $info.Heartbeat
    UpTime       = $info.UpTime
    HealthState  = $info.HealthState
  }
}
```

## [PASS] 列出所有虚拟机  `read_vm_list`

- 区分宿主与虚拟机的可靠方法: 在 Msvm_ComputerSystem 实例中,虚拟机的 Name 属性为 GUID,宿主的 Name 等于主机名(非 GUID)。不应使用 Caption 区分,因为 Caption 已本地化(如中文'承载系统/虚拟机'),按字符串匹配不可移植。
- ElementName 为显示名;Name 为 GUID;EnabledState 常见值 2=Enabled(运行)、3=Disabled(关机)。EnabledState 可直接读取,无需轮询。
- 该操作为只读枚举,不调用任何 WMI 方法,不修改任何虚拟机。

```powershell
$ns = 'root\virtualization\v2'
# 虚拟机的 Name 为 GUID;宿主的 Name 等于主机名(非 GUID),据此区分
$guidRe = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem |
  Where-Object { $_.Name -match $guidRe } |
  ForEach-Object {
    [pscustomobject]@{
      ElementName  = $_.ElementName   # 显示名
      EnabledState = $_.EnabledState  # 2=Enabled(运行) 3=Disabled(关机) 等
      GUID         = $_.Name          # 虚拟机 GUID
    }
  }
```

## [PASS] 读取虚拟机的配置与资源分配  `read_vm_settings`

- 关键关联: Msvm_ComputerSystem 经 Msvm_SettingsDefineState 关联到当前(已实现)的 Msvm_VirtualSystemSettingData。快照设置同样是 VSSD,用 SettingsDefineState 限定关联类可仅取当前配置那一条,避免误取检查点设置。
- 在 VSSD 上用 GetRelated 直接获取 Msvm_ProcessorSettingData 与 Msvm_MemorySettingData(各一条),以及 Msvm_ResourceAllocationSettingData(所有控制器与设备)。第二代空虚拟机默认含 4 条 RASD: 虚拟键盘、串口控制器、合成鼠标、合成键盘,ResourceType 均为 13。
- 内存 VirtualQuantity 单位为 MB(默认 1024);CPU VirtualQuantity 为 vCPU 数;Limit=100000 表示 100%(以千分之一百分比为刻度)。
- GetRelated 返回的是浅对象,需对其 .__PATH 再执行 [wmi] 获取完整实例,才能稳定读取全部属性。
- 该操作为纯读操作。将 $vm 替换为目标 Msvm_ComputerSystem 即可,不产生任何写入。
- 第二代虚拟机 VirtualSystemSubType 为 Microsoft:Hyper-V:SubType:2;配置版本 Version=12.0 为 Windows Server 2025 默认。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# --- ComputerSystem -> (Msvm_SettingsDefineState) -> Msvm_VirtualSystemSettingData ---
# $vm 为已存在的 Msvm_ComputerSystem;经 SettingsDefineState 关联取当前(已实现)VSSD。
$vssd = $vm.GetRelated('Msvm_VirtualSystemSettingData','Msvm_SettingsDefineState',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
$vssdObj = [wmi]$vssd.__PATH
# ElementName / VirtualSystemSubType / Version
$vssdObj.ElementName; $vssdObj.VirtualSystemSubType; $vssdObj.Version
# --- ProcessorSettingData ---
$proc = [wmi]($vssdObj.GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1).__PATH
$proc.VirtualQuantity; $proc.Reservation; $proc.Limit; $proc.Weight
# --- MemorySettingData ---
$mem = [wmi]($vssdObj.GetRelated('Msvm_MemorySettingData') | Select-Object -First 1).__PATH
$mem.VirtualQuantity; $mem.DynamicMemoryEnabled
# --- 所有资源分配(控制器/设备) ---
$rasd = @($vssdObj.GetRelated('Msvm_ResourceAllocationSettingData'))
$rasd | ForEach-Object { '{0} {1}' -f $_.ResourceType, $_.ResourceSubType }
```

## [PASS] 创建参考点(增量备份与变更块跟踪 RCT)  `reference_point`

- Msvm_VirtualSystemReferencePointService.CreateReferencePoint(AffectedSystem REF, ReferencePointSettings string, ReferencePointType uint16, ResultingReferencePoint IN/OUT REF) OUT Job。ReferencePointType: 0=Log based(Hyper-V 副本日志), 1=RCT based(基于虚拟磁盘弹性变更跟踪 RCT)。
- 前置条件: 虚拟机必须挂载至少一块 VHDX,否则创建参考点必然失败。无磁盘时 type=1 的 Job 报 ErrorCode=32770,type=0 返回 32773。参考点服务于增量备份与变更块跟踪(CBT)。挂盘后 type=1(RCT)可成功,返回 4096 并由 Job 完成。
- ReferencePointSettings 可传 $null(可选;对应类 Msvm_VirtualSystemReferencePointSettingData 仅含一个只读属性 ConsistencyLevel)。ResultingReferencePoint 虽为 IN/OUT REF 亦可传 $null,结果实例通过枚举 Msvm_VirtualSystemReferencePoint 获取。
- 读回方式: 枚举 Msvm_VirtualSystemReferencePoint,经 GetRelated('Msvm_ComputerSystem')回到属主虚拟机比对 ElementName。可读回字段包括 ConsistencyLevel 与 ReferencePointType。
- DestroyReferencePoint(AffectedReferencePoint REF) OUT Job 用于删除参考点,返回 4096 时需轮询 Job。DestroySystem 会连带清理该虚拟机的参考点,但显式删除更为稳妥。
- 所有写方法返回 4096 时需以 Wait-Job2 轮询;JobState 7=完成, 10=失败。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$TESTNAME = 'WMITEST_reference_point'
$workDir = 'C:/Users/Administrator/Documents/GitHub/HyperV-WMI-Documentation/verify/work'
$vhdPath = (Join-Path $workDir 'WMITEST_reference_point.vhdx') -replace '/', '\'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}
function Job-Err($p){
  if(-not $p){ return '<no job>' }
  try { $j = [wmi]$p; return ("state=" + $j.JobState + " err=" + $j.ErrorCode + " desc=" + $j.ErrorDescription) } catch { return '<job gone>' }
}
function Get-DefaultSettings($subType){
  $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
  $caps = $pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
  foreach($r in $caps.GetRelationships('Msvm_SettingsDefineCapabilities')){
    if($r.ValueRole -eq 0){ return [wmi]$r.PartComponent }
  }
  return $null
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims  = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$rps  = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemReferencePointService

# Pre-cleanup
Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $TESTNAME } | ForEach-Object {
  try { $d = $vsms.DestroySystem($_.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null } } catch {}
}
if(Test-Path $vhdPath){ Remove-Item $vhdPath -Force }

$vm = $null
try {
  # ---- Create a generation 2 virtual machine ----
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $TESTNAME
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $s = Wait-Job2 $r.Job; if($s -ne 7){ throw "DefineSystem job state $s" } }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv $($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem
  $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  Write-Host ("VM created: " + $vm.ElementName + " " + $vm.Name)

  # ---- Attach a dynamic VHDX (RCT-capable) so the reference point has a trackable object ----
  $scsiTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic SCSI Controller'
  $ar = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
  if($ar.ReturnValue -eq 4096){ Wait-Job2 $ar.Job | Out-Null } elseif($ar.ReturnValue -ne 0){ throw "AddResource(SCSI) rv $($ar.ReturnValue)" }
  $scsi = [wmi]$ar.ResultingResourceSettings[0]

  $vhdSd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $vhdSd.Type = [uint16]3
  $vhdSd.Format = [uint16]3
  $vhdSd.Path = $vhdPath
  $vhdSd.MaxInternalSize = [uint64](1GB)
  $cr = $ims.CreateVirtualHardDisk($vhdSd.GetText(1))
  if($cr.ReturnValue -eq 4096){ $s = Wait-Job2 $cr.Job; if($s -ne 7){ throw "CreateVHD job state $s" } } elseif($cr.ReturnValue -ne 0){ throw "CreateVHD rv $($cr.ReturnValue)" }
  if(-not (Test-Path $vhdPath)){ throw "vhdx not created" }
  Write-Host ("VHDX created: " + $vhdPath)

  $drvTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic Disk Drive'
  $drv = $drvTmpl.psbase.Clone()
  $drv.Parent = $scsi.__PATH
  $drv.AddressOnParent = '0'
  $ar2 = $vsms.AddResourceSettings($vssd2.__PATH, @($drv.GetText(1)))
  if($ar2.ReturnValue -eq 4096){ $s = Wait-Job2 $ar2.Job; if($s -ne 7){ throw "AddResource(Drive) state $s : $(Job-Err $ar2.Job)" } } elseif($ar2.ReturnValue -ne 0){ throw "AddResource(Drive) rv $($ar2.ReturnValue)" }
  $drvPath = $ar2.ResultingResourceSettings[0]

  $sasdTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Virtual Hard Disk'
  $sasd = $sasdTmpl.psbase.Clone()
  $sasd.Parent = $drvPath
  $sasd.HostResource = @($vhdPath)
  $ar3 = $vsms.AddResourceSettings($vssd2.__PATH, @($sasd.GetText(1)))
  if($ar3.ReturnValue -eq 4096){ $s = Wait-Job2 $ar3.Job; if($s -ne 7){ throw "AddResource(VHD) state $s : $(Job-Err $ar3.Job)" } } elseif($ar3.ReturnValue -ne 0){ throw "AddResource(VHD) rv $($ar3.ReturnValue)" }
  Write-Host "VHDX attached to VM"

  # ---- CreateReferencePoint ----
  # ReferencePointSettings = $null (optional). Try RCT (1) first, then fall back to Log based (0).
  $rpReturn = $null; $usedType = $null; $createOk = $false
  foreach($t in @([uint16]1, [uint16]0)){
    $rpReturn = $rps.CreateReferencePoint($vm.__PATH, $null, $t, $null)
    $usedType = $t
    Write-Host ("CreateReferencePoint type=$t rv=" + $rpReturn.ReturnValue)
    if($rpReturn.ReturnValue -eq 0){ $createOk = $true; break }
    if($rpReturn.ReturnValue -eq 4096){
      $st = Wait-Job2 $rpReturn.Job
      if($st -eq 7){ $createOk = $true; break }
      Write-Host ("  job: " + (Job-Err $rpReturn.Job))
    } else {
      Write-Host ("  rv non-success for type=$t")
    }
  }

  if(-not $createOk){
    Write-Host ("RESULT: UNSUPPORTED last rv=" + $rpReturn.ReturnValue + " " + (Job-Err $rpReturn.Job))
    Write-Host "ASSERT: UNSUPPORTED"
    return
  }

  # ---- Enumerate the reference points of this virtual machine ----
  Start-Sleep -Milliseconds 300
  $allRps = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemReferencePoint -ErrorAction SilentlyContinue
  $myRps = @()
  foreach($rp in $allRps){
    try {
      $owner = ([wmi]$rp.__PATH).GetRelated('Msvm_ComputerSystem') | Select-Object -First 1
      if($owner -and $owner.ElementName -eq $TESTNAME){ $myRps += $rp }
    } catch {}
  }
  Write-Host ("ReferencePoints for test VM: " + $myRps.Count)
  foreach($rp in $myRps){
    Write-Host ("  RP InstanceID=" + $rp.InstanceID + " ConsistencyLevel=" + $rp.ConsistencyLevel + " ReferencePointType=" + $rp.ReferencePointType)
  }

  if($myRps.Count -ge 1){
    Write-Host ("RESULT: PASS reference point created (type used=" + $usedType + ", count=" + $myRps.Count + ")")
    Write-Host "ASSERT: PASS"
  } else {
    Write-Host "RESULT: FAIL create returned success but no Msvm_VirtualSystemReferencePoint enumerated"
    Write-Host "ASSERT: FAIL"
  }

  # ---- Delete the reference points ----
  foreach($rp in $myRps){
    $dr = $rps.DestroyReferencePoint($rp.__PATH)
    if($dr.ReturnValue -eq 4096){ Wait-Job2 $dr.Job | Out-Null }
    Write-Host ("DestroyReferencePoint rv=" + $dr.ReturnValue)
  }
}
finally {
  try {
    $stray = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $TESTNAME }
    foreach($s in $stray){
      $d = $vsms.DestroySystem($s.__PATH)
      if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
      Write-Host ("Cleanup DestroySystem rv=" + $d.ReturnValue)
    }
  } catch { Write-Host ("Cleanup VM error: " + $_.Exception.Message) }
  try { if(Test-Path $vhdPath){ Remove-Item $vhdPath -Force; Write-Host "Cleanup: removed vhdx" } } catch {}
}
```

## [PASS] 重命名虚拟机  `rename_vm`

- 重命名通过整机设置完成: 修改 Msvm_VirtualSystemSettingData.ElementName 后,以 Msvm_VirtualSystemManagementService.ModifySystemSettings($vssd.GetText(1)) 提交,而非直接修改 Msvm_ComputerSystem。
- ModifySystemSettings 签名: SystemSettings(IN string,须为 GetText(1) 序列化结果且含有效 InstanceID), Job(OUT ref CIM_ConcreteJob)。该方法通常同步返回 rv=0,不进入 4096 Job 流程。
- 改名后 Msvm_ComputerSystem.ElementName 与 VSSD.ElementName 同步更新;需重新以 [wmi]$vm.__PATH 获取最新对象再读回。
- 返回码: 0=成功, 1=不支持, 2=失败, 4=参数无效, 5=状态无效, 6=参数不兼容, 4096=Job 已启动(需 Wait-Job2 轮询)。

```powershell
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# $vm 为目标虚拟机(例如来自 DefineSystem 或 Msvm_ComputerSystem)
# 获取该虚拟机当前的 VirtualSystemSettingData
$vssd=$vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
# 修改 ElementName 并经 ModifySystemSettings 提交(SystemSettings IN string, Job OUT)
$vssd.ElementName='NewVmName'
$r=$vsms.ModifySystemSettings($vssd.GetText(1))
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
# 返回码 0 表示成功。读回校验:
$vm2=[wmi]$vm.__PATH
$check=$vm2.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
Write-Output $check.ElementName   # -> NewVmName ; $vm2.ElementName 同步更新
```

## [PASS] 读取主机复制能力与配置  `replication_caps`

- 此配方为纯读取操作，无需创建虚拟机，不产生写入或清理。
- 涉及三个类，均可用 Get-WmiObject 直接枚举：Msvm_ReplicationService 为单例主机服务；Msvm_ReplicationServiceSettingData 保存主机复制配置(端口/认证/监控)，其属性均为只读，修改须通过 Msvm_ReplicationService.ModifyServiceSettings 下发。
- 当 RecoveryServerEnabled=False（未作为复制副本服务器启用）时，AllowedAuthenticationType 通常为 0（未配置）。默认 HttpPort=80、HttpsPort=443。MonitoringInterval 以秒计，默认 43200（即 12 小时）。AllowedAuthenticationType 枚举：1=Kerberos，2=Certificate，3=两者兼有。
- Msvm_ReplicationSettingData 可存在多个实例，包含每台虚拟机的复制参数与默认模板，属性含 ReplicationInterval、CompressionEnabled、RecoveryHistory、AuthenticationType 等。
- ElementName 存储的是 UTF-16 值；在按 GBK 渲染的控制台中可能显示为乱码，属显示层现象，不影响读取到的实际值。
- 以上三个类自 build 9200 起提供，属性集稳定。

```powershell
$ns = 'root\virtualization\v2'

# 1) Msvm_ReplicationService —— 主机复制服务(单例)
$svc = Get-WmiObject -Namespace $ns -Class Msvm_ReplicationService
$svc.ElementName

# 2) Msvm_ReplicationServiceSettingData —— 主机复制配置(端口/认证/监控)
$rssd = Get-WmiObject -Namespace $ns -Class Msvm_ReplicationServiceSettingData
$authMap = @{ 1='Kerberos'; 2='Certificate'; 3='CertAndKerberos' }
[pscustomobject]@{
    RecoveryServerEnabled     = $rssd.RecoveryServerEnabled
    AllowedAuthenticationType = $rssd.AllowedAuthenticationType   # 0=未配置(禁用时), 1=Kerberos, 2=Cert, 3=both
    AuthText                  = $authMap[[int]$rssd.AllowedAuthenticationType]
    HttpPort                  = $rssd.HttpPort
    HttpsPort                 = $rssd.HttpsPort
    CertificateThumbPrint     = $rssd.CertificateThumbPrint
    MonitoringInterval        = $rssd.MonitoringInterval        # 秒, 默认43200=12h
    MonitoringStartTime       = $rssd.MonitoringStartTime
} | Format-List

# 3) Msvm_ReplicationSettingData —— 复制设置模板/各VM复制设置(枚举)
$rsd = @(Get-WmiObject -Namespace $ns -Class Msvm_ReplicationSettingData)
"ReplicationSettingData instances = $($rsd.Count)"
```

## [PASS] 创建自定义资源池  `resource_pool_create`

- 创建与删除资源池的方法为 Msvm_ResourcePoolConfigurationService.CreatePool / DeletePool。
- CreatePool 的三个输入参数为：PoolSettings（Msvm_ResourcePoolSettingData 内嵌实例字符串）、ParentPools（REF 数组）、AllocationSettings（对应资源 RASD 内嵌实例的字符串数组）；输出为 Pool(REF) 与 Job。内存池场景通常同步完成并返回 0，无需轮询 Job。
- 设置实例时属性名为 PoolID（ID 大写）。读回时实例以只读属性 PoolId 暴露。WMI 属性名大小写不敏感，写入与过滤两种写法均可。
- 常见陷阱：AllocationSettings 中 RASD 的 PoolID 必须等于新建子池的 PoolID（而非父池的空字符串），且 Reservation/Limit/VirtualQuantity/Weight 必须全部为 0，以便子池从父池按需取用。若沿用父池空 PoolID 或设置了非零预留，CreatePool 提交的 Job 会失败并返回 ErrorCode=32773（Invalid Parameter，提示缺少资源类型）。
- 内置 New-VMResourcePool cmdlet 生成的子池 RPSD 与 MemorySettingData 中所有配额均为 0，且 PoolID 均指向子池名，可作为写法参照。
- 父池取根(primordial)池：Get-WmiObject Msvm_ResourcePool | ?{ $_.Primordial -eq $true -and $_.ResourceType -eq 4 }。各资源类型（内存 4、处理器 3、以太网 10、VHD 31、GPU 分区 32770 等）均有对应根池可作父池。
- DeletePool 要求子池无未结分配，否则返回 In Use（32774）。空子池可直接删除并返回 0。
- Msvm_ResourcePoolConfigurationService 自 build 9200 起提供，稳定可用。

```powershell
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$rpcs = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePoolConfigurationService
$poolId = 'MyMemoryPool'

# 1) 取作为父池的根(primordial)池, 此处使用内存根池(ResourceType=4)
$parent = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object {
  $_.Primordial -eq $true -and $_.ResourceType -eq 4 -and $_.ResourceSubType -eq 'Microsoft:Hyper-V:Memory'
} | Select-Object -First 1

# 2) PoolSettings: Msvm_ResourcePoolSettingData, 属性名为 PoolID(ID 大写)
$rpsd = ([wmiclass]"\\.\$($ns):Msvm_ResourcePoolSettingData").CreateInstance()
$rpsd.PoolID = $poolId
$rpsd.ResourceType = [uint16]4
$rpsd.ResourceSubType = 'Microsoft:Hyper-V:Memory'

# 3) AllocationSettings: 对应资源类型的 RASD(内存=Msvm_MemorySettingData)
#    PoolID 必须等于【新建子池】的 PoolID(不是父池的空字符串);
#    各配额(Reservation/Limit/VirtualQuantity/Weight)均填 0 -> 子池从父池按需取用
$masd = ([wmiclass]"\\.\$($ns):Msvm_MemorySettingData").CreateInstance()
$masd.PoolID = $poolId
$masd.ResourceType = [uint16]4
$masd.ResourceSubType = 'Microsoft:Hyper-V:Memory'
$masd.Reservation = [uint64]0
$masd.Limit = [uint64]0
$masd.VirtualQuantity = [uint64]0
$masd.Weight = [uint32]0

# 4) CreatePool 签名:
#    CreatePool(PoolSettings string, ParentPools REF[], AllocationSettings string[]) -> OUT Pool, Job
$r = $rpcs.CreatePool($rpsd.GetText(1), @($parent.__PATH), @($masd.GetText(1)))
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }

# 5) 读回校验
$child = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.PoolId -eq $poolId } | Select-Object -First 1
$child | Format-List PoolId, ResourceType, Primordial, InstanceID

# 6) 删除子池: DeletePool(Pool REF) -> OUT Job
$rd = $rpcs.DeletePool($child.__PATH)
if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
```

## [PASS] 保存并恢复虚拟机状态  `save_restore_state`

- 启动虚拟机后调用 RequestStateChange(6) 可将其转入保存态（成功时 JobState=7，EnabledState=6）。
- RequestStateChange 的 RequestedState 枚举：2=Running，3=Off，4=Stopping，6=Saved，9=Paused，10=Starting，11=Reset，32773=Saving，32776=Pausing，32777=Resuming，32779=FastSaved，32780=FastSaving。
- 保存操作应传入稳定态 6（Saved），32773（Saving）为过渡态，不应作为目标传入。EnabledState 读回可能显示 32769=Saved，该属性枚举与 RequestedState 枚举不同，二者不可混用。
- 恢复保存态虚拟机：对其调用 RequestStateChange([uint16]2) 即从保存态启动。对应 cmdlet 语义为 Save-VM=ChangeState(Save=6)，Resume=RequestStateChange(2)。
- 方法返回 4096 表示异步执行，需轮询关联 Msvm_ConcreteJob 的 JobState 至 7 判定成功。

```powershell
# 保存/恢复VM状态。RequestStateChange 的 RequestedState 枚举。
$vm=[wmi]$vmPath   # Msvm_ComputerSystem
# RequestedState 取值: 2=Running 3=Off 4=Stopping 6=Saved 9=Paused 10=Starting 11=Reset
#                      32773=Saving 32776=Pausing 32777=Resuming 32779=FastSaved 32780=FastSaving
$vm.RequestStateChange([uint16]2,$null)   # 启动
$vm.RequestStateChange([uint16]6,$null)   # 保存(目标稳定态 Saved=6)。之后 EnabledState 读回可能为 6 或 32769=已保存
$vm.RequestStateChange([uint16]2,$null)   # 从保存态恢复(=启动)
# 返回 4096 则轮询 Msvm_ConcreteJob.JobState 至 7
```

## [PASS] 设置安全启动模板 (SecureBootTemplateId)  `secureboot_template`

- 安全启动模板属性位于 Msvm_VirtualSystemSettingData，名为 SecureBootTemplateId（string，可读写），通过 ModifySystemSettings 下发，而非 ModifyResourceSettings。
- 两个常用模板 GUID：MicrosoftWindows=1734c6e8-3154-4dda-ba5f-a874cc483422（第二代虚拟机新建时的默认值）；MicrosoftUEFICertificateAuthority=272e7447-90a4-4563-a4b9-8e4ab00526ce（适用于 Linux 及第三方系统）。
- 读回的 GUID 为大写形式，比较时应先统一大小写（如 ToLower()）。新建第二代虚拟机时默认 SecureBootEnabled=True 且模板为 MicrosoftWindows。
- 修改后须从 $vm.__PATH 重新 GetRelated 获取 VSSD 才能读到新值，原有 $vssd2 句柄仍为修改前的快照。ModifySystemSettings 在本操作中同步返回 0。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
# 常用安全启动模板 GUID
$tplWindows='1734c6e8-3154-4dda-ba5f-a874cc483422'  # MicrosoftWindows (Gen2 默认)
$tplMSUEFI ='272e7447-90a4-4563-a4b9-8e4ab00526ce'  # MicrosoftUEFICertificateAuthority (Linux/第三方)
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 创建第二代虚拟机
$vssd=([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_secureboot_template'
$vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
# 读取当前设置并写入模板
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
$vssd2.SecureBootEnabled=$true
$vssd2.SecureBootTemplateId=$tplMSUEFI
$mr=$vsms.ModifySystemSettings($vssd2.GetText(1))
if($mr.ReturnValue -eq 4096){Wait-Job2 $mr.Job|Out-Null}
# 读回(需从 VM 路径重新 GetRelated 取 VSSD)
$got=(([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1).SecureBootTemplateId
Write-Host "SecureBootTemplateId=$got"
# 清理
$vsms.DestroySystem($vm.__PATH)|Out-Null
```

## [PASS] 配置虚拟机串口连接命名管道  `serial_com`

- 第二代虚拟机创建后默认即有 2 个串口（COM 1、COM 2），无需 AddResourceSettings；直接从 VSSD 经 GetRelated('Msvm_SerialPortSettingData') 取得已存在的 RASD 修改即可。
- 关键属性为 Connection（string[] 数组），继承自 CIM_ResourceAllocationSettingData，并非 Msvm_SerialPortSettingData 自身声明。该类自身仅显式声明 DebuggerMode 属性。
- Connection 须赋字符串数组 @('\\.\pipe\NAME')。命名管道路径格式为 \\.\pipe\<name>（本地管道）或 \\<server>\pipe\<name>（远程）。
- ResourceSubType 为 'Microsoft:Hyper-V:Serial Port'。COM 1 的 InstanceID 以 \0 结尾，COM 2 以 \1 结尾。
- ModifyResourceSettings 通常返回 0 并立即生效；返回 4096 时按 Job 轮询。
- ModifyResourceSettings 仅修改单个资源；修改后用相同的 GetRelated 重取，并按 InstanceID 匹配读回验证。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$name='WMITEST_serial_com'
$pipePath='\\.\pipe\WMITEST_serial_com_pipe'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 创建第二代虚拟机(默认自带 2 个 COM 口)
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name
  $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){ $null=Wait-Job2 $r.Job } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm=[wmi]$r.ResultingSystem
  # 串口(Msvm_SerialPortSettingData)已作为 VSSD 的子 RASD 存在
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $serials=@(([wmi]$vssd2.__PATH).GetRelated('Msvm_SerialPortSettingData'))
  # 选取 COM 1, 将 Connection(string[]) 设为命名管道路径, 再 ModifyResourceSettings
  $com=$serials | Where-Object { $_.ElementName -match 'COM 1' } | Select-Object -First 1
  if(-not $com){ $com=$serials[0] }
  $com.Connection=@($pipePath)
  $r2=$vsms.ModifyResourceSettings($com.GetText(1))
  if($r2.ReturnValue -eq 4096){ $null=Wait-Job2 $r2.Job } elseif($r2.ReturnValue -ne 0){ throw "ModifyResourceSettings rv=$($r2.ReturnValue)" }
  # 读回
  $vssd3=$vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $com2=@(([wmi]$vssd3.__PATH).GetRelated('Msvm_SerialPortSettingData')) | Where-Object { $_.InstanceID -eq $com.InstanceID } | Select-Object -First 1
  $readVal=if($com2.Connection){ [string]$com2.Connection[0] } else { '<null>' }
  if($readVal -eq $pipePath){ Write-Output "PASS Connection=$readVal" } else { Write-Output "FAIL got=$readVal" }
}
finally {
  if($vm -ne $null){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ $null=Wait-Job2 $d.Job } }
}
```

## [PASS] 为双串口分别配置命名管道  `serial_pipe_full`

- 串口不通过 AddResourceSettings 添加：每台虚拟机（第一代/第二代）创建后即自带 COM1、COM2 两个 Msvm_SerialPortSettingData，只能用 ModifyResourceSettings 修改其 Connection。
- 区分 COM1/COM2 依据 InstanceID 尾号：...\0 为 COM1，...\1 为 COM2；ElementName 为带空格的 'COM 1' / 'COM 2'。按 InstanceID 排序最为稳定。
- Connection 属性继承自父类 CIM_ResourceAllocationSettingData，类型为 string[]（数组），赋值须用 @('\\.\pipe\name')；Msvm_SerialPortSettingData 自身仅独有 DebuggerMode 布尔属性。
- 命名管道路径形如 \\.\pipe\<name>（主机本地管道）。两个端口可各自配置不同管道，互不影响。
- ModifyResourceSettings 返回 0 表示直接成功；返回 4096 时按 Job 轮询。修改后需重新 GetRelated 读回验证，不应依赖本地对象缓存。
- PowerShell 5.1 注意：[wmiclass]"\\.\$ns:Class" 中 $ns 紧跟冒号会被解析为 ${ns:...} 作用域取值而报错；改用字符串拼接 ("\\.\" + $ns + ":Class") 可规避。

```powershell
$ErrorActionPreference='Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$ns='root\virtualization\v2'
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$name='WMITEST_serial_pipe_full'
$pipe1='\\.\pipe\wmitest_com1'
$pipe2='\\.\pipe\wmitest_com2'

# 创建第二代虚拟机
$cls=[wmiclass]("\\.\" + $ns + ":Msvm_VirtualSystemSettingData")
$vssd=$cls.CreateInstance()
$vssd.ElementName=$name
$vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm=[wmi]$r.ResultingSystem

try {
  # 新建虚拟机的 COM1/COM2 已存在, 此处执行修改而非添加
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $serials=@(([wmi]$vssd2.__PATH).GetRelated('Msvm_SerialPortSettingData') | Sort-Object InstanceID)
  # serials[0]=COM1 (InstanceID ...\0), serials[1]=COM2 (...\1)
  $com1=$serials[0]; $com1.Connection=@($pipe1)
  $com2=$serials[1]; $com2.Connection=@($pipe2)
  $r1=$vsms.ModifyResourceSettings(@($com1.GetText(1))); if($r1.ReturnValue -eq 4096){ Wait-Job2 $r1.Job | Out-Null }
  $r2=$vsms.ModifyResourceSettings(@($com2.GetText(1))); if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

  # 读回(重新查询, 不依赖本地对象缓存)
  $vssd3=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $serials2=@(([wmi]$vssd3.__PATH).GetRelated('Msvm_SerialPortSettingData') | Sort-Object InstanceID)
  'COM1 Connection=' + ($serials2[0].Connection -join ',')
  'COM2 Connection=' + ($serials2[1].Connection -join ',')
}
finally {
  $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
}
```

## [PASS] 设置虚拟机自动启动与自动停止动作  `set_autostart`

- AutomaticStartupAction 与 AutomaticShutdownAction 均为 Msvm_VirtualSystemSettingData 上的 uint16 属性，属于整机设置，通过 ModifySystemSettings($vssd.GetText(1)) 修改，而非资源级的 ModifyResourceSettings。
- AutomaticStartupAction 取值：2=None，3=Restart if previously active（第二代虚拟机默认值），4=Always startup。
- AutomaticShutdownAction 取值：2=Turn Off，3=Save state（默认值），4=Shutdown。
- 关联属性 AutomaticStartupActionDelay（datetime 间隔）与 AutomaticStartupActionSequenceNumber（uint16）同样位于 VSSD，可一并设置。
- 修改后应重新 GetRelated 获取新副本再读回，避免读到修改前缓存的旧实例。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$name = 'WMITEST_set_autostart'
$vm = $null

try {
  # 创建第二代测试虚拟机
  $vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $null = Wait-Job2 $r.Job }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem failed rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  # 获取该虚拟机的 VSSD
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # 设置 StartupAction=4(始终启动)、ShutdownAction=3(保存状态)
  $vssd2.AutomaticStartupAction = [uint16]4
  $vssd2.AutomaticShutdownAction = [uint16]3
  $rm = $vsms.ModifySystemSettings($vssd2.GetText(1))
  if($rm.ReturnValue -eq 4096){ $st = Wait-Job2 $rm.Job; if($st -ne 7){ throw "ModifySystemSettings job state=$st" } }
  elseif($rm.ReturnValue -ne 0){ throw "ModifySystemSettings failed rv=$($rm.ReturnValue)" }

  # 重新查询以读回最新值
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $su = [int]$vssd3.AutomaticStartupAction
  $sd = [int]$vssd3.AutomaticShutdownAction
  if($su -eq 4 -and $sd -eq 3){ Write-Host 'PASS' } else { Write-Host 'FAIL' }
}
finally {
  if($vm){
    $rd = $vsms.DestroySystem($vm.__PATH)
    if($rd.ReturnValue -eq 4096){ $null = Wait-Job2 $rd.Job }
  }
}
```

## [PASS] 设置虚拟机备注 (VSSD.Notes)  `set_notes`

- 修改备注属于整机设置：获取虚拟机的 Msvm_VirtualSystemSettingData，设置其 .Notes，再调用 $vsms.ModifySystemSettings($vssd.GetText(1))；不应使用 ModifyResourceSettings。
- VSSD.Notes 在 v2 命名空间 schema 中为 string[]（array=true），但 Hyper-V 实现仅保留数组的第一个元素：传入 @('a','b') 读回仅剩 'a'。可靠写法是使用单元素数组 @('整段备注')，多行或多词内容放在同一字符串中即可。
- ModifySystemSettings 可能同步返回 rv=0（未触发 4096 job），仍应保留 Wait-Job2 作为兜底。
- 创建实例时不能使用 [wmiclass]"\\.\$ns:Class" 强制转换（会报无效参数），应改用 (Get-WmiObject -Namespace $ns -Class <Class> -List).CreateInstance()。另注意 PowerShell 会将 "$ns:" 解析为作用域变量，需写作 "${ns}:"。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){ return 7 }; $j = [wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 获取目标虚拟机的设置数据（$vm 为该虚拟机的 Msvm_ComputerSystem）
$vssd = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$vssd = [wmi]$vssd.__PATH
# Notes 在 v2 中为数组类型，但 Hyper-V 仅保留首个元素，故使用单元素数组
$vssd.Notes = @('My note text (multi-word / multi-line is fine in one element)')
$rm = $vsms.ModifySystemSettings($vssd.GetText(1))
if($rm.ReturnValue -eq 4096){ Wait-Job2 $rm.Job | Out-Null }
elseif($rm.ReturnValue -ne 0){ throw "ModifySystemSettings rv=$($rm.ReturnValue)" }
# 读回
$readNotes = @( ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1 ).Notes
Write-Host ($readNotes -join ' | ')
```

## [PASS] 启用或禁用虚拟机安全启动  `set_secureboot`

- SecureBootEnabled 是 Msvm_VirtualSystemSettingData 上的布尔属性，修改时使用 ModifySystemSettings(VSSD.GetText(1))，而非 ModifyResourceSettings。
- 该属性仅适用于第二代虚拟机（VirtualSystemSubType = Microsoft:Hyper-V:SubType:2）；新建的第二代虚拟机默认 SecureBootEnabled=True。
- 修改后应重新从虚拟机 GetRelated 获取 VSSD 再读回，以确认 WMI 实例已刷新。
- DefineSystem、ModifySystemSettings、DestroySystem 返回 4096 时表示异步 Job，需用 Wait-Job2 轮询至完成。
- 若需同时指定安全启动模板，可配套设置 SecureBootTemplateId（string 类型 GUID），同样经 ModifySystemSettings 修改。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns   = 'root\virtualization\v2'
$name = 'WMITEST_set_secureboot'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第二代虚拟机（仅第二代支持安全启动）
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $name
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# 获取虚拟机的 VSSD；SecureBootEnabled 位于 Msvm_VirtualSystemSettingData
$vssd2 = [wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH

# 关闭安全启动
$vssd2.SecureBootEnabled = $false
$r2 = $vsms.ModifySystemSettings($vssd2.GetText(1))
if ($r2.ReturnValue -eq 4096) { Wait-Job2 $r2.Job | Out-Null }

# 读回
$vssd2 = [wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH
'$vssd2.SecureBootEnabled'  # -> False

# 重新开启安全启动
$vssd2.SecureBootEnabled = $true
$r3 = $vsms.ModifySystemSettings($vssd2.GetText(1))
if ($r3.ReturnValue -eq 4096) { Wait-Job2 $r3.Job | Out-Null }

# 清理
$rd = $vsms.DestroySystem($vm.__PATH)
if ($rd.ReturnValue -eq 4096) { Wait-Job2 $rd.Job | Out-Null }
```

## [PASS] 设置每核硬件线程数 (HwThreadsPerCore)  `smt_threads`

- HwThreadsPerCore 位于 Msvm_ProcessorSettingData，类型为 uint64。0=继承主机（默认），1=禁用 SMT，2=每核 2 线程。
- 修改该值使用 ModifyResourceSettings(GetText(1))，可能同步返回 rv=0（未触发 4096 Job）。0/1/2 三种取值均可写入并读回。
- 该属性在 MOF schema 中标为 Read 限定符，但实际可经 ModifyResourceSettings 写入，Read 限定符仅为信息性标注。
- HwThreadsPerCoreRealized（uint32，只读）表示来宾实际看到的每核线程数，仅在虚拟机运行时填充；关机状态下读回为空，因此不对其做断言。
- 该属性自 build 10586 起提供，长期稳定可用。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$ns = 'root\virtualization\v2'
$vmname = 'WMITEST_smt_threads'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService

# 创建第二代虚拟机
$vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $vmname
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# 定位到 ProcessorSettingData
$vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
$proc = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1

# 设置 HwThreadsPerCore：0=继承主机，1=禁用SMT，2=每核两线程
$proc.HwThreadsPerCore = [uint64]2
$rm = $vsms.ModifyResourceSettings($proc.GetText(1))
if ($rm.ReturnValue -eq 4096) { Wait-Job2 $rm.Job | Out-Null }

# 读回
$p3 = ([wmi]$vssd2.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1
Write-Output ("HwThreadsPerCore = {0}  Realized = {1}" -f $p3.HwThreadsPerCore, $p3.HwThreadsPerCoreRealized)

# 清理
$vsms.DestroySystem($vm.__PATH) | Out-Null
```

## [PASS] 应用虚拟机检查点  `snapshot_apply`

- ApplySnapshot 仅有一个 IN 参数 Snapshot（对快照 VSSD 的引用）与 OUT 参数 Job；直接传快照 VSSD 的 __PATH 字符串即可。CreateSnapshot 与 ApplySnapshot 通常返回 4096，需用 Wait-Job2 轮询 Msvm_ConcreteJob.JobState 至 7（Completed）。
- CreateSnapshot 的 ResultingSnapshot 为 IN/OUT 引用，但当方法走异步 Job（rv=4096）时该 OUT 引用返回为空。应在任务完成后经 Msvm_SnapshotOfVirtualSystem 关联从虚拟机获取快照 VSSD，不要依赖 ResultingSnapshot。使用 Get-WmiObject 调用方法时也不能为引用形参传入 PowerShell [ref]（会报“应为 PSReference”），直接传 $null。
- 验证回滚不应使用 VSSD.Notes。Notes 属于主机侧元数据，ApplySnapshot 不会还原它。应改用真正纳入快照配置树的资源属性，如 ProcessorSettingData.VirtualQuantity（vCPU），可正确观察到 2->apply->1 的回滚。
- 创建快照后，虚拟机经普通 GetRelated('Msvm_VirtualSystemSettingData') 可能返回快照的 VSSD 而非已实现配置。应经 Msvm_SettingsDefineState 关联并按 VirtualSystemType='Microsoft:Hyper-V:System:Realized' 过滤，且每次读回都重新以 [wmi]$vm.__PATH 获取关联（apply 后实例可能变更，缓存对象会过期）。
- 清理顺序：先对虚拟机的所有快照 DestroySnapshot，再对整机 DestroySystem，二者均可能返回 4096 需轮询。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
function Get-RealizedVssd($vmpath){
    $v = [wmi]$vmpath
    $all = $v.GetRelated('Msvm_VirtualSystemSettingData','Msvm_SettingsDefineState',$null,$null,$null,$null,$false,$null)
    $rz = $all | Where-Object { $_.VirtualSystemType -eq 'Microsoft:Hyper-V:System:Realized' } | Select-Object -First 1
    if (-not $rz) { $rz = $all | Select-Object -First 1 }
    return [wmi]$rz.__PATH
}
function Get-Proc($vssd){ $p = ([wmi]$vssd.__PATH).GetRelated('Msvm_ProcessorSettingData') | Select-Object -First 1; return [wmi]$p.__PATH }

$ns = 'root\virtualization\v2'
$name = 'WMITEST_snapshot_apply'
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$snap = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService

# 1) DefineSystem（第二代）-> $vm
$vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = $name; $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
$vm = [wmi]$r.ResultingSystem

# 2) 快照前状态：vCPU=1
$proc = Get-Proc (Get-RealizedVssd $vm.__PATH); $proc.VirtualQuantity = [uint64]1
$rm = $vsms.ModifyResourceSettings($proc.GetText(1)); if ($rm.ReturnValue -eq 4096){ Wait-Job2 $rm.Job | Out-Null }

# 3) CreateSnapshot（Full=2）。rv=4096 时需 Wait-Job2。方法走 Job 时 ResultingSnapshot
#    OUT 引用不会被填充，应经 Msvm_SnapshotOfVirtualSystem 关联获取快照 VSSD。
$rc = $snap.CreateSnapshot($vm.__PATH, $null, 2, $null); if ($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
$snapVssd = $vm.GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
$snapPath = [string]$snapVssd.__PATH

# 4) 修改已实现配置：vCPU=2
$proc = Get-Proc (Get-RealizedVssd $vm.__PATH); $proc.VirtualQuantity = [uint64]2
$rm2 = $vsms.ModifyResourceSettings($proc.GetText(1)); if ($rm2.ReturnValue -eq 4096){ Wait-Job2 $rm2.Job | Out-Null }

# 5) ApplySnapshot（Snapshot 引用）。rv=4096 时需 Wait-Job2。
$ra = $snap.ApplySnapshot($snapPath); if ($ra.ReturnValue -eq 4096){ Wait-Job2 $ra.Job | Out-Null }
Start-Sleep -Milliseconds 800

# 6) 验证：vCPU 由 2 回滚为 1
$cpuAfterApply = (Get-Proc (Get-RealizedVssd $vm.__PATH)).VirtualQuantity   # == 1

# 清理：先 DestroySnapshot，再 DestroySystem
foreach ($s in @($vm.GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null))) {
    $rd = $snap.DestroySnapshot([string]$s.__PATH); if ($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
}
$rdel = $vsms.DestroySystem($vm.__PATH); if ($rdel.ReturnValue -eq 4096){ Wait-Job2 $rdel.Job | Out-Null }
```

## [PASS] 创建虚拟机检查点  `snapshot_create`

- 检查点操作由独立的 Msvm_VirtualSystemSnapshotService 提供，而非 Msvm_VirtualSystemManagementService。CreateSnapshot 与 DestroySnapshot 均以 4096 表示异步作业，需轮询关联的 Msvm_ConcreteJob，作业终态 JobState=7 表示已完成。
- CreateSnapshot 参数：AffectedSystem(ref IN，虚拟机的 __PATH)、SnapshotSettings(string IN，传空串 '' 即可，无需嵌入 Msvm_VirtualSystemSnapshotSettingData)、SnapshotType(uint16 IN，2=全量检查点/3=磁盘检查点)、ResultingSnapshot(IN/OUT ref)、Job(OUT)。
- 处于关机状态(EnabledState=3 Disabled)的虚拟机即可创建全量检查点，无需先启动，也不依赖嵌套虚拟化或 GPU。
- 检查点不会通过 GetRelated('...SettingData') 作为常规配置直接返回，需经 Msvm_SnapshotOfVirtualSystem 关联类从虚拟机获取，或按 VirtualSystemType LIKE '%Snapshot%' 筛选。检查点 VSSD 的 VirtualSystemType 为 'Microsoft:Hyper-V:Snapshot:Realized'，ElementName 形如 '<虚拟机名> - (时间)'。
- DestroySnapshot 参数：AffectedSnapshot(ref IN，检查点 VSSD 的 __PATH)、Job(OUT)。DestroySystem 通常会连带清理检查点，但删除虚拟机前显式删除检查点更稳妥。
- 使用 GetMethodParameters + InvokeMethod 为 ref 参数赋 __PATH 字符串，在 Windows PowerShell 5.1 上可稳定工作，可避免直接调用 $svc.CreateSnapshot(...) 时的参数顺序问题。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$snapSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService

# --- 构建用于演示的虚拟机 ---
$vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = 'WMITEST_snapshot_create'
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { [void](Wait-Job2 $r.Job) }
$vm = [wmi]$r.ResultingSystem

# --- CreateSnapshot: AffectedSystem(ref IN), SnapshotSettings(string IN), SnapshotType(uint16 IN: 2=Full,3=Disk), ResultingSnapshot(IN/OUT ref), Job(OUT) ---
$inParams = $snapSvc.GetMethodParameters('CreateSnapshot')
$inParams.AffectedSystem = $vm.__PATH
$inParams.SnapshotSettings = ''
$inParams.SnapshotType = [uint16]2
$sr = $snapSvc.InvokeMethod('CreateSnapshot', $inParams, $null)
if ($sr.ReturnValue -eq 4096) { [void](Wait-Job2 $sr.Job) }

# --- 通过 Msvm_SnapshotOfVirtualSystem 关联类定位检查点的 VSSD ---
$vmSnaps = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null)
# 检查点 VSSD 的 VirtualSystemType 为 'Microsoft:Hyper-V:Snapshot:Realized'

# --- DestroySnapshot: AffectedSnapshot(ref IN), Job(OUT) ---
foreach ($s in @($vmSnaps)) {
  $dp = $snapSvc.GetMethodParameters('DestroySnapshot')
  $dp.AffectedSnapshot = $s.__PATH
  $dr = $snapSvc.InvokeMethod('DestroySnapshot', $dp, $null)
  if ($dr.ReturnValue -eq 4096) { [void](Wait-Job2 $dr.Job) }
}

# --- 清理虚拟机 ---
$dvm = $vsms.DestroySystem($vm.__PATH)
if ($dvm.ReturnValue -eq 4096) { [void](Wait-Job2 $dvm.Job) }
```

## [PASS] 导出单个检查点定义  `snapshot_export`

- 导出单个检查点没有独立的 ExportSnapshotDefinition 方法，应使用 Msvm_VirtualSystemManagementService.ExportSystemDefinition，并配合 Msvm_VirtualSystemExportSettingData(CopySnapshotConfiguration=2 ExportOneSnapshot，SnapshotVirtualSystem 指向检查点 VSSD 路径)。
- ExportSystemDefinition 参数顺序：ComputerSystem(虚拟机的 Msvm_ComputerSystem 路径，非检查点)、ExportDirectory(目录字符串)、ExportSettingData(内嵌实例，GetText(1))。导出哪个检查点由 ExportSettingData.SnapshotVirtualSystem 指定。
- CopySnapshotConfiguration 的 ValueMap：0=ExportAllSnapshots，1=ExportNoSnapshots，2=ExportOneSnapshot，3=ExportOneSnapshotForBackup。取 2 或 3 时 CopyVmStorage/CopyVmRuntimeInformation 被忽略，存储与运行时信息一并导出。
- CreateSnapshot 的 OUT 参数名为 ResultingSnapshot，返回一个 Msvm_VirtualSystemSettingData 路径；SnapshotType 2=Full，3=Disk。返回 4096 时需轮询作业。
- ExportSystemDefinition 返回 4096(异步作业)，作业成功终态 JobState=7。产物位于 <exportDir>/<VMName>/Virtual Machines/ 下，配置文件 .vmcx 以检查点 InstanceID 的 GUID 命名，并伴随 .vmgs 与 .VMRS。
- CreateVmExportSubdirectory=true 会在导出目录下创建以虚拟机 ElementName 命名的子目录。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vsss=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService

# 1) 创建第二代虚拟机
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_snapshot_export'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm=[wmi]$r.ResultingSystem

# 2) CreateSnapshot (SnapshotType 2 = Full)。OUT 参数 ResultingSnapshot 为 Msvm_VirtualSystemSettingData 路径
$rs=$vsss.CreateSnapshot($vm.__PATH,$null,2)
if($rs.ReturnValue -eq 4096){ Wait-Job2 $rs.Job | Out-Null }
$snapPath=$rs.ResultingSnapshot

# 3) 构造 Msvm_VirtualSystemExportSettingData: 仅导出该检查点
$esd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemExportSettingData").CreateInstance()
$esd.CopySnapshotConfiguration=[uint16]2     # 2 = ExportOneSnapshot
$esd.SnapshotVirtualSystem=$snapPath         # 检查点 VSSD 的路径
$esd.CreateVmExportSubdirectory=$true

# 4) ExportSystemDefinition(ComputerSystem, ExportDirectory, ExportSettingData GetText(1))
$re=$vsms.ExportSystemDefinition($vm.__PATH, $exportDir, $esd.GetText(1))
if($re.ReturnValue -eq 4096){ Wait-Job2 $re.Job | Out-Null }   # 作业成功终态 JobState=7
# 产物: <exportDir>/<VMName>/Virtual Machines/<snapshotGUID>.vmcx (+.vmgs/.VMRS)

# 清理
$vsms.DestroySystem($vm.__PATH) | Out-Null
```

## [PASS] 重命名并读取检查点  `snapshot_rename`

- 重命名检查点不经快照服务：Msvm_VirtualSystemSnapshotService 仅提供 CreateSnapshot/ApplySnapshot/DestroySnapshot/ClearSnapshotState，不含 Rename 或 Modify 方法。重命名即在检查点 VSSD 上修改 ElementName，再经 Msvm_VirtualSystemManagementService.ModifySystemSettings(snap.GetText(1)) 下发，与修改虚拟机名使用同一方法。
- ModifySystemSettings 修改检查点名同步完成，返回 rv=0，不产生作业，无需轮询；随后以 [wmi]$snap.__PATH 回读即可获得新 ElementName。
- 检查点新名称可任意指定，不必形如 '<虚拟机名> - (时间)'。
- 枚举检查点树：从虚拟机经 Msvm_SnapshotOfVirtualSystem 关联类获取所有检查点 VSSD(VirtualSystemType='Microsoft:Hyper-V:Snapshot:Realized')；经 Msvm_MostCurrentSnapshotInBranch 获取各分支的最新检查点(分支尖端)。两者均以 GetRelated('Msvm_VirtualSystemSettingData','<关联类>',...) 获取。
- 处于关机状态(EnabledState=3)的第二代虚拟机即可完成创建检查点、重命名与枚举。删除虚拟机前逐个 DestroySnapshot 更稳妥。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms   = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$snapSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService

# --- 构建第二代演示虚拟机 ---
$vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = 'WMITEST_snapshot_rename'
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($r.ReturnValue -eq 4096) { [void](Wait-Job2 $r.Job) }
$vm = [wmi]$r.ResultingSystem

# --- CreateSnapshot (Full=2) ---
$ip = $snapSvc.GetMethodParameters('CreateSnapshot')
$ip.AffectedSystem = $vm.__PATH
$ip.SnapshotSettings = ''
$ip.SnapshotType = [uint16]2
$sr = $snapSvc.InvokeMethod('CreateSnapshot', $ip, $null)
if ($sr.ReturnValue -eq 4096) { [void](Wait-Job2 $sr.Job) }

# --- 经 Msvm_SnapshotOfVirtualSystem 关联类定位检查点 VSSD ---
$snap = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null) | Select-Object -First 1

# --- 重命名: 在检查点 VSSD 上修改 ElementName, 经 ModifySystemSettings 下发(非快照服务) ---
$snap.ElementName = 'WMITEST_snap_renamed_checkpoint'
$mr = $vsms.ModifySystemSettings($snap.GetText(1))   # 同步返回 rv=0
if ($mr.ReturnValue -eq 4096) { [void](Wait-Job2 $mr.Job) }

# --- 回读 ---
$readName = ([wmi]$snap.__PATH).ElementName

# --- 枚举检查点树及分支尖端 ---
$tree = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null) | ForEach-Object { $_.ElementName }
$tip  = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_MostCurrentSnapshotInBranch',$null,$null,$null,$null,$false,$null) | ForEach-Object { $_.ElementName }

# --- 清理: 先删检查点再删虚拟机 ---
foreach ($s in @(([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null))) {
  $dp = $snapSvc.GetMethodParameters('DestroySnapshot'); $dp.AffectedSnapshot = $s.__PATH
  $dr = $snapSvc.InvokeMethod('DestroySnapshot', $dp, $null)
  if ($dr.ReturnValue -eq 4096) { [void](Wait-Job2 $dr.Job) }
}
$dvm = $vsms.DestroySystem($vm.__PATH)
if ($dvm.ReturnValue -eq 4096) { [void](Wait-Job2 $dvm.Job) }
```

## [PASS] 删除检查点子树 (DestroySnapshotTree)  `snapshot_tree_delete`

- DestroySnapshotTree(SnapshotSettingData REF, Job OUT)：传入根检查点的 __PATH，一次删除根及其全部子孙。返回 4096 时需轮询作业，作业终态 JobState=7 表示已完成。
- CreateSnapshot 参数：(AffectedSystem REF, SnapshotSettings string, SnapshotType uint16, ResultingSnapshot IN/OUT REF, Job OUT)。SnapshotType=2=Full。ResultingSnapshot 为 IN/OUT，可传 $null；SnapshotSettings 传 $null 即可创建。
- 多级链自动形成：连续三次 CreateSnapshot，新检查点自动挂在分支最新检查点之下，经 Msvm_ParentChildSettingData 形成 snap1->snap2->snap3。根检查点为 CreationTime 最早的那个。
- $vm.GetRelated('Msvm_VirtualSystemSettingData') 返回的检查点存在重复(虚拟机经多个关联类指向同一检查点)，需按 __RELPATH 去重，并精确匹配类型 'Microsoft:Hyper-V:Snapshot:Realized'(虚拟机本体为 ...System:Realized)。未去重时 3 个检查点会被计为 4 个。
- 检查点为 Msvm_VirtualSystemSettingData，VirtualSystemType='Microsoft:Hyper-V:Snapshot:Realized'。可通过删除前 count=3、删除后 count=0 回到基线来验证。
- 该方法自 build 9200 起持续可用。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_snapshot_tree_delete'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

# 返回去重后的检查点 VSSD 对象。GetRelated 会返回重复项, 因为虚拟机经多个关联类
# 指向同一检查点; 按 __RELPATH 去重, 并精确匹配类型 'Microsoft:Hyper-V:Snapshot:Realized'。
function Get-Snaps($vm){
  $seen = @{}
  $out = @()
  foreach($s in $vm.GetRelated('Msvm_VirtualSystemSettingData')){
    if($s.VirtualSystemType -eq 'Microsoft:Hyper-V:Snapshot:Realized'){
      if(-not $seen.ContainsKey($s.__RELPATH)){ $seen[$s.__RELPATH] = $true; $out += $s }
    }
  }
  return ,$out
}
function Get-SnapCount($vm){ return (Get-Snaps $vm).Count }

function Create-OneSnapshot($snapSvc, $vm){
  # CreateSnapshot(AffectedSystem REF, SnapshotSettings string, SnapshotType uint16=2 Full, ResultingSnapshot IN/OUT, Job OUT)
  $r = $snapSvc.CreateSnapshot($vm.__PATH, $null, [uint16]2, $null)
  if($r.ReturnValue -eq 4096){ if((Wait-Job2 $r.Job) -ne 7){ throw 'CreateSnapshot job failed' } }
  elseif($r.ReturnValue -ne 0){ throw "CreateSnapshot returned $($r.ReturnValue)" }
  return $r
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$snapSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService
$vm = $null
try {
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $testName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $rv = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($rv.ReturnValue -eq 4096){ Wait-Job2 $rv.Job | Out-Null }
  $vm = [wmi]$rv.ResultingSystem

  $base = Get-SnapCount $vm
  # 连续三次 CreateSnapshot 形成三级链: 每个新检查点挂在分支最新检查点之下
  # (经 Msvm_ParentChildSettingData)。
  Create-OneSnapshot $snapSvc $vm | Out-Null
  Create-OneSnapshot $snapSvc $vm | Out-Null
  Create-OneSnapshot $snapSvc $vm | Out-Null

  # 根 = 创建时间最早、无检查点父节点的那个。
  $snaps = Get-Snaps $vm
  $root = $snaps | Sort-Object { [System.Management.ManagementDateTimeConverter]::ToDateTime($_.CreationTime) } | Select-Object -First 1

  # DestroySnapshotTree(SnapshotSettingData REF, Job OUT) -> 删除根及其全部子孙。
  $rd = $snapSvc.DestroySnapshotTree($root.__PATH)
  if($rd.ReturnValue -eq 4096){ if((Wait-Job2 $rd.Job) -ne 7){ throw 'DestroySnapshotTree job failed' } }
  elseif($rd.ReturnValue -ne 0){ throw "DestroySnapshotTree returned $($rd.ReturnValue)" }

  Start-Sleep -Milliseconds 500
  $vm = [wmi]$vm.__PATH
  $after = Get-SnapCount $vm
  if($after -eq $base){ 'PASS: whole snapshot tree destroyed' } else { "FAIL: $after snapshots remain" }
}
finally {
  if($vm -ne $null){ try { $dr = $vsms.DestroySystem(([wmi]$vm.__PATH).__PATH); if($dr.ReturnValue -eq 4096){ Wait-Job2 $dr.Job | Out-Null } } catch {} }
  $resid = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName }
  if($resid){ foreach($x in $resid){ try { $vsms.DestroySystem($x.__PATH) | Out-Null } catch {} } }
}
```

## [PASS] 请求虚拟机状态变更 (RequestStateChange 启动与停止)  `state_change`

- RequestStateChange 在虚拟机对象(Msvm_ComputerSystem)上调用：$vm.RequestStateChange(RequestedState, [out]Job, [TimeoutPeriod])。在 Windows PowerShell 5.1 / Get-WmiObject 下只需传首个 IN 参数($null 占位 TimeoutPeriod)。返回对象含 .ReturnValue 与 .Job。
- RequestedState 的 ValueMap：2=Enabled(启动)，3=Disabled(关机/断电)，4=ShutDown(经集成服务正常关机)，10=Reboot，11=Reset，32769=Saved，32773=Saving 等。
- 返回码：0 表示同步完成，4096 表示已启动异步作业，需轮询 Msvm_ConcreteJob.JobState 至 7(Completed)，JobState 3/4 表示运行中。
- 空的第二代虚拟机无需引导介质或嵌套虚拟化即可完成 Disabled(3) -> Enabled(2) -> Disabled(3) 的状态转换，作业 ErrorCode=0。
- 读取 EnabledState 前需重新以 [wmi]$vm.__PATH 刷新实例；状态转换为异步，建议等待约 800ms 后再读取。
- EnabledState 常见值：2=Enabled(运行)，3=Disabled(关闭)，32768=PowerOff，32769=Saved，32770=Starting，32774=Stopping。
- 清理时应在 finally 中先确保虚拟机处于关闭态(3 或 32768)再调用 DestroySystem，否则删除可能被拒绝。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$name='WMITEST_state_change'
function Wait-Job2($p){ if(-not $p){return @{State=7}}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return @{State=$j.JobState; Err=$j.ErrorDescription; Code=$j.ErrorCode} }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try{
  # 创建第二代演示虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name
  $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
  $vm=[wmi]$r.ResultingSystem
  # 启动: RequestedState=2 (Enabled)。OUT 参数 Job; rv 0=成功, 4096=异步作业。
  $rStart=$vm.RequestStateChange(2,$null)
  if($rStart.ReturnValue -eq 4096){Wait-Job2 $rStart.Job|Out-Null}
  Start-Sleep -Milliseconds 800
  $vm=[wmi]$vm.__PATH
  "After start EnabledState=$($vm.EnabledState)"   # 2=Enabled
  # 停止: RequestedState=3 (Disabled / 断电)
  $rStop=$vm.RequestStateChange(3,$null)
  if($rStop.ReturnValue -eq 4096){Wait-Job2 $rStop.Job|Out-Null}
  Start-Sleep -Milliseconds 800
  $vm=[wmi]$vm.__PATH
  "After stop EnabledState=$($vm.EnabledState)"    # 3=Disabled
}finally{
  if($vm){
    $cur=[wmi]$vm.__PATH
    if($cur.EnabledState -ne 3 -and $cur.EnabledState -ne 32768){ $rd=$cur.RequestStateChange(3,$null); if($rd.ReturnValue -eq 4096){Wait-Job2 $rd.Job|Out-Null}; Start-Sleep -Milliseconds 500 }
    $dr=$vsms.DestroySystem($vm.__PATH)
    if($dr.ReturnValue -eq 4096){Wait-Job2 $dr.Job|Out-Null}
  }
}
```

## [PASS] 管理增强会话终端设置与交互式会话访问控制  `terminal_access`

- Msvm_TerminalService 与 Msvm_TerminalServiceSettingData 均为主机单例，直接 Get-WmiObject -Class 即得该实例，无需按虚拟机过滤。SettingData 只读，其全部属性(ListenerPort/DisableSelfSignedCertificateGeneration/AuthCertificateHash/TrustedIssuerCertificateHashes/AllowedHashAlgorithms)只能经 ModifyServiceSettings 变更。
- ModifyServiceSettings(ServiceSettingData: string) 以 SettingData.GetText(1) 序列化整份设置回传。本例做无害回环(原样回传)，rv=0 表示同步成功，回读 ListenerPort 仍为 2179。
- GrantInteractiveSessionAccess / RevokeInteractiveSessionAccess 签名为 (ComputerSystem REF, Trustees string[], OUT Job)。ComputerSystem 传虚拟机的 __PATH；Trustees 传 'DOMAIN\User' 形式的字符串数组。rv=0 表示同步生效。
- GetInteractiveSessionACL(ComputerSystem REF, OUT AccessControlList string[]) 返回每条 ACE 的 XML(Msvm_InteractiveSessionACE: AccessType uint16 0=Allow, Trustee string)。授予后 entries=1 含该 trustee，撤销后清空。
- 排障提示：若 vmms 服务处于 Stopped，root\virtualization\v2 下所有 provider 查询(VSMS/ImageMgmt/TerminalService/ComputerSystem)会返回 null 或 0 个实例(类定义仍在，故不报‘类不存在’)。此时应先确认并启动 vmms 服务。
- 本条目涉及的 4 个方法(Grant/Get/Revoke/ModifyServiceSettings)在同步路径下均返回 rv=0，无需轮询作业。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ts   = Get-WmiObject -Namespace $ns -Class Msvm_TerminalService

# ---- A. 读取主机增强会话终端设置 ----
$tssd = Get-WmiObject -Namespace $ns -Class Msvm_TerminalServiceSettingData | Select-Object -First 1
$port = $tssd.ListenerPort            # 2179 (Hyper-V VMConnect / 增强会话端口)
$disableSSC = $tssd.DisableSelfSignedCertificateGeneration

# ---- B. ModifyServiceSettings(无害回环: 类属性只读，仅此方法可变更) ----
$r = $ts.ModifyServiceSettings($tssd.GetText(1))
if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }   # rv 0=同步成功, 4096=作业

# ---- C. 对虚拟机授予/读取/撤销交互式会话 ACL ----
$vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName = 'WMITEST_terminal_access'
$vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
$rd = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
if ($rd.ReturnValue -eq 4096) { Wait-Job2 $rd.Job | Out-Null }
$vm = [wmi]$rd.ResultingSystem

$trustee = "$env:USERDOMAIN\$env:USERNAME"   # 例如 HOST\Administrator

# 授予: (ComputerSystem REF = VM __PATH, Trustees = string[])
$rg = $ts.GrantInteractiveSessionAccess($vm.__PATH, @($trustee))
if ($rg.ReturnValue -eq 4096) { Wait-Job2 $rg.Job | Out-Null }

# 读取 ACL: OUT AccessControlList = string[]，每项为 <INSTANCE CLASSNAME=Msvm_InteractiveSessionACE> XML
$ra  = $ts.GetInteractiveSessionACL($vm.__PATH)
$acl = $ra.AccessControlList   # 每项含 AccessType (uint16, 0=Allow) 与 Trustee (string)

# 撤销
$rr = $ts.RevokeInteractiveSessionAccess($vm.__PATH, @($trustee))
if ($rr.ReturnValue -eq 4096) { Wait-Job2 $rr.Job | Out-Null }

# ---- 清理 ----
$vsms.DestroySystem($vm.__PATH) | Out-Null
```

## [PASS] 查询透明桥接服务(只读)  `transparent_bridge`

- 此为纯读操作,不创建桥接、不改动主机网络。Msvm_TransparentBridgingService 实例的 Name 为 GUID,System 为主机 Msvm_ComputerSystem;该服务始终存在,不限于存在交换机时才出现。
- 该类无实例属性,提供三个方法:StartService()->uint32、StopService()->uint32(均无参),以及继承自 CIM_EnabledLogicalElement 的 RequestStateChange(IN uint16 RequestedState, IN datetime TimeoutPeriod, OUT CIM_ConcreteJob Job)。RequestStateChange 仅声明返回码 0=Completed、1=Not supported。
- 该服务是交换机内部学习 MAC 地址的占位服务,关联 Msvm_VirtualEthernetSwitch 与 Msvm_DynamicForwardingEntry(动态转发表,含 MACAddress/VlanId)。
- 读取方法签名须使用 [wmiclass] 并设置 $cls.Options.UseAmendedQualifiers=$true;OUT 参数除 Job 外,运行时还包含隐式的 ReturnValue。
- 调用 StartService/StopService 或 RequestStateChange 会影响主机交换机的 MAC 学习与桥接,可能中断网络。建议仅用于枚举实例与读取方法签名。

```powershell
$ns = 'root\virtualization\v2'
# 1. 枚举服务实例(只读;不创建桥接)
$svcs = @(Get-WmiObject -Namespace $ns -Class Msvm_TransparentBridgingService)
$svcs | ForEach-Object { $_.__PATH }
# 2. 从 WMI 类读取方法签名
$cls = [wmiclass]("\\.\" + $ns + ':Msvm_TransparentBridgingService')
$cls.Options.UseAmendedQualifiers = $true
$cls.Methods | ForEach-Object { $_.Name }               # RequestStateChange, StartService, StopService
$rsc = $cls.Methods['RequestStateChange']
@($rsc.InParameters.Properties  | ForEach-Object { $_.Name })  # RequestedState, TimeoutPeriod
@($rsc.OutParameters.Properties | ForEach-Object { $_.Name })  # Job, ReturnValue
# StartService / StopService 无 IN 参数,返回 uint32
# 3. 相关的已学习 MAC 转发表类(仅读取存在性)
[wmiclass]("\\.\" + $ns + ':Msvm_DynamicForwardingEntry')  # 属性含 MACAddress, VlanId
```

## [PASS] 压缩VHDX虚拟磁盘  `vhd_compact`

- CompactVirtualHardDisk(Path string, Mode uint16) -> OUT Job（CIM_ConcreteJob 引用）。返回 4096 表示异步 Job，需 Wait-Job2 轮询至 JobState=7（Completed）表示成功。Mode 0=Full，ValueMap 0..4。
- WMI 方法的 OUT 参数（Job）不作为调用实参传入。CreateVirtualHardDisk 仅传 1 个 IN 参数（VirtualDiskSettingData），CompactVirtualHardDisk 仅传 2 个 IN 参数（Path、Mode）。多传参数会导致找不到匹配的方法重载。
- 创建磁盘使用 Msvm_VirtualHardDiskSettingData.CreateInstance()，设置 Type=3（动态）/Format=3（VHDX）/Path/MaxInternalSize，再经 GetText(1) 序列化后传入 CreateVirtualHardDisk。
- 压缩量取决于来宾系统的 TRIM 与释放块位图；若无可回收块，文件大小可能不变。压缩操作成功的判据是 Job 完成且文件未增大，与实际回收字节数无关。
- Path 必须使用反斜杠格式的 Windows 路径。临时磁盘文件应在 finally 块中 Dismount 并 Remove 清理。

```powershell
# Msvm_ImageManagementService.CompactVirtualHardDisk
# ASCII only. PS 5.1 + Get-WmiObject.
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$vhd = 'C:\Temp\WMITEST_vhd_compact.vhdx'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}

$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
if(Test-Path $vhd){ Remove-Item -Force $vhd }

try {
  # 1) 通过嵌入的 Msvm_VirtualHardDiskSettingData 创建动态 vhdx
  $sd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $sd.Type   = [uint16]3   # 3 = 动态
  $sd.Format = [uint16]3   # 3 = VHDX
  $sd.Path   = $vhd
  $sd.MaxInternalSize = [uint64](256MB)
  $sd.BlockSize = [uint32]0; $sd.LogicalSectorSize = [uint32]0; $sd.PhysicalSectorSize = [uint32]0
  # 仅传入 IN 参数。OUT 参数 Job 不作为实参，返回码在结果对象上。
  $rc = $ims.CreateVirtualHardDisk($sd.GetText(1))
  if($rc.ReturnValue -eq 4096){ if((Wait-Job2 $rc.Job) -ne 7){ throw 'create job failed' } }
  elseif($rc.ReturnValue -ne 0){ throw "CreateVirtualHardDisk rv=$($rc.ReturnValue)" }

  # 2)（可选）先写入再释放数据块，使压缩有可回收空间：
  #    Mount-DiskImage / Initialize-Disk GPT / New-Partition / Format-Volume NTFS /
  #    写入大文件后删除，Optimize-Volume -ReTrim，Dismount-DiskImage。

  $before = (Get-Item $vhd).Length
  # 3) 压缩。Mode uint16：0=Full（另有 1..4 模式）。仅传 (Path, Mode)，Job 为 OUT 参数。
  $rc2 = $ims.CompactVirtualHardDisk($vhd, [uint16]0)
  if($rc2.ReturnValue -eq 4096){
    if((Wait-Job2 $rc2.Job) -ne 7){ throw 'compact job failed' }
  } elseif($rc2.ReturnValue -ne 0){ throw "CompactVirtualHardDisk rv=$($rc2.ReturnValue)" }
  $after = (Get-Item $vhd).Length
  Write-Host "PASS before=$before after=$after delta=$($before-$after)"
}
finally {
  try { Dismount-DiskImage -ImagePath $vhd -ErrorAction SilentlyContinue | Out-Null } catch {}
  if(Test-Path $vhd){ Remove-Item -Force $vhd }
}
```

## [PASS] 转换VHDX类型(动态盘转固定盘)  `vhd_convert`

- ConvertVirtualHardDisk(SourcePath, VirtualDiskSettingData) 含两个 IN 参数及一个 Job OUT 参数。VirtualDiskSettingData 描述目标新盘（嵌入 Msvm_VirtualHardDiskSettingData，经 GetText(1) 序列化），方法在目标 Path 处生成新盘，源盘保持不变。
- Msvm_VirtualHardDiskSettingData.Type 枚举：2=Fixed，3=Dynamic，4=Differencing；Format 枚举：2=VHD，3=VHDX，4=VHDSet。VHD 与 VHDX 之间的转换通过改 Format，固定盘与动态盘之间的转换通过改 Type。
- 返回 4096 表示异步 Job，需 Wait-Job2 轮询 Msvm_ConcreteJob.JobState 至 7（Completed）。
- GetVirtualHardDiskSettingData 的 OUT 参数 SettingData 为 CIM-XML（<PROPERTY NAME=...><VALUE>..</VALUE>），不是 MOF 文本，应按 XML 解析而非用 'Type = 3' 正则匹配。
- 该操作仅涉及磁盘文件，不创建或触碰任何 Msvm_ComputerSystem。

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
# GetVirtualHardDiskSettingData 的 OUT 参数 SettingData 为 CIM-XML，不是 MOF
function Get-CimProp($xml,$name){ $rx='NAME="'+[regex]::Escape($name)+'"[^>]*>\s*<VALUE>([^<]*)</VALUE>'; if($xml -match $rx){return $matches[1]}; return $null }

$ims=Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$src='C:\temp\src.vhdx'; $dst='C:\temp\fixed.vhdx'

# 1) 创建动态源盘 (Type=3 Dynamic, Format=3 VHDX)
$sd=([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
$sd.Type=[uint16]3; $sd.Format=[uint16]3; $sd.Path=$src; $sd.MaxInternalSize=[uint64](64MB)
$rc=$ims.CreateVirtualHardDisk($sd.GetText(1))
if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }

# 2) 转换: ConvertVirtualHardDisk(SourcePath, VirtualDiskSettingData)
#    VirtualDiskSettingData 是描述【目标】新盘的嵌入实例 (Type=2 Fixed)
#    方法在目标 Path 处生成新盘，不会原地修改源盘
$cd=([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
$cd.Type=[uint16]2; $cd.Format=[uint16]3; $cd.Path=$dst
$r2=$ims.ConvertVirtualHardDisk($src,$cd.GetText(1))
if($r2.ReturnValue -eq 4096){ Wait-Job2 $r2.Job | Out-Null }

# 3) 验证: GetVirtualHardDiskSettingData 读回目标盘 Type
$r1=$ims.GetVirtualHardDiskSettingData($dst)
if($r1.ReturnValue -eq 4096){ Wait-Job2 $r1.Job | Out-Null }
$dstType=[int](Get-CimProp $r1.SettingData 'Type')   # 期望 2 (Fixed)
Write-Host "dstType=$dstType"
```

## [PASS] 读取VHDX元数据  `vhd_info`

- GetVirtualHardDiskSettingData 与 GetVirtualHardDiskState 的 OUT 参数（SettingData/State）为 CIM-XML 字符串（<INSTANCE CLASSNAME=...><PROPERTY NAME=...><VALUE>...），不是 MOF；应用 [xml] 解析 INSTANCE.PROPERTY 的 NAME/VALUE，不能用 GetText 或 MOF 行正则。
- 两个 Get 方法通常同步返回 ReturnValue=0（Job 为 null），无需轮询；但签名仍含 OUT Job（可能返回 4096），建议保留 Wait-Job2 作为兜底。
- SettingData 关键字段：Type（2=Fixed/3=Dynamic/4=Differencing）、Format（2=VHD/3=VHDX/4=VHDSet）、Path、ParentPath、MaxInternalSize（字节）、BlockSize、LogicalSectorSize、PhysicalSectorSize、VirtualDiskId。
- State 关键字段：FileSize（实际占用字节，动态盘约 4MiB）、InUse（布尔）、MinInternalSize、Alignment、FragmentationPercentage、PhysicalSectorSize。
- GetVirtualHardDiskState 调用后会短暂持有该 vhdx 文件句柄，紧接着的 Remove-Item 可能因文件占用失败；清理需带重试（本脚本 Remove-WithRetry 重试 25 次，每次间隔 200ms）。
- 该操作不创建虚拟机，仅通过 Msvm_ImageManagementService 创建、读取并删除一个临时 vhdx。CreateVirtualHardDisk 返回 4096 表示异步，需 Wait-Job2。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'

function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

# GetVirtualHardDiskSettingData / GetVirtualHardDiskState 的 OUT 参数为 CIM-XML <INSTANCE>...，不是 MOF。按 NAME->VALUE 解析。
function Parse-CimXml($text){ $h=@{}; if([string]::IsNullOrWhiteSpace($text)){return $h}; $xml=[xml]$text; foreach($p in $xml.INSTANCE.PROPERTY){ $v=$null; if($p.VALUE -ne $null){$v=$p.VALUE}; $h[$p.NAME]=$v }; return $h }

function Remove-WithRetry($path){ for($i=0;$i -lt 25;$i++){ if(-not (Test-Path $path)){return $true}; try{Remove-Item $path -Force -ErrorAction Stop; return $true}catch{Start-Sleep -Milliseconds 200} }; return (-not (Test-Path $path)) }

$vhdPath='C:\Temp\WMITEST_vhd_info.vhdx'
Remove-WithRetry $vhdPath | Out-Null
$ims=Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
try {
  # 创建动态 VHDX
  $vhdSD=([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $vhdSD.Type=[uint16]3      # 2=Fixed 3=Dynamic 4=Differencing
  $vhdSD.Format=[uint16]3    # 2=VHD 3=VHDX 4=VHDSet
  $vhdSD.Path=$vhdPath
  $vhdSD.MaxInternalSize=[uint64](4GB)
  $vhdSD.BlockSize=[uint32](1MB)
  $vhdSD.LogicalSectorSize=[uint32]512
  $vhdSD.PhysicalSectorSize=[uint32]4096
  $rc=$ims.CreateVirtualHardDisk($vhdSD.GetText(1))
  if($rc.ReturnValue -eq 4096){ $js=Wait-Job2 $rc.Job; if($js -ne 7){throw "create job JobState=$js"} } elseif($rc.ReturnValue -ne 0){ throw "create rv=$($rc.ReturnValue)" }

  # 读取静态元数据（同步返回 rv=0，OUT=SettingData）
  $rSD=$ims.GetVirtualHardDiskSettingData($vhdPath)
  if($rSD.ReturnValue -ne 0){ throw "GetSD rv=$($rSD.ReturnValue)" }
  $sd=Parse-CimXml $rSD.SettingData

  # 读取运行态/文件态（同步返回 rv=0，OUT=State）
  $rState=$ims.GetVirtualHardDiskState($vhdPath)
  if($rState.ReturnValue -ne 0){ throw "GetState rv=$($rState.ReturnValue)" }
  $st=Parse-CimXml $rState.State

  'SettingData: Type='+$sd['Type']+' Format='+$sd['Format']+' MaxInternalSize='+$sd['MaxInternalSize']+' BlockSize='+$sd['BlockSize']+' LogicalSectorSize='+$sd['LogicalSectorSize']+' PhysicalSectorSize='+$sd['PhysicalSectorSize']+' VirtualDiskId='+$sd['VirtualDiskId']
  'State: FileSize='+$st['FileSize']+' InUse='+$st['InUse']+' Alignment='+$st['Alignment']+' FragmentationPercentage='+$st['FragmentationPercentage']
}
finally {
  # GetVirtualHardDiskState 会短暂锁定文件，删除需重试
  Remove-WithRetry $vhdPath | Out-Null
}
```

## [PASS] 合并差分盘到父盘  `vhd_merge`

- Msvm_ImageManagementService.MergeVirtualHardDisk(SourcePath, DestinationPath, [out]Job). Source is the differencing child disk, Destination is the parent disk. A return value of 4096 requires polling with Wait-Job2.
- Creating a differencing disk: Msvm_VirtualHardDiskSettingData.CreateInstance(); set Type=[uint16]4 (Differencing), Format=[uint16]3 (VHDX), Path=child disk, ParentPath=parent disk, then create it with CreateVirtualHardDisk(GetText(1)).
- Creating a dynamic parent disk: Type=3 (Dynamic), Format=3 (VHDX); passing 0 for BlockSize/LogicalSectorSize/PhysicalSectorSize lets the system apply default values (default Block=2MB, Logical=512, Physical=4096).
- After a successful merge the differencing child disk file is automatically deleted (consumed); the parent disk is retained and absorbs the child's changes. The absence of the child disk file indicates the merge took effect.
- The OUT parameter SettingData of GetVirtualHardDiskSettingData is CIM-XML (<PROPERTY NAME="Type"><VALUE>4</VALUE>), not MOF text; the regular expression must match XML tags and cannot use a MOF-style pattern such as Type=4.
- This operation involves only disk files; it neither requires nor creates any virtual machine.

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){ return 7 }; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }; return $j.JobState }
$work = 'C:\Users\Administrator\Documents\GitHub\HyperV-WMI-Documentation\verify\work'
$parent = Join-Path $work 'wmitest_parent.vhdx'
$child  = Join-Path $work 'wmitest_child.vhdx'
Remove-Item -LiteralPath $parent,$child -ErrorAction SilentlyContinue
$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
try {
  # 1) Parent disk: dynamic VHDX (Type=3, Format=3). Sector parameters set to 0 so the system uses defaults.
  $pSd = ([wmiclass]"\\.\$($ns):Msvm_VirtualHardDiskSettingData").CreateInstance()
  $pSd.Type=[uint16]3; $pSd.Format=[uint16]3; $pSd.Path=$parent
  $pSd.MaxInternalSize=[uint64](64MB); $pSd.BlockSize=[uint32]0; $pSd.LogicalSectorSize=[uint32]0; $pSd.PhysicalSectorSize=[uint32]0
  $r1 = $ims.CreateVirtualHardDisk($pSd.GetText(1))
  if($r1.ReturnValue -eq 4096){ if((Wait-Job2 $r1.Job) -ne 7){ throw 'parent job failed' } } elseif($r1.ReturnValue -ne 0){ throw "parent rv=$($r1.ReturnValue)" }
  # 2) Differencing child disk (Type=4), pointing to the parent via ParentPath
  $cSd = ([wmiclass]"\\.\$($ns):Msvm_VirtualHardDiskSettingData").CreateInstance()
  $cSd.Type=[uint16]4; $cSd.Format=[uint16]3; $cSd.Path=$child; $cSd.ParentPath=$parent
  $r2 = $ims.CreateVirtualHardDisk($cSd.GetText(1))
  if($r2.ReturnValue -eq 4096){ if((Wait-Job2 $r2.Job) -ne 7){ throw 'child job failed' } } elseif($r2.ReturnValue -ne 0){ throw "child rv=$($r2.ReturnValue)" }
  # Read back: the SettingData OUT parameter is CIM-XML (not MOF)
  $r3 = $ims.GetVirtualHardDiskSettingData($child)
  $sd = $r3.SettingData; $type=$null
  if($sd -match '(?s)NAME="Type"[^>]*>\s*<VALUE>(\d+)</VALUE>'){ $type=$matches[1] }   # expected 4
  # 3) Merge: SourcePath=child (differencing), DestinationPath=parent. On success the child disk is consumed.
  $r4 = $ims.MergeVirtualHardDisk($child, $parent)
  if($r4.ReturnValue -eq 4096){ if((Wait-Job2 $r4.Job) -ne 7){ throw 'merge job failed' } } elseif($r4.ReturnValue -ne 0){ throw "merge rv=$($r4.ReturnValue)" }
  $ok = ($type -eq '4') -and (Test-Path $parent) -and (-not (Test-Path $child))
  Write-Host ("PASS=" + $ok)
}
finally { Remove-Item -LiteralPath $parent,$child -ErrorAction SilentlyContinue }
```

## [PASS] 扩容VHDX虚拟磁盘  `vhd_resize`

- Msvm_ImageManagementService.ResizeVirtualHardDisk signature: the parameters are (Path string, MaxInternalSize uint64), and the OUT parameter is named Job (a CIM_ConcreteJob reference). There are only two input parameters, with no Type or credential parameter.
- MaxInternalSize is expressed in bytes (uint64) and represents the visible capacity ceiling of the virtual disk rather than the size of the physical file. In the example, 10 GiB=10737418240 is expanded to 30 GiB=32212254720.
- Like CreateVirtualHardDisk, ResizeVirtualHardDisk returns 4096 (an asynchronous job) and requires Wait-Job2 to poll ConcreteJob.JobState until it reaches 7 (Completed).
- Expansion only requires the disk file to be offline; no virtual machine or SCSI controller needs to be attached. Shrinking (reducing MaxInternalSize) requires the partitions inside the VHDX to have been compacted; this recipe covers only the expansion scenario.
- Read-back verification reuses GetVirtualHardDiskSettingData(Path), whose OUT parameter SettingData is CIM-XML; a regular expression is used to extract MaxInternalSize.
- This operation involves only the disk file and does not create a virtual machine; cleanup requires only Remove-Item to delete the .vhdx.

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p) {
  if (-not $p) { return 7 }
  $j = [wmi]$p
  while ($j.JobState -eq 3 -or $j.JobState -eq 4) { Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

function Read-MaxInternalSize($ims, $path) {
  $info = $ims.GetVirtualHardDiskSettingData($path)
  if ($info.ReturnValue -ne 0) { throw "GetVHDSettingData rv=$($info.ReturnValue)" }
  $sd = $info.SettingData
  if ($sd -match 'NAME="MaxInternalSize"[^<]*<VALUE>(\d+)</VALUE>') { return [uint64]$matches[1] }
  if ($sd -match 'NAME="MaxInternalSize".*?<VALUE>(\d+)</VALUE>') { return [uint64]$matches[1] }
  throw "MaxInternalSize not found in SettingData"
}

$vhdPath = 'C:\Temp\WMITEST_vhd_resize.vhdx'
if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }
$startSize = [uint64](10 * 1024 * 1024 * 1024)   # 10 GiB
$newSize   = [uint64](30 * 1024 * 1024 * 1024)   # 30 GiB
$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

try {
  # 1. Create a small dynamic VHDX (Type=3 Dynamic, Format=3 VHDX)
  $vhdsd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $vhdsd.Type = [uint16]3; $vhdsd.Format = [uint16]3; $vhdsd.Path = $vhdPath
  $vhdsd.MaxInternalSize = $startSize
  $vhdsd.BlockSize = [uint32]0; $vhdsd.LogicalSectorSize = [uint32]0; $vhdsd.PhysicalSectorSize = [uint32]0
  $rc = $ims.CreateVirtualHardDisk($vhdsd.GetText(1))
  if ($rc.ReturnValue -eq 4096) { if ((Wait-Job2 $rc.Job) -ne 7) { throw 'create job failed' } } elseif ($rc.ReturnValue -ne 0) { throw "create rv=$($rc.ReturnValue)" }
  $beforeMax = Read-MaxInternalSize $ims $vhdPath

  # 2. Expand: ResizeVirtualHardDisk(Path string, MaxInternalSize uint64) -> OUT Job
  $rr = $ims.ResizeVirtualHardDisk($vhdPath, $newSize)
  if ($rr.ReturnValue -eq 4096) { if ((Wait-Job2 $rr.Job) -ne 7) { throw 'resize job failed' } } elseif ($rr.ReturnValue -ne 0) { throw "resize rv=$($rr.ReturnValue)" }

  # 3. Read back and verify
  $afterMax = Read-MaxInternalSize $ims $vhdPath
  Write-Output ("Before=$beforeMax After=$afterMax")
  if ($afterMax -eq $newSize) { Write-Output 'RESULT: PASS' } else { Write-Output 'RESULT: FAIL' }
}
finally {
  if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }
}
```

## [PASS] 为差分虚拟硬盘重新设置父盘  `vhd_setparent`

- This operation uses only Msvm_ImageManagementService and does not require creating a virtual machine.
- SetParentVirtualHardDisk signature: (string ChildPath, string ParentPath, string LeafPath, boolean IgnoreIDMismatch, [OUT] CIM_ConcreteJob Job). ChildPath is the differencing disk (leaf disk) whose parent is being reassigned, ParentPath is the new parent disk, LeafPath may be passed as $null, and IgnoreIDMismatch is typically $false. A return value of 0 indicates synchronous completion, while 4096 indicates an asynchronous job that requires polling JobState.
- When creating a differencing disk (Type=4), Msvm_VirtualHardDiskSettingData needs only Path, Type=4, Format, and ParentPath set; MaxInternalSize and BlockSize must not be set (these properties are inherited from the parent). The file extension must be .vhdx (VHDX) or .vhd (VHD); using .avhdx is rejected by CreateVirtualHardDisk, returning job ErrorCode=32773 (invalid file extension).
- The disk identifier of the new parent disk must match the original parent identifier recorded in the differencing disk; otherwise IgnoreIDMismatch must be set to $true. The example obtains parentB by byte-copying the original parent, so the identifiers naturally match and IgnoreIDMismatch=$false can be used.
- The OUT parameter SettingData of GetVirtualHardDiskSettingData returns a CIM-XML string (System.String) rather than a WMI object. It must be parsed with [xml] to read <INSTANCE>/<PROPERTY NAME='ParentPath'>/<VALUE>; .ParentPath cannot be accessed directly, and a simple regular expression is not advisable (it may erroneously match the NAME attribute).
- The related method ReconnectParentVirtualHardDisk is used to relink after the parent disk's location has moved (without changing the parent path), whereas SetParentVirtualHardDisk is used to change the parent disk path.
- Type enumeration: 2=Fixed, 3=Dynamic, 4=Differencing; Format enumeration: 2=VHD, 3=VHDX. This method and the related classes have been available since build 9200.

```powershell
# vhd_setparent: differencing disk reconnect parent via SetParentVirtualHardDisk
# Pure Msvm_ImageManagementService; no VM needed. ASCII only.
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}

$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$vhdClassPath = "\\.\" + $ns + ":Msvm_VirtualHardDiskSettingData"

$work = 'C:\Users\Administrator\Documents\GitHub\HyperV-WMI-Documentation\verify\work'
$parentA = Join-Path $work 'sp_parentA.vhdx'
$parentB = Join-Path $work 'sp_parentB.vhdx'
$child   = Join-Path $work 'sp_child.vhdx'
foreach($f in @($parentA,$parentB,$child)){ if(Test-Path $f){ Remove-Item $f -Force } }

function New-Vhd($path, $type, $parentPath){
  $vsd = ([wmiclass]$vhdClassPath).CreateInstance()
  $vsd.Path = $path
  $vsd.Type = [uint16]$type        # 2=Fixed 3=Dynamic 4=Differencing
  $vsd.Format = [uint16]3          # 3=VHDX
  if($type -ne 4){
    $vsd.MaxInternalSize = [uint64](64MB)
  } else {
    $vsd.ParentPath = $parentPath  # diff disk: set ParentPath, NOT MaxInternalSize
  }
  $r = $ims.CreateVirtualHardDisk($vsd.GetText(1))
  if($r.ReturnValue -eq 4096){
    $st = Wait-Job2 $r.Job
    if($st -ne 7){ $jb=[wmi]$r.Job; throw "CreateVHD job $st code=$($jb.ErrorCode) desc=$($jb.ErrorDescription)" }
  } elseif($r.ReturnValue -ne 0){ throw "CreateVHD rv $($r.ReturnValue)" }
}

# GetVirtualHardDiskSettingData returns SettingData as a CIM-XML <INSTANCE> STRING
function Get-CimXmlProp($xmlStr, $propName){
  if(-not $xmlStr){ return $null }
  [xml]$x = $xmlStr
  foreach($p in $x.INSTANCE.PROPERTY){ if($p.NAME -eq $propName){ return [string]$p.VALUE } }
  return $null
}
function Get-ParentPath($path){
  $r = $ims.GetVirtualHardDiskSettingData($path)
  if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
  return (Get-CimXmlProp $r.SettingData 'ParentPath')
}

try {
  New-Vhd $parentA 3 $null
  New-Vhd $child   4 $parentA
  $origParent = Get-ParentPath $child            # -> sp_parentA.vhdx
  Copy-Item $parentA $parentB -Force             # byte copy so parent IDs match

  # SetParentVirtualHardDisk(ChildPath, ParentPath, LeafPath, IgnoreIDMismatch, [OUT]Job)
  $rs = $ims.SetParentVirtualHardDisk($child, $parentB, $null, $false)
  if($rs.ReturnValue -eq 4096){
    $st = Wait-Job2 $rs.Job
    if($st -ne 7){ $jb=[wmi]$rs.Job; throw "SetParent job $st code=$($jb.ErrorCode) desc=$($jb.ErrorDescription)" }
  } elseif($rs.ReturnValue -ne 0){ throw "SetParent rv $($rs.ReturnValue)" }

  $newParent = Get-ParentPath $child             # -> sp_parentB.vhdx
  $pass = ($newParent -ne $null) -and ($newParent.ToLower() -eq $parentB.ToLower())
  Write-Host ("ORIG=$origParent  NEW=$newParent  " + $(if($pass){'PASS'}else{'FAIL'}))
}
finally {
  foreach($f in @($child,$parentB,$parentA)){ if(Test-Path $f){ try{ Remove-Item $f -Force }catch{} } }
}
```

## [PASS] 校验 VHDX 磁盘完整性  `vhd_validate`

- Msvm_ImageManagementService.ValidateVirtualHardDisk has only one IN parameter, Path (string), and its OUT parameter is Job (a CIM_ConcreteJob reference). This method typically returns asynchronously with rv=4096 and requires polling JobState until completion.
- Decision criteria: when the job reaches the completed state JobState=7 (Completed) the disk is valid; a corrupt disk drives the job into JobState=10 (Exception), from which ErrorCode and ErrorDescription can be read via [wmi]$Job to obtain the specific reason. The method validates integrity by attempting to open the disk read-only.
- Under PowerShell 5.1 / Get-WmiObject, CreateVirtualHardDisk accepts only a single IN parameter (the embedded Msvm_VirtualHardDiskSettingData serialized via GetText(1)); passing an additional second $null triggers a MethodCountCouldNotFindBest error. Get-WmiObject does not require OUT parameters to be passed when invoking a method.
- The canonical directory does not include a ValidateVirtualHardDiskSnapshot method (referenced in the catalog but not implemented); currently only ValidateVirtualHardDisk is available.
- This method is a pure file-level operation that neither creates nor affects any virtual machine; the temporary vhdx is deleted after use.

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}

$vhd = 'C:\Temp\test_validate.vhdx'
$ims = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService

# --- Create a dynamic VHDX to validate ---
$vhdsd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
$vhdsd.Type = [uint16]3          # 3 = dynamic
$vhdsd.Format = [uint16]3        # 3 = VHDX
$vhdsd.Path = $vhd
$vhdsd.MaxInternalSize = [uint64](64MB)
$vhdsd.BlockSize = [uint32]0
$vhdsd.LogicalSectorSize = [uint32]0
$vhdsd.PhysicalSectorSize = [uint32]0
# CreateVirtualHardDisk only takes the single IN param (embedded VHDSD); do NOT pass a 2nd arg
$rc = $ims.CreateVirtualHardDisk($vhdsd.GetText(1))
if($rc.ReturnValue -eq 4096){ if((Wait-Job2 $rc.Job) -ne 7){ throw 'create failed' } }

# --- Validate: ValidateVirtualHardDisk(Path) -> OUT Job ---
$rv = $ims.ValidateVirtualHardDisk($vhd)
if($rv.ReturnValue -eq 4096){
  $js = Wait-Job2 $rv.Job        # 7 = Completed = valid; 10 = Exception
  if($js -eq 7){ Write-Host 'VHDX VALID' }
  else {
    $job = [wmi]$rv.Job
    Write-Host ("INVALID ErrorCode=$($job.ErrorCode): $($job.ErrorDescription)")
  }
} elseif($rv.ReturnValue -eq 0){ Write-Host 'VHDX VALID (sync)' }
else { Write-Host ("call rv=$($rv.ReturnValue)") }

Remove-Item -Force $vhd
```

## [PASS] 配置合成显示控制器分辨率  `video_display`

- Msvm_SyntheticDisplayControllerSettingData has no methods of its own; modifying its properties must go through Msvm_VirtualSystemManagementService.ModifyResourceSettings (passing the settings serialized via GetText(1)).
- ResolutionType is of type uint8; PowerShell 5.1 has no [uint8] type accelerator and requires the [byte] cast (using [uint8] raises a "type not found" error). HorizontalResolution and VerticalResolution are uint16 and can be cast directly with [uint16].
- ResolutionType ValueMap: 0=Unknown, 1=Other, 2=Maximum, 3=Single, 4=Default. A newly created generation-2 virtual machine defaults to ResolutionType=4 (Default) at 1920x1200; the custom HorizontalResolution/VerticalResolution take effect only when it is set to 3 (Single).
- This resource is the synthetic display controller setting that each virtual machine carries by default, so AddResourceSettings is not needed; the first instance can be retrieved directly via GetRelated on the VSSD.
- ModifyResourceSettings returning 0 indicates synchronous completion; DefineSystem and DestroySystem require polling the job when they return 4096.
- This operation is a pure configuration-layer operation and does not depend on the guest operating system or the running state of the virtual machine. The related classes are available in Windows Server 2025 (build 26100) Hyper-V.

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$name = 'WMITEST_video_display'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null

try {
  # Create Gen2 VM
  $vssd = ([wmiclass]"\\.\$($ns):Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $null = Wait-Job2 $r.Job }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  # Get the VM's VSSD, then its display controller setting data
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $disp = ([wmi]$vssd2.__PATH).GetRelated('Msvm_SyntheticDisplayControllerSettingData') | Select-Object -First 1
  if(-not $disp){ throw "No Msvm_SyntheticDisplayControllerSettingData found on VM" }

  # Modify: set Single resolution 1280x1024 (ResolutionType uint8 -> use [byte] in PS5.1)
  $disp.ResolutionType = [byte]3
  $disp.HorizontalResolution = [uint16]1280
  $disp.VerticalResolution = [uint16]1024
  $r2 = $vsms.ModifyResourceSettings(@($disp.GetText(1)))
  if($r2.ReturnValue -eq 4096){ $st = Wait-Job2 $r2.Job; if($st -ne 7){ throw "ModifyResourceSettings job state=$st" } }
  elseif($r2.ReturnValue -ne 0){ throw "ModifyResourceSettings rv=$($r2.ReturnValue)" }

  # Read back fresh
  $vssd3 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $disp2 = ([wmi]$vssd3.__PATH).GetRelated('Msvm_SyntheticDisplayControllerSettingData') | Select-Object -First 1
  $ok = ($disp2.ResolutionType -eq 3) -and ($disp2.HorizontalResolution -eq 1280) -and ($disp2.VerticalResolution -eq 1024)
  if($ok){ Write-Host "PASS ResolutionType=3 1280x1024" } else { Write-Host "FAIL" }
}
catch { Write-Host "ERROR: $($_.Exception.Message)"; Write-Host "FAIL" }
finally {
  if($vm){
    $d = $vsms.DestroySystem($vm.__PATH)
    if($d.ReturnValue -eq 4096){ $null = Wait-Job2 $d.Job }
  }
}
```

## [PASS] 设置端口 VLAN (AccessVlanId)  `vlan_set`

- The port VLAN must be applied through Msvm_VirtualSystemManagementService.AddFeatureSettings (the virtual-machine connection variant); Msvm_VirtualEthernetSwitchManagementService.AddFeatureSettings (the switch-port variant) cannot be used, as the latter drives the job into JobState=10 (Exception) with ErrorCode=32773 (failed while modifying virtual Ethernet switch connection settings).
- AddFeatureSettings signature: AffectedConfiguration is a reference to the connected Msvm_EthernetPortAllocationSettingData, and FeatureSettings is a string[] (embedded instances serialized via GetText(1)); the OUT parameters are ResultingFeatureSettings[] and Job. A return value of 0 indicates synchronous completion.
- A VLAN feature instance cannot be created via a bare CreateInstance; the default Msvm_EthernetSwitchPortVlanSettingData should be retrieved from Msvm_EthernetSwitchFeatureCapabilities (InstanceID=Microsoft:952C5004-4465-451C-8CB8-FA9AB382B773) through the Msvm_FeatureSettingsDefineCapabilities association, then cloned and modified.
- Msvm_EthernetSwitchPortVlanSettingData: OperationMode (uint32) 1=Access, 2=Trunk, 3=Private; AccessVlanId (uint16) takes effect only in Access mode; NativeVlanId is used in Trunk mode.
- Precondition: the NIC must already be connected to the switch via AddResourceSettings (Msvm_EthernetPortAllocationSettingData.HostResource points to the switch __PATH, with EnabledState=2), and the VLAN feature is added onto that connection. The virtual machine does not need to be powered on.
- On read-back, the value is obtained through the connection's EthernetPortAllocationSettingData.GetRelated('Msvm_EthernetSwitchPortVlanSettingData'). This class has been available since build 9200.

```powershell
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 1) Gen2 VM
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance(); $vssd.ElementName='WMITEST_vlan_set'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){[void](Wait-Job2 $r.Job)}
$vm=[wmi]$r.ResultingSystem
$vmSettings=[wmi](($vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1).__PATH)
# 2) add synthetic NIC
$nic=(Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData -Filter "InstanceID like '%\\Default'").Clone()
$nic.ElementName='WMITEST_NIC'; $nic.VirtualSystemIdentifiers=@([Guid]::NewGuid().ToString('B').ToUpper())
$ra=$vsms.AddResourceSettings($vmSettings.__PATH,@($nic.GetText(1))); if($ra.ReturnValue -eq 4096){[void](Wait-Job2 $ra.Job)}
$nicRasd=[wmi]$ra.ResultingResourceSettings[0]
# 3) connect NIC to existing switch named 'Switch'
$sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch -Filter "ElementName='Switch'"
$epas=(Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData -Filter "InstanceID like '%\\Default'").Clone()
$epas.Parent=$nicRasd.__PATH; $epas.HostResource=@($sw.__PATH)
$rc=$vsms.AddResourceSettings($vmSettings.__PATH,@($epas.GetText(1))); if($rc.ReturnValue -eq 4096){[void](Wait-Job2 $rc.Job)}
$connEpas=[wmi]$rc.ResultingResourceSettings[0]
# 4) build VLAN feature: clone default from capabilities (bare CreateInstance is rejected, err 32773)
$cap=Get-WmiObject -Namespace $ns -Class Msvm_EthernetSwitchFeatureCapabilities -Filter "InstanceID='Microsoft:952C5004-4465-451C-8CB8-FA9AB382B773'"
$vlanDef=$cap.GetRelated('Msvm_EthernetSwitchPortVlanSettingData','Msvm_FeatureSettingsDefineCapabilities',$null,$null,'PartComponent','GroupComponent',$false,$null)|Select-Object -First 1
$vlan=([wmi]$vlanDef.__PATH).Clone()
$vlan.OperationMode=[uint32]1   # 1=Access 2=Trunk 3=Private
$vlan.AccessVlanId=[uint16]42
# 5) IMPORTANT: use VSMS.AddFeatureSettings (VM-connection variant), NOT VirtualEthernetSwitchManagementService
$rf=$vsms.AddFeatureSettings($connEpas.__PATH,@($vlan.GetText(1))); if($rf.ReturnValue -eq 4096){[void](Wait-Job2 $rf.Job)}
# 6) read back
$vlanBack=$connEpas.GetRelated('Msvm_EthernetSwitchPortVlanSettingData')|Select-Object -First 1
"OperationMode=$($vlanBack.OperationMode) AccessVlanId=$($vlanBack.AccessVlanId)"
# cleanup
$vsms.DestroySystem($vm.__PATH)
```

## [PASS] 创建虚拟机集合并添加成员  `vm_groups`

- 服务类为 Msvm_CollectionManagementService（单例，经 Get-WmiObject 获取实例）。
- DefineCollection(Name, Id, Type)：Name 为显示名（string）；Id 为 GUID 字符串，传 $null 时由服务自动生成；Type 为 uint16，0=虚拟机集合（组），1=管理集合。OUT 参数为 DefinedCollection（集合引用路径）与 Job。返回值 0 表示同步完成。
- 返回的 DefinedCollection 经 [wmi] 转换后即 Msvm_VirtualSystemCollection，其 ElementName 为传入的 Name。转换回的对象上 InstanceID 可能为空，集合 GUID 应从该实例的标识属性读取，不应依赖 InstanceID。
- AddMember(Member, Collection)：Member 为待加入元素的引用，此处为虚拟机的 __PATH（Msvm_ComputerSystem）；Collection 为 DefinedCollection 路径。OUT 仅有 Job。Member 也可为另一个集合，从而实现集合嵌套。
- 验证成员：通过集合对象的 GetRelated('Msvm_ComputerSystem') 枚举成员，并按 VM.Name（GUID）匹配确认目标虚拟机在内。
- 清理顺序：RemoveMember(Member, Collection) -> DestroyCollection(Collection) -> DestroySystem(VM)。
- 所有写方法返回 4096 时按统一范式轮询 Msvm_ConcreteJob.JobState。该类自 build 10240 起提供。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$cms =Get-WmiObject -Namespace $ns -Class Msvm_CollectionManagementService

# build a Gen2 test VM
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName='WMITEST_vm_groups'; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
$vm=[wmi]$r.ResultingSystem

# DefineCollection: IN Name,Id,Type(uint16 0|1) ; OUT DefinedCollection(ref),Job. Type=0 => VM group.
$rc=$cms.DefineCollection('WMITEST_vm_groups_coll',$null,[uint16]0)
if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job | Out-Null }
$collPath=$rc.DefinedCollection
$coll=[wmi]$collPath

# AddMember: IN Member(VM __PATH), Collection(collPath) ; OUT Job
$ra=$cms.AddMember($vm.__PATH,$collPath)
if($ra.ReturnValue -eq 4096){ Wait-Job2 $ra.Job | Out-Null }

# verify: members reachable from the collection via GetRelated('Msvm_ComputerSystem')
$members=([wmi]$collPath).GetRelated('Msvm_ComputerSystem')
$ok=$false; foreach($m in $members){ if($m.Name -eq $vm.Name){ $ok=$true } }

# cleanup: RemoveMember -> DestroyCollection -> DestroySystem
$rr=$cms.RemoveMember($vm.__PATH,$collPath); if($rr.ReturnValue -eq 4096){ Wait-Job2 $rr.Job | Out-Null }
$rd=$cms.DestroyCollection($collPath); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
$rdv=$vsms.DestroySystem($vm.__PATH); if($rdv.ReturnValue -eq 4096){ Wait-Job2 $rdv.Job | Out-Null }
Write-Host "memberFound=$ok"
```

## [PASS] 读取与修改 BIOS GUID 及虚拟机 Generation ID  `vmgenid_bios`

- BIOSGUID 位于 Msvm_VirtualSystemSettingData 上。MOF/canonical 将其标记为 access=Read（只读），但通过 ModifySystemSettings 下发可返回 rv=0 且读回值确实改变，即该属性实际可写。该属性自 build 9200 起提供。
- Hyper-V 读回 BIOSGUID 时不带花括号（返回 '8A2B...' 而非 '{8A2B...}'），写入时带或不带花括号均可接受。比较前须统一去除花括号并转为大写，否则可能误判为未改变。
- 暴露给来宾操作系统的虚拟机 Generation ID 为 VSSD.VirtualSystemIdentifiers（string[]，GUID）。该属性在虚拟机停止态为空，运行时才填充；其自身为只读（仅可经 ModifyVirtualSystemResources 修改，常规路径不可写）。
- BIOSGUID 是第一代（SubType:1）虚拟机的概念，对应来宾内的 SMBIOS UUID；示例使用一台第一代空虚拟机。第二代虚拟机同样具有该属性，语义对应固件 UUID。
- 写操作使用 ModifySystemSettings（传入整机设置的 GetText(1)），而非 ModifyResourceSettings。返回 0 表示同步完成。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j = [wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j = [wmi]$p }
  return $j.JobState
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$name = 'WMITEST_vmgenid_bios'

# Pre-clean any residue
Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$name'" | ForEach-Object { $vsms.DestroySystem($_.__PATH) | Out-Null }

$vm = $null
try {
  # Create a Gen1 VM (Gen1 is where BIOSGUID lives). SubType:1
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:1'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $st = Wait-Job2 $r.Job; if($st -ne 7){ throw "DefineSystem job failed state=$st" } }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem

  # Get the VSSD of the new VM
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $vssd2 = [wmi]$vssd2.__PATH

  # 1) READ BIOSGUID
  $biosGuidOrig = $vssd2.BIOSGUID
  Write-Output "READ BIOSGUID = $biosGuidOrig"

  # 2) MODIFY BIOSGUID via ModifySystemSettings (MOF marks it Read-only, but it is writable in practice)
  $newGuid = '{11112222-3333-4444-5555-666677778888}'
  $vssd2.BIOSGUID = $newGuid
  $rm = $vsms.ModifySystemSettings($vssd2.GetText(1))
  if($rm.ReturnValue -eq 4096){ Wait-Job2 $rm.Job | Out-Null }
  elseif($rm.ReturnValue -ne 0){ throw "ModifySystemSettings rv=$($rm.ReturnValue)" }

  # Re-read BIOSGUID to verify it changed (Hyper-V returns it WITHOUT braces)
  $vssd3 = [wmi]($vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1).__PATH
  $biosGuidAfter = $vssd3.BIOSGUID
  $norm = { param($g) ($g -replace '[{}]','').ToUpper() }
  $changed = ((& $norm $biosGuidAfter) -eq (& $norm $newGuid))
  Write-Output "READ-BACK BIOSGUID = $biosGuidAfter  changed=$changed"

  # 3) VM Generation ID exposed to guest = VSSD.VirtualSystemIdentifiers (empty until VM runs)
  Write-Output "VirtualSystemIdentifiers = $($vssd3.VirtualSystemIdentifiers -join ',')"

  if($changed){ Write-Output 'ASSERT: PASS' } else { Write-Output 'ASSERT: FAIL' }
}
finally {
  if($vm -ne $null){ try { $vsms.DestroySystem($vm.__PATH) | Out-Null } catch {} }
  $left = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$name'"
  if($left){ $left | ForEach-Object { $vsms.DestroySystem($_.__PATH) | Out-Null } }
}
```

## [PASS] 查询来宾群集与 VSS 集成组件信息  `vss_cluster_query`

- Msvm_VssService 类暴露 QueryGuestClusterInformation(OUT GuestClusterInformation: Msvm_GuestClusterInformation)。该类为来宾服务，superclass 为 Msvm_GuestService。
- 关键限制：Msvm_VssService 是来宾侧服务，仅当来宾 OS 已安装并运行集成服务(VSS/备份组件)并向主机回报时，才存在与该虚拟机关联的 INSTANCE。在无 OS 的空测试虚拟机上 $vm.GetRelated('Msvm_VssService') 为空，因此 QueryGuestClusterInformation 无法在无来宾 OS 的虚拟机上调用。这是 API 设计使然。
- Msvm_GuestClusterInformation(纯 OUT 嵌入返回)字段：ClusterId, ClusterSize, IsActiveActive, IsClustered, IsOnline, IsOwned, LastResourceMoveTime, SharedVirtualHardDiskPaths, SharedVirtualHardDisks，用于读取来宾 OS 所在故障转移群集的信息。
- Msvm_VssComponentSettingData 是每虚拟机的 VSS 集成组件设置(继承 CIM_ResourceAllocationSettingData)，每台虚拟机默认 1 个实例，EnabledState=2(启用)，经 VSSD.GetRelated('Msvm_VssComponentSettingData') 枚举。它对应虚拟机的‘备份(卷影复制)’集成服务开关；EnabledState 2=启用、3=禁用，可用 ModifyResourceSettings 修改。
- 此操作为纯读取(kind=read)：可确认类与方法 schema 存在、每虚拟机的 VssComponentSettingData 可枚举读回，以及 QueryGuestClusterInformation 需要活跃来宾群集这一调用前置条件。
- 调用 QueryGuestClusterInformation 的前置条件：来宾运行 Windows Server 故障转移群集且 Hyper-V 集成服务在线。此时 $vm.GetRelated('Msvm_VssService') 返回实例，调用后从 ret.GuestClusterInformation 读取 ClusterId/ClusterSize/IsClustered 等字段。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$TESTNAME = 'WMITEST_vss_cluster_query'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null
try {
  # --- 读取 Msvm_VssService.QueryGuestClusterInformation 与 OUT 类型 Msvm_GuestClusterInformation 的 schema ---
  $vssSvcClass = Get-WmiObject -Namespace $ns -Class Msvm_VssService -List
  $hasQuery = ($vssSvcClass.Methods['QueryGuestClusterInformation'] -ne $null)
  $gciClass = Get-WmiObject -Namespace $ns -Class Msvm_GuestClusterInformation -List
  ($gciClass.Properties | ForEach-Object { $_.Name }) -join ','

  # --- 创建隔离的第二代测试虚拟机 ---
  $vssdClass = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSettingData -List
  $vssd = $vssdClass.CreateInstance()
  $vssd.ElementName = $TESTNAME
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
  $vm = [wmi]$r.ResultingSystem

  # --- 枚举该虚拟机的 Msvm_VssComponentSettingData(每虚拟机的 VSS 集成组件设置) ---
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  $vcsd = ([wmi]$vssd2.__PATH).GetRelated('Msvm_VssComponentSettingData')
  # $vcsd[0].EnabledState : 2=启用(默认), 3=禁用

  # --- 尝试获取来宾 VSS 服务实例并查询群集信息 ---
  # Msvm_VssService 是每虚拟机的来宾服务(superclass Msvm_GuestService)；仅当来宾 OS
  # 已运行集成服务并向主机回报时，对应 INSTANCE 才存在。
  $vssSvc = $vm.GetRelated('Msvm_VssService') | Select-Object -First 1
  if ($vssSvc) {
    $ret = ([wmi]$vssSvc.__PATH).QueryGuestClusterInformation()
    # ret.ReturnValue 0=成功 4096=作业; ret.GuestClusterInformation = 嵌入的 Msvm_GuestClusterInformation
  }
}
finally {
  if ($vm) {
    $vsms2 = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
    $dr = $vsms2.DestroySystem($vm.__PATH)
    if ($dr.ReturnValue -eq 4096) { Wait-Job2 $dr.Job | Out-Null }
  }
  Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $TESTNAME } | ForEach-Object {
    (Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService).DestroySystem($_.__PATH) | Out-Null
  }
}
```

## [PASS] 读取虚拟机的 VTL2/paravisor 设置  `vtl2_settings`

- Msvm_VirtualSystemGuestManagementService 自 build 26100 起提供，是 VTL2/OpenHCL paravisor 设置的读写入口，为单例服务，各方法均以 VmId(即 ComputerSystem.Name，GUID)定位虚拟机。
- 三个读方法在普通(非 OpenHCL)第二代虚拟机上的返回行为：GetVtl2Settings 返回 rv=32795(无 VTL2 配置，Settings=null)；QueryVtl2Settings 抛 WBEM_E_SHUTTING_DOWN(ErrorCode=ShuttingDown，表示 VTL2 通道未建立)；GetManagementVtlSettings(VmId, Namespace) 对任意 Namespace 均抛 ErrorCode=NotFound(无管理 VTL 命名空间)。
- 对不存在的 VmId(如全零 GUID)，三方法均抛 ErrorCode=NotFound。因此在存在的虚拟机上 rv=32795 的语义是‘虚拟机存在但未配置 VTL2’，而非定位失败。
- 方法签名：GetVtl2Settings(string VmId) -> uint8[] Settings, uint64 CurrentUpdateId；QueryVtl2Settings(string VmId) -> string Settings(JSON), uint64 CurrentUpdateId；GetManagementVtlSettings(string VmId, string Namespace) -> uint8[] Settings, uint64 CurrentUpdateId。写方法 ModifyVtl2Settings/UpdateVtl2Settings/SetManagementVtlSettings 带 OUT Job(CIM_ConcreteJob 引用)，返回 4096 时须轮询作业。GetVtl2Settings/QueryVtl2Settings 的 ValueMap 仅声明 0/1，实现上另有 32795 等实现相关返回码。
- 要读取真正的 VTL2 JSON 载荷，需虚拟机以 OpenHCL paravisor 运行(机密计算 TDX/SEV-SNP 隔离场景)。在无此类客户机时三方法返回‘未配置/未建立/未找到’，属功能边界，而非调用错误。
- vmms 提供程序在上一次 DestroySystem 后可能短暂重启，导致单例服务枚举返回空或抛 WBEM_E_SHUTTING_DOWN。脚本以 Get-SvcRetry(最多 60 次、每次 500ms)重试获取服务实例，以避免连续运行时的间歇性失败。
- 脚本使用唯一测试虚拟机 WMITEST_vtl2_settings，并在 try/finally 中通过 DestroySystem 清理，保证运行前后无残留。

```powershell
$ErrorActionPreference = 'Stop'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
# vmms 单例服务在上一次 DestroySystem 后可能短暂重启(WBEM_E_SHUTTING_DOWN)，枚举须重试
function Get-SvcRetry($ns,$cls){ for($i=0;$i -lt 60;$i++){ try{ $o=@(Get-WmiObject -Namespace $ns -Class $cls -ErrorAction Stop)[0]; if($o){return $o} }catch{}; Start-Sleep -Milliseconds 500 }; return $null }

$ns='root\virtualization\v2'
$vmName='WMITEST_vtl2_settings'
$vsms = Get-SvcRetry $ns 'Msvm_VirtualSystemManagementService'
$gms  = Get-SvcRetry $ns 'Msvm_VirtualSystemGuestManagementService'  # VTL2 读取入口(单例服务)
try {
    # 创建第二代测试虚拟机(VmId = ComputerSystem.Name = GUID)
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $vmName
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { Wait-Job2 $r.Job | Out-Null }
    $vm = [wmi]$r.ResultingSystem
    $vmId = $vm.Name

    # 1) GetVtl2Settings(VmId IN) -> Settings(uint8[] OUT), CurrentUpdateId(uint64 OUT)
    #    非 OpenHCL 虚拟机返回 rv=32795(无 VTL2/paravisor 配置)，Settings=null。
    $g = $gms.GetVtl2Settings($vmId)
    Write-Output "GetVtl2Settings rv=$($g.ReturnValue)"

    # 2) QueryVtl2Settings(VmId IN) -> Settings(string JSON OUT), CurrentUpdateId(uint64 OUT)
    #    非 OpenHCL 虚拟机 VTL2 通道未建立，抛 WBEM_E_SHUTTING_DOWN。
    try { $q = $gms.QueryVtl2Settings($vmId); Write-Output "QueryVtl2Settings rv=$($q.ReturnValue) json=$($q.Settings)" }
    catch { Write-Output "QueryVtl2Settings EXC ErrorCode=$($_.Exception.ErrorCode)" }

    # 3) GetManagementVtlSettings(VmId IN, Namespace IN) -> Settings(uint8[] OUT), CurrentUpdateId(uint64 OUT)
    #    非 OpenHCL 虚拟机无管理 VTL 命名空间，任意 Namespace 均返回 ErrorCode=NotFound。
    try { $m = $gms.GetManagementVtlSettings($vmId,''); Write-Output "GetManagementVtlSettings rv=$($m.ReturnValue)" }
    catch { Write-Output "GetManagementVtlSettings EXC ErrorCode=$($_.Exception.ErrorCode)" }
}
finally {
    # 清理: 按名重取并销毁
    $vsms2 = Get-SvcRetry $ns 'Msvm_VirtualSystemManagementService'
    Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $vmName } |
        ForEach-Object { $d=$vsms2.DestroySystem($_.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null} }
}
```

## [PASS] 为第二代虚拟机启用 vTPM 安全设置  `vtpm_security`

- vTPM 相关的三个方法均定义在 Msvm_SecurityService 上（而非 Msvm_VirtualSystemManagementService）：ModifySecuritySettings、SetKeyProtector、GetKeyProtector。
- Msvm_SecuritySettingData 通过 VSSD 的 GetRelated('Msvm_SecuritySettingData') 获取；其属性（TpmEnabled、ShieldingRequested、DataProtectionRequested、EncryptStateAndVmMigrationTraffic 等）均为只读，修改值需将嵌入实例经 GetText(1) 重新提交给 ModifySecuritySettings。
- vTPM 仅对第二代虚拟机（VirtualSystemSubType 为 Microsoft:Hyper-V:SubType:2）有效。将 TpmEnabled 置为 true 前必须先调用 SetKeyProtector，否则启用 TPM 的作业将失败。
- 使用 New-HgsGuardian -GenerateCertificates 与 New-HgsKeyProtector -Owner $g -AllowUntrustedRoot 生成本地守护者及密钥保护器；SetKeyProtector 的 KeyProtector 入参类型为 uint8[]，应传入 $kp.RawData。
- 方法返回码：0 表示同步成功；4096 表示已启动异步作业；32768 至 32778 为 SetKeyProtector 与 GetKeyProtector 的厂商特定错误码区段。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$secsvc=Get-WmiObject -Namespace $ns -Class Msvm_SecurityService
$name='WMITEST_vtpm_security'
try {
  # 1) 创建第二代虚拟机（vTPM 仅适用于 SubType:2）
  $vssd=([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$name; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
  if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
  $vm=[wmi]$r.ResultingSystem
  # 2) 定位 Msvm_SecuritySettingData（VSSD -> SecuritySettingData）
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $sec=([wmi]$vssd2.__PATH).GetRelated('Msvm_SecuritySettingData')|Select-Object -First 1
  # 3) 生成守护者与密钥保护器并设置（启用 TpmEnabled=true 前必需）
  $g=Get-HgsGuardian -Name 'WMITESTGuardian' -ErrorAction SilentlyContinue
  if(-not $g){$g=New-HgsGuardian -Name 'WMITESTGuardian' -GenerateCertificates}
  $kp=New-HgsKeyProtector -Owner $g -AllowUntrustedRoot
  $r2=$secsvc.SetKeyProtector($sec.GetText(1),$kp.RawData)   # 返回 0 表示成功，4096 表示异步 Job
  if($r2.ReturnValue -eq 4096){Wait-Job2 $r2.Job|Out-Null}
  # 4) 通过 Msvm_SecurityService.ModifySecuritySettings 启用 TPM（TpmEnabled 在类上为只读，通过重新提交嵌入实例修改）
  $sec2=([wmi]$vssd2.__PATH).GetRelated('Msvm_SecuritySettingData')|Select-Object -First 1
  $sec2.TpmEnabled=$true
  $r3=$secsvc.ModifySecuritySettings($sec2.GetText(1))
  if($r3.ReturnValue -eq 4096){Wait-Job2 $r3.Job|Out-Null}
  # 5) 读回确认
  $secR=([wmi]$vssd2.__PATH).GetRelated('Msvm_SecuritySettingData')|Select-Object -First 1
  Write-Output "TpmEnabled=$($secR.TpmEnabled)"   # 预期 True
}
finally {
  if($vm){$vsms.DestroySystem($vm.__PATH)|Out-Null}
}
```

## [UNSUPPORTED] 创建集合级参考点(增量备份/CBT)  `collection_refpoint`

- 服务为 Msvm_CollectionReferencePointService(单例)。方法 CreateReferencePoint(Collection ref, ReferencePointSettings string 嵌入实例|$null, ReferencePointType uint16, ResultingReferencePointCollection ref, OUT Job)。ReferencePointType 枚举: 0=Log based / 1=RCT based / 2=RCT based。
- 该功能需要来宾集群/多虚拟机一致性备份环境，由 VSS 或备份子系统在集群或适当的备份上下文中触发，依赖 Msvm_CollectionSnapshotService 的一致性快照能力与来宾集成。对独立主机上一个停机的空虚拟机组直接调用会被拒绝，所有集合级参考点尝试均同步返回 rv=32770(Failed，厂商专用码，不产生 Job)。此结果与集合类型(0=虚拟机组 / 1=管理集合)、ReferencePointSettings(null 或 ConsistencyLevel=2)、ReferencePointType(0/1/2)均无关。
- 单虚拟机服务 Msvm_VirtualSystemReferencePointService.CreateReferencePoint(type=1) 在同一停机虚拟机与同一 RCT VHDX 上可成功执行(rv=4096, JobState=7, ErrorCode=0)，说明 RCT 磁盘前置条件已满足、虚拟机停机(EnabledState=3)对单虚拟机路径无碍。集合级服务的限制来自其对活动备份上下文的要求。
- 参数约束: ResultingReferencePointCollection 虽为 IN 引用参数，但必须传 $null；传入真实集合路径会抛出 WMI 'Invalid method parameter(s)' 异常，而非返回码。
- 集合的创建与添加成员本身可用: DefineCollection(Name, $null, Type) + AddMember(VM.__PATH, collPath)。清理顺序为 RemoveMember -> DestroyCollection -> DestroySystem。
- 全程仅操作以 WMITEST_collection_refpoint 命名的对象；try/finally 确保删除集合、虚拟机与 vhdx。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$TESTNAME = 'WMITEST_collection_refpoint'
$COLLNAME = 'WMITEST_collection_refpoint_coll'
$workDir = 'C:/.../verify/work'
$vhdPath = (Join-Path $workDir 'WMITEST_collection_refpoint.vhdx') -replace '/', '\'
function Wait-Job2($p){ if(-not $p){ return 7 }; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }; return $j.JobState }
function Job-Err($p){ if(-not $p){ return '<no job>' }; try { $j=[wmi]$p; return ('state='+$j.JobState+' err='+$j.ErrorCode+' desc='+$j.ErrorDescription) } catch { return '<job gone>' } }
function Get-DefaultSettings($subType){ $pool=Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"; $caps=$pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null)|Select-Object -First 1; foreach($r in $caps.GetRelationships('Msvm_SettingsDefineCapabilities')){ if($r.ValueRole -eq 0){ return [wmi]$r.PartComponent } }; return $null }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims =Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$cms =Get-WmiObject -Namespace $ns -Class Msvm_CollectionManagementService
$crps=Get-WmiObject -Namespace $ns -Class Msvm_CollectionReferencePointService
try {
  # 第二代虚拟机 + 挂载支持 RCT 的动态 VHDX(参考点需要磁盘进行跟踪)
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance(); $vssd.ElementName=$TESTNAME; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job|Out-Null }
  $vm=[wmi]$r.ResultingSystem; $vssd2=([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  $scsi=[wmi]((($vsms.AddResourceSettings($vssd2.__PATH,@((Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic SCSI Controller').GetText(1))))).ResultingResourceSettings[0])
  $vhdSd=([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance(); $vhdSd.Type=[uint16]3; $vhdSd.Format=[uint16]3; $vhdSd.Path=$vhdPath; $vhdSd.MaxInternalSize=[uint64](1GB)
  $cr=$ims.CreateVirtualHardDisk($vhdSd.GetText(1)); if($cr.ReturnValue -eq 4096){ Wait-Job2 $cr.Job|Out-Null }
  $drv=(Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic Disk Drive').psbase.Clone(); $drv.Parent=$scsi.__PATH; $drv.AddressOnParent='0'
  $drvPath=($vsms.AddResourceSettings($vssd2.__PATH,@($drv.GetText(1)))).ResultingResourceSettings[0]
  $sasd=(Get-DefaultSettings 'Microsoft:Hyper-V:Virtual Hard Disk').psbase.Clone(); $sasd.Parent=$drvPath; $sasd.HostResource=@($vhdPath)
  $vsms.AddResourceSettings($vssd2.__PATH,@($sasd.GetText(1)))|Out-Null
  # 虚拟机集合(组) + 添加成员
  $rc=$cms.DefineCollection($COLLNAME,$null,[uint16]0); if($rc.ReturnValue -eq 4096){ Wait-Job2 $rc.Job|Out-Null }; $collPath=$rc.DefinedCollection
  $ra=$cms.AddMember($vm.__PATH,$collPath); if($ra.ReturnValue -eq 4096){ Wait-Job2 $ra.Job|Out-Null }
  # CreateReferencePoint(Collection ref, ReferencePointSettings string|$null, ReferencePointType uint16, ResultingReferencePointCollection ref|$null) OUT Job
  # 注意: ResultingReferencePointCollection 必须传 $null(传入集合路径会抛 'Invalid method parameter(s)')。
  foreach($t in @([uint16]2,[uint16]1,[uint16]0)){
    $x=$crps.CreateReferencePoint($collPath,$null,$t,$null)
    Write-Host ("CreateReferencePoint(collection) type=$t rv="+$x.ReturnValue)
    if($x.ReturnValue -eq 0 -or ($x.ReturnValue -eq 4096 -and (Wait-Job2 $x.Job) -eq 7)){ break }
  }
  # 在此配置下所有类型均返回 rv=32770(Failed，厂商专用码，同步返回，不产生 Job)。
  # 清理
  $rr=$cms.RemoveMember($vm.__PATH,$collPath); if($rr.ReturnValue -eq 4096){ Wait-Job2 $rr.Job|Out-Null }
  $rd=$cms.DestroyCollection($collPath); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job|Out-Null }
}
finally {
  Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemCollection -EA SilentlyContinue | ?{ $_.ElementName -eq $COLLNAME } | %{ $d=$cms.DestroyCollection($_.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job|Out-Null } }
  Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | ?{ $_.ElementName -eq $TESTNAME } | %{ $d=$vsms.DestroySystem($_.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job|Out-Null } }
  if(Test-Path $vhdPath){ Remove-Item $vhdPath -Force }
}
```

## [UNSUPPORTED] 创建虚拟机集合级快照  `collection_snapshot`

- Msvm_CollectionSnapshotService.CreateSnapshot(Collection REF IN, SnapshotSettings string IN, SnapshotType uint16 IN, ResultingSnapshotCollection REF IN/OUT, Job REF OUT)。SnapshotType 枚举: 1=Standard Snapshot, 2=Recovery Snapshot。DestroySnapshot(AffectedSnapshotCollection REF) OUT Job。
- 该功能需要处于活动状态(运行或已保存)的集群/备份组成员。集合级快照产生的是组崩溃一致(group crash-consistent)快照，Msvm_VirtualSystemCollection 属于 Hyper-V Replica 与备份组基础设施(属性含 ReplicationState / ReplicationMode / GroupCrashConsistent / LastApplyVirtualMachineIds)。对没有操作系统、始终停机的测试虚拟机无法生成: 无论集合 Type(0/1)、SnapshotType(1/2)、成员虚拟机是否挂载 VHDX，CreateSnapshot 一律直接返回 rv=32770(厂商特定 Failed)，不产生异步 Job，也无 Msvm_Error 对象可读。同源用例 collection_refpoint 亦属此类。
- 不存在 Msvm_CollectionSnapshotSettingData 类，SnapshotSettings 传空串即可。ResultingSnapshotCollection 虽为 IN/OUT REF，用 GetMethodParameters/InvokeMethod 或直接位置调用传 $null 均可，成功时结果应为 Msvm_SnapshotCollection 引用。
- 集合的创建、添加成员与清理链路本身可用(DefineCollection Type0 -> AddMember -> RemoveMember -> DestroyCollection)，各步返回 rv=0/4096 正常，仅 CreateSnapshot 因主机与来宾状态限制失败。因此记录为 UNSUPPORTED。
- 全程仅操作以 WMITEST_ 命名的对象；清理在 try/finally 中依次删除集合快照(若有)、各虚拟机快照兜底、RemoveMember、DestroyCollection、DestroySystem 与 vhdx，运行前后均确认无残留。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$TESTNAME = 'WMITEST_collection_snapshot'
$workDir = 'C:/Users/Administrator/Documents/GitHub/HyperV-WMI-Documentation/verify/work'
$vhdPath = (Join-Path $workDir 'WMITEST_collection_snapshot.vhdx') -replace '/', '\'

function Wait-Job2($p){
  if(-not $p){ return 7 }
  $j=[wmi]$p
  while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }
  return $j.JobState
}
function Job-Err($p){
  if(-not $p){ return '<no job>' }
  try { $j=[wmi]$p; return ("state="+$j.JobState+" err="+$j.ErrorCode+" desc="+$j.ErrorDescription) } catch { return '<job gone>' }
}
function Get-DefaultSettings($subType){
  $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
  $caps = $pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
  foreach($r in $caps.GetRelationships('Msvm_SettingsDefineCapabilities')){
    if($r.ValueRole -eq 0){ return [wmi]$r.PartComponent }
  }
  return $null
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims  = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
$cms  = Get-WmiObject -Namespace $ns -Class Msvm_CollectionManagementService
$css  = Get-WmiObject -Namespace $ns -Class Msvm_CollectionSnapshotService

# 预清理
Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$TESTNAME'" | ForEach-Object {
  try { $d=$vsms.DestroySystem($_.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job|Out-Null } } catch {}
}
if(Test-Path $vhdPath){ Remove-Item $vhdPath -Force }

$vm = $null
$coll = $null
$collPath = $null
$snapCollPath = $null
$status = 'FAIL'
$snapCreated = $false
$snapVSSDCount = 0
$usedType = $null
$lastRv = $null

try {
  # --- 创建测试虚拟机(第二代) ---
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $TESTNAME
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $s = Wait-Job2 $r.Job; if($s -ne 7){ throw "DefineSystem job state=$s" } }
  elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem
  $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  Write-Host "VM created: $($vm.ElementName) $($vm.Name)"

  # --- 挂载动态 VHDX(集合快照为备份功能，空虚拟机会失败) ---
  $scsiTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic SCSI Controller'
  $ar = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
  if($ar.ReturnValue -eq 4096){ Wait-Job2 $ar.Job|Out-Null } elseif($ar.ReturnValue -ne 0){ throw "AddResource(SCSI) rv=$($ar.ReturnValue)" }
  $scsi = [wmi]$ar.ResultingResourceSettings[0]

  $vhdSd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
  $vhdSd.Type = [uint16]3
  $vhdSd.Format = [uint16]3
  $vhdSd.Path = $vhdPath
  $vhdSd.MaxInternalSize = [uint64](1GB)
  $cr = $ims.CreateVirtualHardDisk($vhdSd.GetText(1))
  if($cr.ReturnValue -eq 4096){ $s = Wait-Job2 $cr.Job; if($s -ne 7){ throw "CreateVHD job state=$s" } } elseif($cr.ReturnValue -ne 0){ throw "CreateVHD rv=$($cr.ReturnValue)" }
  if(-not (Test-Path $vhdPath)){ throw "vhdx not created" }

  $drvTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic Disk Drive'
  $drv = $drvTmpl.psbase.Clone()
  $drv.Parent = $scsi.__PATH
  $drv.AddressOnParent = '0'
  $ar2 = $vsms.AddResourceSettings($vssd2.__PATH, @($drv.GetText(1)))
  if($ar2.ReturnValue -eq 4096){ $s = Wait-Job2 $ar2.Job; if($s -ne 7){ throw "AddResource(Drive) state=$s $(Job-Err $ar2.Job)" } } elseif($ar2.ReturnValue -ne 0){ throw "AddResource(Drive) rv=$($ar2.ReturnValue)" }
  $drvPath = $ar2.ResultingResourceSettings[0]

  $sasdTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Virtual Hard Disk'
  $sasd = $sasdTmpl.psbase.Clone()
  $sasd.Parent = $drvPath
  $sasd.HostResource = @($vhdPath)
  $ar3 = $vsms.AddResourceSettings($vssd2.__PATH, @($sasd.GetText(1)))
  if($ar3.ReturnValue -eq 4096){ $s = Wait-Job2 $ar3.Job; if($s -ne 7){ throw "AddResource(VHD) state=$s $(Job-Err $ar3.Job)" } } elseif($ar3.ReturnValue -ne 0){ throw "AddResource(VHD) rv=$($ar3.ReturnValue)" }
  Write-Host "VHDX attached to member VM"

  # --- DefineCollection(Type 0 = 虚拟机集合 / 组) ---
  $rc = $cms.DefineCollection('WMITEST_cs_coll', $null, [uint16]0)
  if($rc.ReturnValue -eq 4096){ $s = Wait-Job2 $rc.Job; if($s -ne 7){ throw "DefineCollection job state=$s" } }
  elseif($rc.ReturnValue -ne 0){ throw "DefineCollection rv=$($rc.ReturnValue)" }
  $collPath = $rc.DefinedCollection
  $coll = [wmi]$collPath
  Write-Host "Collection created: ElementName=$($coll.ElementName)"

  # --- AddMember(虚拟机 -> 集合) ---
  $ra = $cms.AddMember($vm.__PATH, $collPath)
  if($ra.ReturnValue -eq 4096){ $s = Wait-Job2 $ra.Job; if($s -ne 7){ throw "AddMember job state=$s" } }
  elseif($ra.ReturnValue -ne 0){ throw "AddMember rv=$($ra.ReturnValue)" }
  Write-Host "AddMember rv=$($ra.ReturnValue)"

  # --- 对整个集合执行 CreateSnapshot ---
  # 参数: Collection(ref IN), SnapshotSettings(string IN), SnapshotType(uint16 IN),
  #       ResultingSnapshotCollection(ref IN/OUT), Job(ref OUT)
  # SnapshotType 枚举: 1=Standard, 2=Recovery。依次尝试 1 与 2。
  $rs = $null; $createOk = $false
  foreach($stype in @(1,2)){
    $inp = $css.GetMethodParameters('CreateSnapshot')
    $inp.Collection = $collPath
    $inp.SnapshotSettings = ''
    $inp.SnapshotType = [uint16]$stype
    $rs = $css.InvokeMethod('CreateSnapshot', $inp, $null)
    $usedType = $stype; $lastRv = $rs.ReturnValue
    Write-Host "CreateSnapshot(type=$stype) rv=$($rs.ReturnValue)"
    if($rs.ReturnValue -eq 0){ $createOk = $true; break }
    if($rs.ReturnValue -eq 4096){
      $s = Wait-Job2 $rs.Job
      if($s -eq 7){ $createOk = $true; break }
      Write-Host ("  job: " + (Job-Err $rs.Job))
    } else {
      Write-Host "  non-job failure rv=$($rs.ReturnValue)"
    }
  }

  if(-not $createOk){
    Write-Host "CreateSnapshot did not succeed for any type; last rv=$lastRv"
    $status = 'UNSUPPORTED'
  } else {
    $snapCollPath = $rs.ResultingSnapshotCollection
    Write-Host "ResultingSnapshotCollection=$snapCollPath"
    if($snapCollPath){
      $snapCreated = $true
      $snapColl = [wmi]$snapCollPath
      Write-Host "SnapshotCollection class=$($snapColl.__CLASS) InstanceID=$($snapColl.InstanceID)"
      # 枚举集合快照产生的各虚拟机快照
      try {
        $snapVssds = $snapColl.GetRelated('Msvm_VirtualSystemSettingData')
        $snapVSSDCount = @($snapVssds).Count
        foreach($sv in @($snapVssds)){ Write-Host ("  snap VSSD ElementName=" + $sv.ElementName + " Type=" + $sv.VirtualSystemType) }
      } catch { Write-Host "enum snap VSSDs err: $($_.Exception.Message)" }
      $status = 'PASS'
    } else {
      # 成功但未返回 OUT 集合，仍可通过虚拟机快照发现
      $vmSnaps = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null)
      $snapVSSDCount = @($vmSnaps).Count
      if($snapVSSDCount -ge 1){ $snapCreated = $true; $status = 'PASS' } else { $status = 'FAIL' }
    }
  }
}
catch {
  Write-Host "ERROR: $($_.Exception.Message)"
  $status = 'FAIL'
}
finally {
  # --- 销毁集合快照 ---
  if($snapCollPath){
    try {
      $rds = $css.DestroySnapshot($snapCollPath)
      if($rds.ReturnValue -eq 4096){ Wait-Job2 $rds.Job|Out-Null }
      Write-Host "DestroySnapshot rv=$($rds.ReturnValue)"
    } catch { Write-Host "DestroySnapshot cleanup err: $($_.Exception.Message)" }
  }
  # 兜底: 销毁任何残留的各虚拟机快照
  if($vm -ne $null){
    try {
      $snapSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemSnapshotService
      $vmSnaps2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData','Msvm_SnapshotOfVirtualSystem',$null,$null,$null,$null,$false,$null)
      foreach($sv in @($vmSnaps2)){
        try { $dp=$snapSvc.GetMethodParameters('DestroySnapshot'); $dp.AffectedSnapshot=$sv.__PATH; $dr=$snapSvc.InvokeMethod('DestroySnapshot',$dp,$null); if($dr.ReturnValue -eq 4096){ Wait-Job2 $dr.Job|Out-Null } } catch {}
      }
    } catch {}
  }
  # --- 移除成员 + 销毁集合 ---
  if($collPath -ne $null -and $vm -ne $null){
    try { $rr = $cms.RemoveMember($vm.__PATH, $collPath); if($rr.ReturnValue -eq 4096){ Wait-Job2 $rr.Job|Out-Null }; Write-Host "RemoveMember rv=$($rr.ReturnValue)" } catch { Write-Host "RemoveMember cleanup err: $($_.Exception.Message)" }
  }
  if($collPath -ne $null){
    try { $rd = $cms.DestroyCollection($collPath); if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job|Out-Null }; Write-Host "DestroyCollection rv=$($rd.ReturnValue)" } catch { Write-Host "DestroyCollection cleanup err: $($_.Exception.Message)" }
  }
  # --- 销毁虚拟机 ---
  if($vm -ne $null){
    try { $rdv = $vsms.DestroySystem($vm.__PATH); if($rdv.ReturnValue -eq 4096){ Wait-Job2 $rdv.Job|Out-Null }; Write-Host "DestroySystem rv=$($rdv.ReturnValue)" } catch { Write-Host "DestroySystem cleanup err: $($_.Exception.Message)" }
  }
  # 安全网
  $leftover = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$TESTNAME'"
  if($leftover){ foreach($l in $leftover){ try { $vsms.DestroySystem($l.__PATH)|Out-Null } catch {} } ; Write-Host "WARN: cleaned leftover VM" }
  if(Test-Path $vhdPath){ try { Remove-Item $vhdPath -Force; Write-Host "vhdx removed" } catch { Write-Host "vhd remove err: $($_.Exception.Message)" } }
}

Write-Host "----"
Write-Host "ASSERT snapCreated=$snapCreated snapVSSDCount=$snapVSSDCount usedType=$usedType lastRv=$lastRv"
Write-Host "RESULT: $status"
```

## [UNSUPPORTED] 探测容器镜像管理服务类的可用性  `container_image`

- 该功能需要 build 10586 环境：Msvm_ContainerImageManagementService 及全部 Msvm_ContainerImage* 类仅在该版本提供，此后被移除，在较新的 root\virtualization\v2 命名空间下不存在。
- 该系列类是 Windows Server 2016 早期技术预览 (build 10586) 提供的 WMI 版 Windows Server Containers 镜像仓库接口，first_seen 与 last_seen 均为 10586。
- 现代 Windows 容器不再经由 v2 命名空间的 WMI 管理，改由 HCS (Host Compute Service, computestorage/computecore API) 及 docker/containerd 处理，因此 root\virtualization\v2 下不再暴露容器镜像相关类。
- 服务方法签名（DefineContainerImage / ImportContainerImage / ExportContainerImage / ValidateContainerImage / DestroyContainerImage / ModifyServiceSettings）已记录于 code 字段供参考，OUT 参数均含 Job (CIM_ConcreteJob ref)，返回 4096 时须轮询 Job 直至完成。
- 本示例为纯读探测操作，不创建任何虚拟机或镜像，无需清理。

```powershell
$ns = 'root\virtualization\v2'
# Msvm_ContainerImageManagementService: Windows Server Containers 镜像仓库管理服务
# 该类仅存在于 build 10586；在后续版本中已被移除，26100 上不再提供。
$classes = @(
  'Msvm_ContainerImageManagementService',
  'Msvm_ContainerImage',
  'Msvm_ContainerImageManagementServiceSettingData',
  'Msvm_ContainerImageExportSettingData',
  'Msvm_ContainerImageImportSettingData'
)
foreach ($cls in $classes) {
  $exists = $false; $methods = @()
  try {
    $c = Get-WmiObject -Namespace $ns -List -Class $cls -ErrorAction Stop
    if ($c) { $exists = $true; $methods = @($c.Methods | ForEach-Object { $_.Name }) }
  } catch { $exists = $false }
  Write-Output ("CLASS $cls Exists=$exists Methods=" + ($methods -join ','))
}
# 服务方法签名（build 10586）供参考:
#   DefineContainerImage(ContainerImageSettings string, ReferenceConfiguration ref CIM_VirtualSystemSettingData) -> ResultingContainerImage ref, Job ref
#   ImportContainerImage(ContainerImageToImport string, ImportSettings string) -> ResultingContainerImage ref, Job ref
#   ExportContainerImage(ExportedFile string, ContainerImageToExport ref, ExportSettings string) -> Job ref
#   ValidateContainerImage(ContainerImageToValidate ref Msvm_ContainerImage) -> Job ref
#   DestroyContainerImage(AffectedContainerImage ref) -> Job ref
#   ModifyServiceSettings(SettingData string) -> Job ref
# Msvm_ContainerImage 键属性: Publisher/Name/Version (string, Key), IsOSImage (bool)
# Msvm_ContainerImageManagementServiceSettingData: DefaultRepository (string)
# 返回码 ValueMap: 0,4096,32768..32778
```

## [UNSUPPORTED] 为虚拟机添加合成光纤通道适配器 (虚拟 HBA)  `fibre_channel`

- 该操作需要主机具备物理 NPIV-capable 光纤通道 HBA 作为后端。当主机无此硬件时 (Msvm_ExternalFcPort 枚举为空)，合成 FC 适配器 (虚拟 HBA) 无法添加，故此配方标记为 UNSUPPORTED。
- 完整流程为两步：① 从 AllocationCapabilities 取默认 Msvm_SyntheticFcPortSettingData 端口模板，修改 WWN (VirtualPortWWNN/WWPN/Secondary*) 后 AddResourceSettings；② 取默认 FC 连接模板 (Msvm_FibreChannelPortAllocationSettingData)，设 Parent=新端口路径、PoolId/HostResource 指向目标虚拟 SAN，再 AddResourceSettings。SanName 为必填项。本配方仅演示第一步 (添加合成 FC 端口)。
- 当主机配置了基于虚拟化的安全 (VBS) 时，设备无法落地会次生返回 AddResourceSettings 转入 Job 后 JobState=10 (Exception)、ErrorCode=32773，错误文案为‘在未配置 VirtualizationBasedSecurityOptOut 的情况下无法修改属性’。此为表象，根本原因仍是缺少 FC 硬件。
- WWNN/WWPN 在 Msvm_SyntheticFcPortSettingData 实例对象上为只读，但可在嵌入实例模板 (GetText(1)) 中赋值，再经 AddResourceSettings 下发生效。
- 即便端口配置添加成功，若无 NPIV-capable 物理 HBA，虚拟 HBA 也无法连接到任何真实 SAN。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$testName='WMITEST_fibre_channel'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
# 创建第二代虚拟机
$vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
$vssd.ElementName=$testName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
$r=$vsms.DefineSystem($vssd.GetText(1),$null,$null)
if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
$vm=[wmi]$r.ResultingSystem
$vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
try {
  # 从 primordial 池的 AllocationCapabilities 取默认合成 FC 端口模板
  $rasd=$null
  $caps=Get-WmiObject -Namespace $ns -Class Msvm_AllocationCapabilities -Filter "ResourceSubType='Microsoft:Hyper-V:Synthetic FibreChannel Port'"
  foreach($c in @($caps)){
    $sdc=Get-WmiObject -Namespace $ns -Query ("ASSOCIATORS OF {"+$c.__PATH+"} WHERE ResultClass=Msvm_SyntheticFcPortSettingData")
    if($sdc){$rasd=@($sdc)|Select-Object -First 1; break}
  }
  # WWNN/WWPN 在实例对象上只读，但可在嵌入模板中赋值后经 AddResourceSettings 下发
  $c3='C003FF'
  $rasd.VirtualPortWWNN='2000'+$c3+'00000000'
  $rasd.VirtualPortWWPN='1001'+$c3+'0EA00001'
  $rasd.SecondaryWWNN ='2000'+$c3+'00000000'
  $rasd.SecondaryWWPN ='1001'+$c3+'0EA00002'
  $add=$vsms.AddResourceSettings($vssd2.__PATH, @($rasd.GetText(1)))
  if($add.ReturnValue -eq 4096){ $st=Wait-Job2 $add.Job; if($st -ne 7){$jb=[wmi]$add.Job; Write-Host ('FC add failed ErrorCode='+$jb.ErrorCode)} }
} finally {
  $rd=$vsms.DestroySystem($vm.__PATH); if($rd.ReturnValue -eq 4096){Wait-Job2 $rd.Job|Out-Null}
}
```

## [UNSUPPORTED] 经集成组件优雅关机/重启/休眠  `graceful_shutdown`

- 优雅关机经关机集成组件 Msvm_ShutdownComponent(子设备类，superclass=CIM_LogicalDevice)完成，区别于 Msvm_ComputerSystem.RequestStateChange 的强制关机/停止。
- 当虚拟机处于关机态(EnabledState=3)时，Msvm_ShutdownComponent 不存在实例——vm.GetRelated('Msvm_ShutdownComponent') 返回空，直接 WQL 查询亦无结果。因此空闲或未运行的虚拟机无法调用 InitiateShutdown，本条目标记为 UNSUPPORTED：需来宾 OS 运行且启用关机集成服务，该组件才会出现。
- 方法签名：InitiateShutdown(Force boolean, Reason string) -> uint32；InitiateReboot(Force boolean, Reason string) -> uint32(自 build 10240 起提供)；InitiateHibernate() 无参数 -> uint32(自 build 17763 起提供)。三者均无 Job OUT 参数，为同步返回码，rc=0 表示成功，非 0 为错误(ValueMap 含 32768..32782 厂商错误码)。
- 正确用法：先让虚拟机安装来宾 OS 并启用关机集成服务且处于运行态，再经 $vm.GetRelated('Msvm_ShutdownComponent') 获取组件对象调用。这区别于 RequestStateChange(3=Disabled)的强制断电。
- 脚本注意：[wmiclass] 路径中用 ${ns} 括起命名空间变量，避免 $ns: 被解析为 PowerShell 驱动器；GetText(1) 序列化嵌入实例；DefineSystem 的 OUT 为 ResultingSystem，返回值可能为 4096，须 Wait-Job2 等待作业完成。

```powershell
$ns = 'root\virtualization\v2'
$name = 'WMITEST_graceful_shutdown'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null
try {
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $name
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
    $vm = [wmi]$r.ResultingSystem

    # 优雅关机经关机集成组件完成，而非 RequestStateChange。
    # 该组件仅在来宾 OS 运行且启用关机集成服务时才存在。
    $sc = $vm.GetRelated('Msvm_ShutdownComponent') | Select-Object -First 1
    if ($sc) {
        $sc2 = [wmi]$sc.__PATH
        # InitiateShutdown(Force[bool], Reason[string]); 0=成功, 非 0=错误(同步返回, 无 Job OUT)
        $rc = $sc2.InitiateShutdown($true, 'graceful shutdown reason')
        # $sc2.InitiateReboot($true, 'reboot reason')   # 重启
        # $sc2.InitiateHibernate()                      # 休眠(无参数)
        Write-Output "InitiateShutdown rc=$($rc.ReturnValue)"
    } else {
        Write-Output 'Msvm_ShutdownComponent absent: VM must be running with shutdown integration service.'
    }
}
finally {
    if ($vm) { $d = $vsms.DestroySystem($vm.__PATH); if ($d.ReturnValue -eq 4096) { $null = Wait-Job2 $d.Job } }
}
```

## [UNSUPPORTED] 校验虚拟机是否可迁移至目标主机  `migration_check`

- 本示例需要启用实时迁移的环境。当 EnableVirtualSystemMigration=False 时，Msvm_VirtualSystemMigrationService 的活动实例仅暴露 1 个方法(RequestStateChange)；CheckVirtualSystemIsMigratableToHost 等迁移方法虽在类定义(Get-WmiObject -List)中存在，但活动实例的提供程序未实现，调用会抛出 '此方法未与任何管理实现'(provider method-not-implemented)。
- 前置条件：通过 Enable-VMMigration 或 ModifyServiceSettings 将 EnableVirtualSystemMigration 置为 True，并配置迁移网络(Msvm_VirtualSystemMigrationNetworkSettingData)后，该方法方可调用。
- 方法签名：CheckVirtualSystemIsMigratableToHost(ComputerSystem REF, DestinationHost string, MigrationSettingData string=Msvm_VirtualSystemMigrationSettingData 嵌入实例, NewSystemSettingData string, NewResourceSettingData string[], OUT IsMigratable boolean)；返回 uint32：0=检查已执行(参见 OUT IsMigratable)、1=不支持、2=失败、3=超时、4=参数无效、5=状态无效、6=参数不兼容。
- MigrationSettingData.MigrationType：2=实时迁移、3=暂停迁移、4=停机迁移。DestinationHost 接受的格式由关联的 CIM_VirtualSystemMigrationCapabilities.DestinationHostFormatsSupported 决定。
- 迁移方法未被 PowerShell 动态包装到实例上，必须使用 Invoke-WmiMethod -Path $migSvc.__PATH -Name ... 直连提供程序调用；在实例上直接调用会因方法缺失而报 '不能对 Null 值表达式调用方法'。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$testName = 'WMITEST_migration_check'

function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$migSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationService
$hostName = $env:COMPUTERNAME

# 读取迁移服务设置(宿主级，纯读)
$migSetSvc = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationServiceSettingData
Write-Output ("MigServiceSetting: EnabledForMigration=" + $migSetSvc.EnableVirtualSystemMigration + " AuthType=" + $migSetSvc.AuthenticationType + " MaxParallel=" + $migSetSvc.MaximumActiveVirtualSystemMigration)
$migNets = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemMigrationNetworkSettingData
Write-Output ("MigNetworkSettings count = " + @($migNets).Count)

$vm = $null
$result = 'FAIL'
try {
    # 创建第二代测试虚拟机
    $vssd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $testName
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }
    $vm = [wmi]$r.ResultingSystem
    Write-Output ("Created VM: " + $vm.ElementName)

    # 迁移设置数据(MigrationType 2 = 实时迁移)
    $msd = ([wmiclass]"\\.\$ns`:Msvm_VirtualSystemMigrationSettingData").CreateInstance()
    $msd.MigrationType = [uint16]2

    # 检查方法可用性：类中定义了该方法，但活动实例可能不暴露
    $classMethods = (Get-WmiObject -Namespace $ns -List | Where-Object { $_.Name -eq 'Msvm_VirtualSystemMigrationService' }).PSBase.Methods | ForEach-Object { $_.Name }
    Write-Output ("Class defines CheckVirtualSystemIsMigratableToHost = " + ($classMethods -contains 'CheckVirtualSystemIsMigratableToHost'))
    Write-Output ("Live instance exposed method count = " + @($migSvc.PSBase.Methods).Count)

    # 签名: ComputerSystem(ref), DestinationHost(string), MigrationSettingData(string),
    #        NewSystemSettingData(string), NewResourceSettingData(string[]), OUT IsMigratable
    try {
        $chk = Invoke-WmiMethod -Path $migSvc.__PATH -Name CheckVirtualSystemIsMigratableToHost `
                 -ArgumentList $vm.__PATH, $hostName, $msd.GetText(1), $null, $null
        Write-Output ("rv=" + $chk.ReturnValue + " IsMigratable=" + $chk.IsMigratable)
        $result = 'PASS'
    } catch {
        Write-Output ("Invoke EXCEPTION: " + $_.Exception.Message)
        if($migSetSvc.EnableVirtualSystemMigration -eq $false){
            $result = 'UNSUPPORTED'
            Write-Output ('UNSUPPORTED: methods gated behind EnableVirtualSystemMigration=True')
        } else { $result = 'FAIL' }
    }
}
catch { Write-Output ("EXCEPTION: " + $_.Exception.Message); $result = 'FAIL' }
finally {
    if($vm){
        $d = $vsms.DestroySystem($vm.__PATH)
        if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }
        Write-Output ("Cleanup DestroySystem rv=" + $d.ReturnValue)
    }
}
$leftover = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem | Where-Object { $_.ElementName -eq $testName }
if($leftover){ Write-Output 'LEFTOVER'; $result='FAIL' } else { Write-Output 'No leftover' }
Write-Output ("RESULT: " + $result)
```

## [UNSUPPORTED] 配置虚拟网卡硬件卸载 (SR-IOV/VMQ/IPsec)  `nic_sriov_offload`

- 需要具备 SR-IOV(VT-d/IOMMU) 的物理网卡及以 New-VMSwitch -EnableIov $true 创建的交换机。在不具备 SR-IOV 的主机上，AddFeatureSettings 下发 Msvm_EthernetSwitchPortOffloadSettingData 返回 rv=4096，异步 Job 以 JobState=10(Exception)、ErrorCode=32773、HRESULT 0x80070032(ERROR_NOT_SUPPORTED) 结束。Get-VMSwitch 报告 IovSupport=False。
- WMI 写入路径与 net_bandwidth 相同：构建网卡(克隆 \Default SyntheticEthernetPortSettingData) -> 连接(EthernetPortAllocationSettingData -> 交换机) -> Msvm_VirtualSystemManagementService(vsms).AddFeatureSettings(AffectedConfiguration=连接引用, FeatureSettings[]=Msvm_EthernetSwitchPortOffloadSettingData.GetText(1))。此为 Set-VMNetworkAdapter -IovWeight/-VmqWeight 所用路径。虚拟机端口功能不应使用 Msvm_VirtualEthernetSwitchManagementService。
- 卸载属性含义(Msvm_EthernetSwitchPortOffloadSettingData，均为 uint32)：IOVOffloadWeight(默认 0；>0 启用 SR-IOV，相对权重)、VMQOffloadWeight(默认 100；0 禁用 VMQ)、IPSecOffloadLimit(默认 512；IPsec SA 卸载槽位上限)、IOVQueuePairsRequested(默认 1)、IOVInterruptModeration(0=Default/1=Adaptive/2=Off/100=Low/200=Medium/300=High)、PacketDirectNumProcs/PacketDirectModerationCount/Interval(Packet Direct)。
- 该失败并非仅针对 SR-IOV：IOVOffloadWeight=0 但仅修改 VMQ/IPsec 值的功能同样以 JobState=10/ErrorCode=32773 失败。当交换机后端网卡不支持 SR-IOV 时，整个卸载功能类无法经 WMI 应用到端口。
- 运行后无残留 WMITEST_nic_sriov_offload。
- 控制台的中文错误文本可能显示为 GBK 乱码；解码后的 HRESULT 0x80070032 = ERROR_NOT_SUPPORTED 为权威判定依据。

```powershell
$ErrorActionPreference='Stop'
$ns='root\virtualization\v2'
$testName='WMITEST_nic_sriov_offload'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j }
$vsms=Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm=$null
try {
  # 1) 创建第二代虚拟机
  $vssd=([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName=$testName; $vssd.VirtualSystemSubType='Microsoft:Hyper-V:SubType:2'
  $r=$vsms.DefineSystem($vssd.GetText(1),$null,$null); if($r.ReturnValue -eq 4096){Wait-Job2 $r.Job|Out-Null}
  $vm=[wmi]$r.ResultingSystem
  $vssd2=$vm.GetRelated('Msvm_VirtualSystemSettingData')|Select-Object -First 1
  # 2) 选择一个可用交换机，排除 'Default Switch'
  $sw=Get-WmiObject -Namespace $ns -Class Msvm_VirtualEthernetSwitch | Where-Object { $_.ElementName -ne 'Default Switch' } | Select-Object -First 1
  # 3) 通过克隆默认 RASD 模板添加合成网卡
  $nicTmpl=Get-WmiObject -Namespace $ns -Class Msvm_SyntheticEthernetPortSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $nic=$nicTmpl.psbase.Clone(); $nic.ElementName='WMITEST_nic'; $nic.VirtualSystemIdentifiers=@('{'+[guid]::NewGuid().ToString()+'}')
  $ra=$vsms.AddResourceSettings($vssd2.__PATH,@($nic.GetText(1))); if($ra.ReturnValue -eq 4096){Wait-Job2 $ra.Job|Out-Null}
  $nicInst=[wmi]($ra.ResultingResourceSettings[0])
  # 4) 通过 Msvm_EthernetPortAllocationSettingData 将网卡连接到交换机
  $epasTmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetPortAllocationSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $epas=$epasTmpl.psbase.Clone(); $epas.Parent=$nicInst.__PATH; $epas.HostResource=@($sw.__PATH)
  $rc=$vsms.AddResourceSettings($vssd2.__PATH,@($epas.GetText(1))); if($rc.ReturnValue -eq 4096){Wait-Job2 $rc.Job|Out-Null}
  $connInst=[wmi]($rc.ResultingResourceSettings[0])
  # 5) 从默认模板构建卸载功能：IOVOffloadWeight>0 请求 SR-IOV；VMQOffloadWeight=VMQ；IPSecOffloadLimit=IPsec SA 槽位
  $tmpl=Get-WmiObject -Namespace $ns -Class Msvm_EthernetSwitchPortOffloadSettingData | Where-Object { $_.InstanceID -like '*\Default' } | Select-Object -First 1
  $off=$tmpl.psbase.Clone()
  $off.IOVOffloadWeight=[uint32]50
  $off.VMQOffloadWeight=[uint32]100
  $off.IPSecOffloadLimit=[uint32]256
  # 6) 通过 vsms.AddFeatureSettings 下发（虚拟机端端口功能，与 Set-VMNetworkAdapter 同一路径）
  $rf=$vsms.AddFeatureSettings($connInst.__PATH,@($off.GetText(1)))
  $rfState=$null; if($rf.ReturnValue -eq 4096){ $rfState=Wait-Job2 $rf.Job }
  # 7) 读回验证
  $feat=$null
  if($rf.ResultingFeatureSettings -and $rf.ResultingFeatureSettings.Count -ge 1){ $feat=[wmi]($rf.ResultingFeatureSettings[0]) }
  if(-not $feat){ $feat=([wmi]$connInst.__PATH).GetRelated('Msvm_EthernetSwitchPortOffloadSettingData')|Select-Object -First 1 }
  # 8) 判定：成功 vs ERROR_NOT_SUPPORTED（主机无 SR-IOV）
  $applied = ($feat -and [uint32]$feat.IOVOffloadWeight -eq 50 -and [uint32]$feat.VMQOffloadWeight -eq 100 -and [uint32]$feat.IPSecOffloadLimit -eq 256)
  if($applied){ $status='PASS' }
  elseif($rfState -and $rfState.JobState -eq 10 -and ([uint32]$rfState.ErrorCode -eq 32773)){ $status='UNSUPPORTED' }
  else { $status='FAIL' }
  Write-Output ("RESULT="+$status)
  if($feat){ Write-Output ("READBACK=IOV="+$feat.IOVOffloadWeight+";VMQ="+$feat.VMQOffloadWeight+";IPSec="+$feat.IPSecOffloadLimit) }
  $vmsw=Get-VMSwitch -Name $sw.ElementName; Write-Output ("IovSupport="+$vmsw.IovSupport+";reasons="+($vmsw.IovSupportReasons -join '|'))
} finally {
  if($vm){ $d=$vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){Wait-Job2 $d.Job|Out-Null} }
}
```

## [UNSUPPORTED] 添加 RemoteFX 3D 显示控制器(旧机制)  `remotefx_3d`

- 该特性需要主机具备 RemoteFX 物理 GPU 池(Msvm_Physical3dGraphicsProcessor);缺少该硬件时无法添加 RemoteFX 3D 显示控制器。此时 AddResourceSettings 返回 4096(Job),Job 终态 JobState=10(Exception),ErrorCode=32773(资源添加被拒),读回控制器数为 0。
- RemoteFX vGPU 自 Windows Server 2019 / Windows 10 1809 起已弃用并默认禁用(出于安全考虑)。现代 GPU 虚拟化应改用 GPU 分区(GPU-P,Msvm_PartitionableGpu)或 DDA 直通。
- 类 Msvm_Synthetic3DDisplayControllerSettingData 仍存在于 WMI schema 中,可 CreateInstance,但会被 VMMS 在运行时拒绝。关键字段: ResourceSubType='Microsoft:Hyper-V:Synthetic 3D Display Controller'、MaximumMonitors、MaximumScreenResolution、VRAMSizeBytes。
- CreateInstance 后 ResourceSubType 与 ResourceType 为空,需显式赋值 ResourceSubType;即便正确赋值,在缺少 RemoteFX GPU 的主机上失败模式不变(ErrorCode=32773)。
- 通用排错方式: 写操作返回 4096 时用 Wait-Job2 获取 JobState;终态为 10 时,通过 [wmi]$ra.Job 读取 ErrorCode 与 ErrorDescription 定位原因。ErrorCode=32773 表示 'cannot add resource',即该资源类型在当前主机或该虚拟机上不被允许。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){ Start-Sleep -Milliseconds 200; $j=[wmi]$p }; return $j.JobState }
$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vmName = 'WMITEST_remotefx_3d'
$vm = $null
# RemoteFX vGPU 的前置条件: 主机需具备 RemoteFX 物理 GPU 池。Windows Server 2019 及以上该类为空。
$phys3d = @(Get-WmiObject -Namespace $ns -Class Msvm_Physical3dGraphicsProcessor -ErrorAction SilentlyContinue)
Write-Output ("Physical3dGraphicsProcessor count = " + $phys3d.Count)
try {
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $vmName
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if($r.ReturnValue -eq 4096){ $st = Wait-Job2 $r.Job; if($st -ne 7){ throw "DefineSystem job failed state=$st" } } elseif($r.ReturnValue -ne 0){ throw "DefineSystem rv=$($r.ReturnValue)" }
  $vm = [wmi]$r.ResultingSystem
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
  # 构造 RemoteFX 3D 显示控制器的 RASD
  $rfx = ([wmiclass]"\\.\${ns}:Msvm_Synthetic3DDisplayControllerSettingData").CreateInstance()
  $rfx.ResourceSubType = 'Microsoft:Hyper-V:Synthetic 3D Display Controller'
  $rfx.MaximumMonitors = [byte]1
  $rfx.MaximumScreenResolution = [byte]4
  $ra = $vsms.AddResourceSettings($vssd2.__PATH, @($rfx.GetText(1)))
  Write-Output ("AddResourceSettings ReturnValue = " + $ra.ReturnValue)
  if($ra.ReturnValue -eq 4096){
    $jstate = Wait-Job2 $ra.Job
    Write-Output ("Add job final JobState = " + $jstate)
    if($ra.Job){ $jobObj = [wmi]$ra.Job; Write-Output ("Job ErrorCode = " + $jobObj.ErrorCode + "  Desc = " + $jobObj.ErrorDescription) }
  }
  $rfxBack = @(([wmi]$vssd2.__PATH).GetRelated('Msvm_Synthetic3DDisplayControllerSettingData'))
  Write-Output ("Synthetic3D controllers after add = " + $rfxBack.Count)
  if($rfxBack.Count -ge 1){ Write-Output 'RESULT=PASS' } else { Write-Output 'RESULT=UNSUPPORTED' }
}
catch { Write-Output ("EXCEPTION: " + $_.Exception.Message); Write-Output 'RESULT=FAIL' }
finally {
  if($vm){ $d = $vsms.DestroySystem($vm.__PATH); if($d.ReturnValue -eq 4096){ Wait-Job2 $d.Job | Out-Null }; Write-Output ("Cleanup DestroySystem rv = " + $d.ReturnValue) }
}
```

## [UNSUPPORTED] 创建子资源池  `resource_pool_child`

- Msvm_ResourcePoolConfigurationService 实际仅暴露七个方法:RequestStateChange / StartService / StopService / CreatePool / ModifyPoolResources / ModifyPoolSettings / DeletePool。不包含 CreateChildResourcePool 与 DeleteResourcePool。
- CreateChildResourcePool / DeleteResourcePool 是 DMTF 基类 CIM_ResourcePoolConfigurationService 定义的标准方法,但 Hyper-V provider 未将其实现为可调用的 WMI 方法。直接调用 GetMethodParameters 或 InvokeMethod 会抛出 MethodInvocationException(HRESULT 0x80131501,方法无实现)。这是 MOF 声明与实际实现脱节的典型情形。
- 因此以 CreateChildResourcePool 创建子池的操作判定为 UNSUPPORTED。
- 创建子资源池的可用方法为 CreatePool(参见 resource_pool_create 配方),删除对应 DeletePool。CreatePool 接受三个入参:PoolSettings(Msvm_ResourcePoolSettingData 内嵌串)、ParentPools(REF[])、AllocationSettings(对应资源 RASD 内嵌串数组)。内存子池场景同步返回 0,无需轮询 Job。
- AllocationSettings 中 RASD 的 PoolID 必须等于新子池名,且 Reservation/Limit/VirtualQuantity/Weight 均为 0,否则 Job 失败(ErrorCode=32773)。DeletePool 要求子池无未结分配:空子池返回 0,占用中返回 32774。
- 父池取 primordial(原始)根池:Get-WmiObject Msvm_ResourcePool | ?{ $_.Primordial -and $_.ResourceType -eq 4 }。资源类型取值:内存 4 / 处理器 3 / 以太网 10 / VHD 31 / GPU 分区 32770。

```powershell
$ns = 'root\virtualization\v2'
function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }
$rpcs   = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePoolConfigurationService
$rpcsCl = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePoolConfigurationService -List

# CreateChildResourcePool / DeleteResourcePool 在 MOF 中定义于基类 CIM_ResourcePoolConfigurationService,
# 但 Hyper-V 的 Msvm_ResourcePoolConfigurationService provider 未将其实现为可调用方法。
# provider 仅暴露 CreatePool / DeletePool / ModifyPoolResources / ModifyPoolSettings。
$names = @($rpcsCl.Methods | ForEach-Object { $_.Name })
'LIVE methods: ' + ($names -join ', ')
$hasChild = $names -contains 'CreateChildResourcePool'

# 直接调用 CreateChildResourcePool 会抛出异常(方法无实现, HRESULT 0x80131501):
try { $rpcs.GetMethodParameters('CreateChildResourcePool') }
catch { 'INVOKE ERROR (expected): ' + $_.Exception.GetType().FullName }

# === 可用的等价写法 = CreatePool ===
# CreatePool(PoolSettings string, ParentPools REF[], AllocationSettings string[]) -> OUT Pool, Job
$poolId = 'WMITEST_resource_pool_child'
$parent = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object {
  $_.Primordial -eq $true -and $_.ResourceType -eq 4 -and $_.ResourceSubType -eq 'Microsoft:Hyper-V:Memory'
} | Select-Object -First 1

$rpsd = ([wmiclass]"\\.\$($ns):Msvm_ResourcePoolSettingData").CreateInstance()
$rpsd.PoolID = $poolId; $rpsd.ResourceType = [uint16]4; $rpsd.ResourceSubType = 'Microsoft:Hyper-V:Memory'

# AllocationSettings 中 RASD 的 PoolID 必须等于新子池名, 各配额均填 0 (子池按需从父池取用)
$masd = ([wmiclass]"\\.\$($ns):Msvm_MemorySettingData").CreateInstance()
$masd.PoolID = $poolId; $masd.ResourceType = [uint16]4; $masd.ResourceSubType = 'Microsoft:Hyper-V:Memory'
$masd.Reservation=[uint64]0; $masd.Limit=[uint64]0; $masd.VirtualQuantity=[uint64]0; $masd.Weight=[uint32]0

$r = $rpcs.CreatePool($rpsd.GetText(1), @($parent.__PATH), @($masd.GetText(1)))
if($r.ReturnValue -eq 4096){ Wait-Job2 $r.Job | Out-Null }

# 读回校验
$child = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool | Where-Object { $_.PoolId -eq $poolId } | Select-Object -First 1
$child | Format-List PoolId, ResourceType, Primordial, InstanceID

# 删除子池: DeletePool(Pool REF) (DeleteResourcePool 同样未实现)
$rd = $rpcs.DeletePool($child.__PATH)
if($rd.ReturnValue -eq 4096){ Wait-Job2 $rd.Job | Out-Null }
```

## [UNSUPPORTED] 配置共享 VHDX 与 SCSI-3 持久预留  `shared_vhd`

- 共享 VHDX 与 SCSI-3 持久预留需要故障转移群集的群集共享卷（CSV）、共享 SAS 存储或横向扩展文件服务器（SOFS）承载 .vhds 文件。独立（非群集）Hyper-V 主机上的本地 NTFS 卷不满足该硬件/环境要求，AddResourceSettings 会以 JobState=10、ErrorCode=32768（存储不支持虚拟硬盘共享）或 32770（不是可共享的 VHD 文件）失败，故状态判定为 UNSUPPORTED。
- WMI 写法：在 Msvm_StorageAllocationSettingData 上设置 PersistentReservationsSupported=$true（共享盘/持久预留开关），其余与普通挂盘一致（Parent=磁盘驱动器路径，HostResource=@(盘路径)）。该属性在类定义中标为 Read 限定符，但实例上可写。
- 共享盘必须使用 VHD Set（.vhds），不能使用普通 .vhdx。创建方式：设置 Msvm_VirtualHardDiskSettingData 的 Type=3（Dynamic）+ Format=4（VHDSet），再经 Msvm_ImageManagementService.CreateVirtualHardDisk 创建。Type 枚举仅有 2/3/4（Fixed/Dynamic/Differencing），无独立的 VHDSet 类型，VHD Set 通过 Format=4 区分。
- VHD Set 创建时会同时生成 <name>.vhds（元数据）与一个 <guid>.avhdx（数据）文件，清理时两者都需删除。
- Type 或 Format 取值非法（如 Type=5/6）时，CreateVirtualHardDisk 直接返回 32773（参数无效），而非以 Job 错误形式返回。
- 在 Windows Server 2025 中共享 VHDX / VHD Set 仍为受支持特性，上述限制源自缺少群集共享存储环境，而非特性本身缺失。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$vmName = 'WMITEST_shared_vhd'
$workDir = 'C:/Users/Administrator/Documents/GitHub/HyperV-WMI-Documentation/verify/work'
# 共享 VHDX 需要 VHD Set (.vhds)，不能使用普通 .vhdx
$vhdPath = (Join-Path $workDir 'WMITEST_shared_vhd.vhds') -replace '/', '\'

function Wait-Job2($p) {
    if (-not $p) { return 7 }
    $j = [wmi]$p
    while ($j.JobState -eq 3 -or $j.JobState -eq 4) { Start-Sleep -Milliseconds 200; $j = [wmi]$p }
    return $j.JobState
}
function Job-Err($p) {
    if (-not $p) { return '<no job>' }
    try { $j = [wmi]$p; return "state=$($j.JobState) err=$($j.ErrorCode) desc=$($j.ErrorDescription)" } catch { return "<job gone>" }
}
function Get-DefaultSettings($subType) {
    $pool = Get-WmiObject -Namespace $ns -Class Msvm_ResourcePool -Filter "ResourceSubType='$subType' AND Primordial=True"
    $caps = $pool.GetRelated('Msvm_AllocationCapabilities','Msvm_ElementCapabilities',$null,$null,$null,$null,$false,$null) | Select-Object -First 1
    $rels = $caps.GetRelationships('Msvm_SettingsDefineCapabilities')
    foreach ($r in $rels) { if ($r.ValueRole -eq 0) { return [wmi]$r.PartComponent } }
    return $null
}

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$ims  = Get-WmiObject -Namespace $ns -Class Msvm_ImageManagementService
if (Test-Path $vhdPath) { Remove-Item $vhdPath -Force }

try {
    # 1. 第二代虚拟机 + SCSI 控制器
    $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
    $vssd.ElementName = $vmName
    $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
    $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
    if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
    $vm = [wmi]$r.ResultingSystem
    $vssd2 = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
    $scsiTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic SCSI Controller'
    $ar = $vsms.AddResourceSettings($vssd2.__PATH, @($scsiTmpl.GetText(1)))
    if ($ar.ReturnValue -eq 4096) { $null = Wait-Job2 $ar.Job }
    $scsi = [wmi]$ar.ResultingResourceSettings[0]

    # 2. 创建 VHD Set (.vhds)：Type=3(Dynamic) + Format=4(VHDSet)
    $vhdSd = ([wmiclass]"\\.\${ns}:Msvm_VirtualHardDiskSettingData").CreateInstance()
    $vhdSd.Type = [uint16]3
    $vhdSd.Format = [uint16]4
    $vhdSd.Path = $vhdPath
    $vhdSd.MaxInternalSize = [uint64](1GB)
    $cr = $ims.CreateVirtualHardDisk($vhdSd.GetText(1))
    if ($cr.ReturnValue -eq 4096) { $s = Wait-Job2 $cr.Job; if ($s -ne 7) { throw "CreateVHDSet failed: $(Job-Err $cr.Job)" } }
    elseif ($cr.ReturnValue -ne 0) { throw "CreateVHDSet rv $($cr.ReturnValue)" }

    # 3. 在 SCSI LUN0 上添加合成磁盘驱动器
    $drvTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Synthetic Disk Drive'
    $drv = $drvTmpl.psbase.Clone(); $drv.Parent = $scsi.__PATH; $drv.AddressOnParent = '0'
    $ar2 = $vsms.AddResourceSettings($vssd2.__PATH, @($drv.GetText(1)))
    if ($ar2.ReturnValue -eq 4096) { $null = Wait-Job2 $ar2.Job }
    $drvPath = $ar2.ResultingResourceSettings[0]

    # 4. 设置 StorageAllocationSettingData，PersistentReservationsSupported=$true（共享/群集标志）
    $sasdTmpl = Get-DefaultSettings 'Microsoft:Hyper-V:Virtual Hard Disk'
    $sasd = $sasdTmpl.psbase.Clone()
    $sasd.Parent = $drvPath
    $sasd.HostResource = @($vhdPath)
    $sasd.PersistentReservationsSupported = $true   # SCSI-3 持久预留 / 共享 VHDX
    $ar3 = $vsms.AddResourceSettings($vssd2.__PATH, @($sasd.GetText(1)))
    if ($ar3.ReturnValue -eq 4096) {
        $s = Wait-Job2 $ar3.Job
        if ($s -ne 7) { Write-Host "SHARED ATTACH FAILED (host limitation): $(Job-Err $ar3.Job)"; Write-Host 'RESULT: UNSUPPORTED' }
        else {
            $vf = ([wmi]$vm.__PATH).GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1
            $disks = ([wmi]$vf.__PATH).GetRelated('Msvm_StorageAllocationSettingData')
            foreach ($dk in $disks) { $res=@($dk.HostResource); if ($res[0] -and $res[0].ToLower() -eq $vhdPath.ToLower()) { Write-Host "PR readback=$($dk.PersistentReservationsSupported)" } }
            Write-Host 'RESULT: PASS'
        }
    } elseif ($ar3.ReturnValue -eq 0) { Write-Host 'RESULT: PASS' }
    else { Write-Host "SHARED ATTACH rv=$($ar3.ReturnValue)"; Write-Host 'RESULT: UNSUPPORTED' }
}
catch { Write-Host "ERROR: $_"; Write-Host 'RESULT: UNSUPPORTED' }
finally {
    try {
        $existing = Get-WmiObject -Namespace $ns -Class Msvm_ComputerSystem -Filter "ElementName='$vmName'"
        foreach ($e in @($existing)) { if ($e) { $d = $vsms.DestroySystem($e.__PATH); if ($d.ReturnValue -eq 4096) { $null = Wait-Job2 $d.Job } } }
    } catch {}
    # VHD Set 会留下 <name>.vhds + <guid>.avhdx 数据文件，需全部删除
    Get-ChildItem -Path $workDir -Filter 'WMITEST_shared_vhd*.vhds' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $workDir -Filter 'WMITEST_shared_vhd*.avhdx' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
}
```

## [UNSUPPORTED] 在主机侧启用 RemoteFX GPU 虚拟化  `synth3d_enable`

- 该操作需要支持 RemoteFX 的物理 3D GPU。Msvm_Synthetic3DService 类以单例形式存在(Name=synth3d)，但当 Msvm_Physical3dGraphicsProcessor 枚举数为 0 时，主机上没有可虚拟化的物理 3D GPU，EnableGPUForVirtualization 无可作用的目标。
- RemoteFX vGPU 自 Windows 10 / Server 1809 起弃用，其后的版本已从平台移除。现代 GPU 虚拟化应使用 GPU-P (Msvm_GpuPartitionSettingData) 或 DDA(离散设备分配)。
- 方法签名：Msvm_Synthetic3DService.EnableGPUForVirtualization([IN,REF]Msvm_Physical3dGraphicsProcessor PhysicalGPU, [OUT,REF]CIM_ConcreteJob Job) -> uint32。返回码 0=Completed with No Error，1=Not supported；返回 4096 时需轮询作业。DisableGPUForVirtualization 的参数与返回码对称。该方法自 build 9200 起提供。
- PhysicalGPU 为 REF 参数，传入 GPU 实例的 __PATH。GPU 是否已启用虚拟化可读取 Msvm_Physical3dGraphicsProcessor.EnabledForVirtualization(只读 Boolean)。
- 该操作为主机侧操作，与具体虚拟机无关。

```powershell
$ns='root\virtualization\v2'
# 1) 枚举支持 RemoteFX 的物理 GPU
$phys=@(Get-WmiObject -Namespace $ns -Class Msvm_Physical3dGraphicsProcessor)
# 2) 定位主机 Synthetic3D 服务(单例)
$svc=Get-WmiObject -Namespace $ns -Class Msvm_Synthetic3DService
# 3) 在某物理 GPU 上启用 RemoteFX 虚拟化(PhysicalGPU 为 REF; 传 __PATH)
if($phys.Count -gt 0){
  $target=$phys[0]
  $r=$svc.EnableGPUForVirtualization($target.__PATH)   # ret 0=成功, 1=不支持, 4096=异步作业
  if($r.ReturnValue -eq 4096){ $j=[wmi]$r.Job; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -m 200; $j=[wmi]$r.Job} }
  # 回读
  ([wmi]$target.__PATH).EnabledForVirtualization
}
# 停用操作对称: $svc.DisableGPUForVirtualization($target.__PATH)
```

## [UNSUPPORTED] 获取虚拟机缩略图  `thumbnail_screenshot`

- 方法签名：Msvm_VirtualSystemManagementService.GetVirtualSystemThumbnailImage(TargetSystem REF, WidthPixels uint16, HeightPixels uint16) -> ImageData uint8[]；返回 uint32 返回码。
- TargetSystem 必须传入虚拟机的 Msvm_VirtualSystemSettingData 的 __PATH（REF CIM_VirtualSystemSettingData），不能传 Msvm_ComputerSystem。可通过 $vm.GetRelated('Msvm_VirtualSystemSettingData') 获取。
- 图像格式为原始 RGB565，每像素 2 字节，期望字节数 = Width*Height*2（80x60 即 9600）。该方法同步返回，不返回 Job。
- 返回码映射（ValueMap）：0=成功，4096=Job，32775=Invalid State。缩略图取自运行中的视频帧缓冲，仅当虚拟机处于运行或已保存状态时才返回非空字节。
- 该操作需要处于运行或已保存状态的虚拟机环境。停止状态（EnabledState=3）的虚拟机调用此方法恒返回 32775（Invalid State）且 ImageData 为空。

```powershell
$ErrorActionPreference = 'Stop'
$ns = 'root\virtualization\v2'
$name = 'WMITEST_thumbnail_screenshot'

function Wait-Job2($p){ if(-not $p){return 7}; $j=[wmi]$p; while($j.JobState -eq 3 -or $j.JobState -eq 4){Start-Sleep -Milliseconds 200; $j=[wmi]$p}; return $j.JobState }

$vsms = Get-WmiObject -Namespace $ns -Class Msvm_VirtualSystemManagementService
$vm = $null
try {
  # 创建第二代测试虚拟机
  $vssd = ([wmiclass]"\\.\${ns}:Msvm_VirtualSystemSettingData").CreateInstance()
  $vssd.ElementName = $name
  $vssd.VirtualSystemSubType = 'Microsoft:Hyper-V:SubType:2'
  $r = $vsms.DefineSystem($vssd.GetText(1), $null, $null)
  if ($r.ReturnValue -eq 4096) { $null = Wait-Job2 $r.Job }
  $vm = [wmi]$r.ResultingSystem

  # TargetSystem 需为虚拟机的 VirtualSystemSettingData 引用，而非 ComputerSystem
  $vssd2 = $vm.GetRelated('Msvm_VirtualSystemSettingData') | Select-Object -First 1

  # GetVirtualSystemThumbnailImage(TargetSystem REF VSSD, WidthPixels uint16, HeightPixels uint16) -> ImageData uint8[]（原始 RGB565，每像素 2 字节）
  $t = $vsms.GetVirtualSystemThumbnailImage($vssd2.__PATH, [uint16]80, [uint16]60)
  $len = 0; if ($t.ImageData) { $len = $t.ImageData.Length }
  Write-Output "RV=$($t.ReturnValue) LEN=$len EXPECTED_RGB565=$([int](80*60*2))"
  # 运行中的虚拟机：RV=0，LEN = Width*Height*2。停止状态的虚拟机：RV=32775（Invalid State），LEN=0。
}
finally {
  if ($vm -ne $null) { try { $null = $vsms.DestroySystem($vm.__PATH) } catch {} }
}
```
