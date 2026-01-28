; Cooksy Recipe PDF - Professional Windows Installer
; NSIS 3.x - Complete installer with License Agreement, Directory Selection
; Features: Terms & Conditions, Custom Install Path, Start App Option, Windows Uninstall
; Updated: 28 Jan 2026 - CSRF Token Security Fix Included

!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

; ============== DEFINES ==============
!define APPNAME "Cooksy"
!define APPVERSION "1.0.0"
!define APPURL "https://cooksy.local"
!define COMPANYNAME "Cooksy"
!define BUILDDATE "28 Jan 2026"

; ============== INSTALLER SETTINGS ==============
Name "${APPNAME} ${APPVERSION}"
OutFile "Cooksy-${APPVERSION}-Setup.exe"
InstallDir "$PROGRAMFILES\${APPNAME}"
CRCCheck off
SetCompress off
RequestExecutionLevel admin

; Registry key for uninstall info
!define UNINSTKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"

; ============== MUI PAGES ==============
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "data\legal\TERMS_AND_CONDITIONS.md"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ============== LANGUAGE ==============
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "English"

; ============== VERSION INFORMATION ==============
VIProductVersion "${APPVERSION}.0"
VIAddVersionKey ProductName "${APPNAME} Recipe PDF"
VIAddVersionKey ProductVersion "${APPVERSION}"
VIAddVersionKey CompanyName "${COMPANYNAME}"
VIAddVersionKey FileVersion "${APPVERSION}"
VIAddVersionKey FileDescription "Cooksy - Generatore PDF per Ricette"
VIAddVersionKey LegalCopyright "Copyright 2026 ${COMPANYNAME}"
VIAddVersionKey InternalName "${APPNAME}"
VIAddVersionKey Comments "Updated: ${BUILDDATE}"

; ============== INSTALLER SECTION ==============
Section "${APPNAME} Application"
  SetOutPath "$INSTDIR"
  DetailPrint "Installing ${APPNAME} v${APPVERSION}..."
  
  ; Copy executable, dependencies and legal documents
  File /r "dist\Cooksy\*.*"
  
  ; Create Start Menu folder and shortcuts
  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\${APPNAME}.lnk" "$INSTDIR\Cooksy.exe" "" "$INSTDIR\Cooksy.exe" 0
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Uninstall ${APPNAME}.lnk" "$INSTDIR\uninstall.exe"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Leggimi.lnk" "$INSTDIR\LICENSE.md"
  CreateShortCut "$SMPROGRAMS\${APPNAME}\Termini e Condizioni.lnk" "$INSTDIR\TERMS_AND_CONDITIONS.md"
  
  ; Create Desktop shortcut
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\Cooksy.exe"
  
  ; Write uninstaller
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
  ; Registry entries for Windows Add/Remove Programs
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayName" "${APPNAME} - Generatore PDF Ricette"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayVersion" "${APPVERSION}"
  WriteRegStr HKLM "${UNINSTKEY}" "Publisher" "${COMPANYNAME}"
  WriteRegStr HKLM "${UNINSTKEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegStr HKLM "${UNINSTKEY}" "DisplayIcon" "$INSTDIR\Cooksy.exe"
  WriteRegStr HKLM "${UNINSTKEY}" "URLInfoAbout" "${APPURL}"
  WriteRegStr HKLM "${UNINSTKEY}" "URLUpdateInfo" "${APPURL}"
  WriteRegStr HKLM "${UNINSTKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "${UNINSTKEY}" "BuildDate" "${BUILDDATE}"
  
  DetailPrint "Installation complete! Build date: ${BUILDDATE}"
SectionEnd

; ============== UNINSTALLER SECTION ==============
Section "Uninstall"
  DetailPrint "Removing ${APPNAME}..."
  
  ; Stop running application
  nsExec::Exec "taskkill /F /IM Cooksy.exe /T 2>nul"
  Sleep 500
  
  ; Remove installation directory
  RMDir /r "$INSTDIR"
  
  ; Remove Start Menu folder
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  
  ; Remove Desktop shortcut
  Delete "$DESKTOP\${APPNAME}.lnk"
  
  ; Remove registry entries
  DeleteRegKey HKLM "${UNINSTKEY}"
  
  DetailPrint "Uninstallation complete!"
SectionEnd

; ============== FUNCTIONS ==============
Function .onInit
  SetShellVarContext all
FunctionEnd

Function .onInstSuccess
  MessageBox MB_YESNO "${APPNAME} è ora installato.$\n$\nVuoi avviare ${APPNAME} adesso?" IDYES LaunchApp IDNO SkipLaunch
  
  LaunchApp:
    ExecShell "" "$INSTDIR\Cooksy.exe"
  
  SkipLaunch:
FunctionEnd

Function un.onUninstSuccess
  MessageBox MB_OK "${APPNAME} è stato disinstallato con successo."
FunctionEnd
