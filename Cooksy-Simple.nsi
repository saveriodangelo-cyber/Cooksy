; Cooksy Installer - Simple & Working
; Copy this to NSIS and compile

!include "MUI2.nsh"

Name "Cooksy 1.0.0"
OutFile "Cooksy-Setup.exe"
InstallDir "$PROGRAMFILES\Cooksy"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "data\legal\TERMS_AND_CONDITIONS.md"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"

Section "Cooksy"
  SetOutPath "$INSTDIR"
  File /r "dist\Cooksy\*.*"
  
  CreateDirectory "$SMPROGRAMS\Cooksy"
  CreateShortCut "$SMPROGRAMS\Cooksy\Cooksy.lnk" "$INSTDIR\Cooksy.exe"
  CreateShortCut "$SMPROGRAMS\Cooksy\Uninstall.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$DESKTOP\Cooksy.lnk" "$INSTDIR\Cooksy.exe"
  
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Cooksy" "DisplayName" "Cooksy"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Cooksy" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Cooksy" "DisplayIcon" "$INSTDIR\Cooksy.exe"
SectionEnd

Section "Uninstall"
  ExecWait "taskkill /F /IM Cooksy.exe /T"
  RMDir /r "$INSTDIR"
  RMDir /r "$SMPROGRAMS\Cooksy"
  Delete "$DESKTOP\Cooksy.lnk"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\Cooksy"
SectionEnd

Function .onInstSuccess
  MessageBox MB_YESNO "Cooksy installato. Avviare ora?" IDYES LaunchApp IDNO SkipLaunch
  LaunchApp:
    ExecShell "" "$INSTDIR\Cooksy.exe"
  SkipLaunch:
FunctionEnd
