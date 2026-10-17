Unicode true
ManifestSupportedOS all
RequestExecutionLevel admin
SetCompressor /SOLID lzma
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
Name "DeepSeek Harness ${VERSION} (${EDITION})"
OutFile "${OUTPUT}"
InstallDir "$PROGRAMFILES64\DeepSeek Harness"
InstallDirRegKey HKLM "Software\DeepSeekHarnessWin7" "InstallLocation"
ShowInstDetails show
ShowUninstDetails show
Var PrereqLog
Var Generation
!ifndef MAX_INSTALL_ROOT
  !define MAX_INSTALL_ROOT 100
!endif
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TEXT "DeepSeek Harness was installed. Start it from the Start menu. Your settings and sessions stay in your DSH_HOME."
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
  ${IfNot} ${AtLeastWin7}
    MessageBox MB_ICONSTOP "Windows 7 SP1 or later is required."
    SetErrorLevel 1
    Abort
  ${EndIf}
  ${If} ${IsWin7}
  ${AndIfNot} ${AtLeastServicePack} 1
    MessageBox MB_ICONSTOP "Windows 7 Service Pack 1 is required."
    SetErrorLevel 1
    Abort
  ${EndIf}
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "This package requires x64 Windows."
    SetErrorLevel 1
    Abort
  ${EndIf}
  SetRegView 64
FunctionEnd

Function ValidateInstallDirectory
  StrLen $0 $INSTDIR
  ${If} $0 > ${MAX_INSTALL_ROOT}
    MessageBox MB_ICONSTOP "Choose a shorter installation folder. This Win7 package allows at most ${MAX_INSTALL_ROOT} characters before its version directory."
    SetErrorLevel 1
    Abort
  ${EndIf}
FunctionEnd
Function .onVerifyInstDir
  Call ValidateInstallDirectory
FunctionEnd

Section "Desktop" SEC_DESKTOP
  Call ValidateInstallDirectory
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=prerequisites.ps1 "${POLICY}"
  File /oname=uninstall-files.ps1 "${CLEANUP}"
  GetTempFileName $PrereqLog
  ${DisableX64FSRedirection}
  nsExec::ExecToLog /TIMEOUT=60000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\uninstall-files.ps1" -InstallDirectory "$INSTDIR" -CheckOnly'
  Pop $0
  ${EnableX64FSRedirection}
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Close all DeepSeek Harness windows and quit its tray icon, then run setup again. No running application will be terminated."
    SetErrorLevel 4
    Abort
  ${EndIf}
!if "${EDITION}" == "aio"
  IfSilent consent_done
  MessageBox MB_OKCANCEL|MB_ICONINFORMATION "AIO will install missing Microsoft prerequisites on Windows 7. It may require restarting and running this installer again before the application can be installed." IDOK consent_done
    SetErrorLevel 1
    Abort
  consent_done:
  SetOutPath "$PLUGINSDIR\prereq"
  File /r "${PREREQUISITES}\*"
!endif
  ${DisableX64FSRedirection}
  nsExec::ExecToLog /TIMEOUT=1850000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\prerequisites.ps1" -Edition ${EDITION} -Payload "$PLUGINSDIR\prereq" -LogPath "$PrereqLog"'
  Pop $0
  ${EnableX64FSRedirection}
  ${If} $0 == 3010
    DetailPrint "Servicing restart required. Log: $PrereqLog"
    IfSilent reboot_later
    MessageBox MB_YESNO|MB_ICONINFORMATION "Windows must restart. Run this installer again after restarting to continue. Restart now?" IDNO reboot_later
    Reboot
    reboot_later:
    SetErrorLevel 3010
    Abort
  ${ElseIf} $0 != 0
    MessageBox MB_ICONSTOP "Prerequisites are unavailable or installation failed. Windows 7 needs SSU KB4490628, SHA-2 KB4474419, D3DCompiler47 KB4019990, .NET 4.7.2 and PowerShell 5.1. WMF 3.0 must first be removed using Microsoft guidance. Standard users can use the AIO installer. Log: $PrereqLog"
    SetErrorLevel 1
    Abort
  ${EndIf}
  StrCpy $Generation "$INSTDIR\versions\${GENERATION}"
  IfFileExists "$Generation\*" generation_exists
  SetOutPath "$Generation"
  ClearErrors
  File /r "${PAYLOAD}\*"
  IfErrors install_failed
  WriteUninstaller "$Generation\uninstall.exe"
  IfErrors install_failed
  ${DisableX64FSRedirection}
  nsExec::ExecToLog /TIMEOUT=60000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\uninstall-files.ps1" -InstallDirectory "$INSTDIR" -RegisterGeneration "$Generation"'
  Pop $0
  ${EnableX64FSRedirection}
  ${If} $0 != 0
    Goto install_failed
  ${EndIf}
  SetShellVarContext all
  CreateDirectory "$SMPROGRAMS\DeepSeek Harness"
  CreateShortCut "$SMPROGRAMS\DeepSeek Harness\DeepSeek Harness.lnk" "$Generation\DeepSeek Harness.exe"
  CreateShortCut "$SMPROGRAMS\DeepSeek Harness\Uninstall.lnk" "$Generation\uninstall.exe"
  WriteRegStr HKLM "Software\DeepSeekHarnessWin7" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "DisplayName" "DeepSeek Harness"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "DisplayVersion" "${VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "UninstallString" '$\"$Generation\uninstall.exe$\"'
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7" "NoRepair" 1
  Goto done
  generation_exists:
    MessageBox MB_ICONINFORMATION "This exact application generation already exists. Start the installed application or uninstall it before reinstalling."
    SetErrorLevel 1
    Abort
  install_failed:
    MessageBox MB_ICONSTOP "Application extraction failed. Previous generations and user data have been preserved."
    SetErrorLevel 1
    Abort
  done:
SectionEnd

Function un.onInit
  SetRegView 64
  # The uninstaller lives inside versions/<generation>.
  GetFullPathName $INSTDIR "$INSTDIR\..\.."
FunctionEnd
Section "Uninstall"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=uninstall-files.ps1 "${CLEANUP}"
  ${DisableX64FSRedirection}
  nsExec::ExecToLog /TIMEOUT=180000 '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\uninstall-files.ps1" -InstallDirectory "$INSTDIR"'
  Pop $0
  ${EnableX64FSRedirection}
  ${If} $0 != 0
    MessageBox MB_ICONSTOP "Quit DeepSeek Harness first. Uninstall stopped; files and user data were preserved."
    SetErrorLevel 1
    Abort
  ${EndIf}
  SetShellVarContext all
  Delete "$SMPROGRAMS\DeepSeek Harness\DeepSeek Harness.lnk"
  Delete "$SMPROGRAMS\DeepSeek Harness\Uninstall.lnk"
  RMDir "$SMPROGRAMS\DeepSeek Harness"
  ReadRegStr $0 HKLM "Software\DeepSeekHarnessWin7" "InstallLocation"
  ${If} $0 == $INSTDIR
    DeleteRegKey HKLM "Software\DeepSeekHarnessWin7"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\DeepSeekHarnessWin7"
  ${EndIf}
  Delete "$EXEPATH"
  RMDir "$INSTDIR"
SectionEnd
