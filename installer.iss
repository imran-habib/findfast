[Setup]
AppName=QuickFind
AppVersion={#GetEnv('TAG_VERSION')}
DefaultDirName={autopf}\QuickFind
DefaultGroupName=QuickFind
OutputBaseFilename=QuickFind-Setup
SetupIconFile=quickfind.ico
UninstallDisplayIcon={app}\QuickFind.exe
Compression=lzma2
SolidCompression=yes
OutputDir=installer

[Files]
Source: "dist\QuickFind.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "quickfind.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\QuickFind"; Filename: "{app}\QuickFind.exe"
Name: "{commondesktop}\QuickFind"; Filename: "{app}\QuickFind.exe"; Tasks: desktopicon
Name: "{userstartup}\QuickFind"; Filename: "{app}\QuickFind.exe"; Tasks: startup

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "startup"; Description: "Start QuickFind on Windows startup"; GroupDescription: "Additional options:"

[Run]
Filename: "{app}\QuickFind.exe"; Description: "Launch QuickFind"; Flags: nowait postinstall skipifsilent
