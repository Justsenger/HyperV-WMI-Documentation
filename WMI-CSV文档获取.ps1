# --- 极致全量版 WMI 文档采集脚本 (兼容 PowerShell 5.1) ---

$os = Get-CimInstance Win32_OperatingSystem
$buildNum = $os.BuildNumber
$csvPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "WmiDoc_Final_$($buildNum)_WithEnums.csv"

# 1. 定义要遍历的命名空间
$namespaces = @("root\virtualization\v2", "root\cimv2")

# 排除列表：排除掉一些系统级别的内部类
$excludePrefix = "__"

$results = New-Object System.Collections.Generic.List[PSCustomObject]
Add-Type -AssemblyName System.Management

foreach ($ns in $namespaces) {
    Write-Host "`n正在连接命名空间: $ns" -ForegroundColor Cyan
    $scope = New-Object System.Management.ManagementScope("\\.\$ns")
    
    try {
        $scope.Connect()
    } catch {
        Write-Warning "无法连接到 $ns"
        continue
    }

    $options = New-Object System.Management.ObjectGetOptions
    $options.UseAmendedQualifiers = $true 

    # 获取所有类
    $searcher = New-Object System.Management.ManagementObjectSearcher($scope, [System.Management.SelectQuery]::new("SELECT * FROM meta_class"))
    $allClasses = $searcher.Get()

    $totalInNs = 0
    foreach ($classMetadata in $allClasses) {
        $clsName = $classMetadata["__CLASS"].ToString()

        # 过滤系统类
        if ($clsName.StartsWith($excludePrefix)) { continue }
        
        # 针对 root\cimv2 的过滤逻辑
        if ($ns -eq "root\cimv2" -and $clsName -ne "Win32_VideoController") { continue }

        $totalInNs++
        Write-Progress -Activity "正在采集命名空间: $ns" -Status "当前处理: $clsName ($totalInNs)"
        
        try {
            $path = New-Object System.Management.ManagementPath($clsName)
            $class = New-Object System.Management.ManagementClass($scope, $path, $options)
            $class.Get() 

            # --- 属性采集 ---
            foreach ($prop in $class.Properties) {
                $rawDesc = ""
                $valMap = $null
                $valNames = $null

                foreach ($q in $prop.Qualifiers) {
                    if ($q.Name -eq "Description") { $rawDesc = $q.Value.ToString().Replace("`n", " ").Replace("`r", "").Trim() }
                    if ($q.Name -eq "ValueMap") { $valMap = $q.Value }
                    if ($q.Name -eq "Values") { $valNames = $q.Value }
                }

                # 兼容 5.1 的描述赋值逻辑
                $finalDesc = "[无描述]"
                if ($rawDesc) { $finalDesc = $rawDesc }

                if ($valMap -and $valNames) {
                    $enumStrings = @()
                    $max = [Math]::Min($valMap.Count, $valNames.Count)
                    for ($i = 0; $i -lt $max; $i++) { $enumStrings += "$($valMap[$i]) - $($valNames[$i])" }
                    $finalDesc += " [枚举值: " + ($enumStrings -join "; ") + "]"
                }

                $results.Add([PSCustomObject]@{
                    Class    = $clsName
                    Member   = $prop.Name
                    Type     = $prop.Type.ToString()
                    Category = "Property"
                    Desc     = $finalDesc
                })
            }

            # --- 方法采集 ---
            foreach ($method in $class.Methods) {
                $mRawDesc = ""
                foreach ($q in $method.Qualifiers) {
                    if ($q.Name -eq "Description") {
                        $mRawDesc = $q.Value.ToString().Replace("`n", " ").Replace("`r", "").Trim()
                        break
                    }
                }
                
                $methodDesc = "[无描述]"
                if ($mRawDesc) { $methodDesc = $mRawDesc }

                $results.Add([PSCustomObject]@{
                    Class    = $clsName
                    Member   = $method.Name
                    Type     = "Method"
                    Category = "Method"
                    Desc     = $methodDesc
                })
            }
        } catch {
            continue
        }
    }
}

# 导出结果
if ($results.Count -gt 0) {
    # 使用 UTF8 编码导出，以便后续处理
    $results | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    Write-Host "`n全部完成！总共处理了 $totalInNs 个类。" -ForegroundColor Green
    Write-Host "文件保存在桌面: $csvPath" -ForegroundColor Cyan
} else {
    Write-Warning "未采集到任何数据。"
}