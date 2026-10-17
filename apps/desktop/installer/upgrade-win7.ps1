# Windows 7 PowerShell 2.0 entry. Run explicitly as administrator.
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (!$principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  Write-Host 'Right-click upgrade-win7.bat and select Run as administrator. No components were changed.'
  exit 5
}
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log = [IO.Path]::Combine([IO.Path]::GetTempPath(), ('dsh-win7-upgrade-' + [Guid]::NewGuid().ToString('N') + '.log'))
Write-Host ('Log: ' + $log)
try {
  . ([IO.Path]::Combine($root, 'prerequisites.ps1')) -LibraryOnly
  $Payload = [IO.Path]::Combine($root, 'prerequisites')
  $LogPath = $log
  $arch = 'x86'
  if ([IntPtr]::Size -eq 8) { $arch = 'x64' }
  $code = Invoke-Prerequisites 'aio' $arch
  if ($code -eq 3010) { Write-Host 'Restart Windows, then run upgrade-win7.bat again to continue.' }
  exit $code
} catch { Write-Host ('ERROR: ' + $_.Exception.Message); exit 1 }
