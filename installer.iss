#define AppName "Akis Kurgu AI"
; AppVersion comes from akis/__init__.py: CI passes /DAppVersion=<version>.
; Local build: iscc /DAppVersion=0.3.9 installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif
[Setup]
AppId={{3F3FE53D-553B-4D25-9169-4493F9AFD241}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\AkisKurguAI
DefaultGroupName={#AppName}
PrivilegesRequired=admin
UsePreviousAppDir=no
OutputDir=dist
OutputBaseFilename=AkisKurguAI-Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=app.ico
UninstallDisplayIcon={app}\AkisKurguAI.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Files]
Source: "dist\AkisKurguAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\AkisKurguAI.exe"
[Run]
Filename: "{app}\AkisKurguAI.exe"; Description: "Akis Kurgu AI"; Flags: nowait postinstall skipifsilent
