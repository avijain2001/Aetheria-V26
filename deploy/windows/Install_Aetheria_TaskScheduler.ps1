$taskName = "Aetheria World Experience"
$app = Join-Path $PSScriptRoot "..\..\Start_Aetheria.vbs" | Resolve-Path
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument ('"' + $app.Path + '"')
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Force
Write-Host "Installed $taskName"
