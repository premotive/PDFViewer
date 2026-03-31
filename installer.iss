; Inno Setup Script for PDF Viewer

[Setup]
AppName=PDF Viewer
AppVersion=1.0
AppPublisher=Noah
DefaultDirName={autopf}\PDFViewer
DefaultGroupName=PDF Viewer
OutputDir=installer_output
OutputBaseFilename=PDFViewer_Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\PDFViewer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "fileassoc"; Description: "Associate .pdf files with PDF Viewer"; GroupDescription: "File associations:"

[Files]
Source: "dist\PDFViewer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Viewer"; Filename: "{app}\PDFViewer.exe"
Name: "{group}\Uninstall PDF Viewer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PDF Viewer"; Filename: "{app}\PDFViewer.exe"; Tasks: desktopicon

[Registry]
Root: HKCR; Subkey: ".pdf"; ValueType: string; ValueName: ""; ValueData: "PDFViewer.PDF"; Flags: uninsdeletevalue; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF"; ValueType: string; ValueName: ""; ValueData: "PDF Document"; Flags: uninsdeletekey; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\PDFViewer.exe,0"; Tasks: fileassoc
Root: HKCR; Subkey: "PDFViewer.PDF\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\PDFViewer.exe"" ""%1"""; Tasks: fileassoc

[Run]
Filename: "{app}\PDFViewer.exe"; Description: "Launch PDF Viewer"; Flags: nowait postinstall skipifsilent
