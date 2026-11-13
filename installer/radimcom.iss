; RADIMCOM setup (Inno Setup 6). Built by installer/make_installer.py, which passes:
;   /DAppVersion=0.115beta1 /DVersionNumeric=0.115.0.1 /DBuildDir=<staged program> /DOutDir=<dist> /DIconFile=<ico>
;   /DDsdVersion=<VERSION of install_dsd.py>
; One setup for a new installation and for an upgrade: an upgrade keeps the folder and data\ (settings, memories,
; logs, recordings). No administrator rights (installed per user); only the USB drivers ask for them.
; Upgrade = the chosen folder has data\config.json or RADIMCOM.exe: an installation by this setup, or an older zip
; installation (0.114 and older: .venv, start.bat), which it says on the first page, the folder page and the last one.
; An upgrade skips the SDR setup at the end and offers DSD-FME only when the installed one is of another version.

#ifndef AppVersion
  #error Build with installer/make_installer.py
#endif

[Setup]
AppId={{6E0A3C2B-5D1F-4B7A-9C1E-2A7F0D3B8E41}
AppName=RADIMCOM
AppVersion={#AppVersion}
AppVerName=RADIMCOM {#AppVersion}
AppPublisher=Radim Mutina
AppPublisherURL=https://github.com/om2amr/RADIMCOM
AppSupportURL=https://github.com/om2amr/RADIMCOM/issues
AppUpdatesURL=https://github.com/om2amr/RADIMCOM/releases
VersionInfoVersion={#VersionNumeric}
VersionInfoProductName=RADIMCOM
VersionInfoDescription=RADIMCOM setup
DefaultDirName={sd}\RADIMCOM
DefaultGroupName=RADIMCOM
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=RADIMCOM_Setup_v{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\RADIMCOM.exe
UninstallDisplayName=RADIMCOM
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=auto
LicenseFile={#BuildDir}\LICENSE
UsePreviousTasks=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "sk"; MessagesFile: "compiler:Languages\Slovak.isl"
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"

[CustomMessages]
en.Drivers=USB drivers (they ask for administrator rights):
en.Zadig=Run Zadig: WinUSB driver for the RTL-SDR dongles (once per dongle)
en.D3XX=Install the FTDI D3XX driver for the LimeSDR Mini
en.Extras=Optional:
en.Dsd=Download the DSD-FME decoder (DSD mode, digital voice; shows a patent notice)
en.Autostart=Start RADIMCOM with Windows (in the tray)
en.SdrSetup=Configure the SDR dongles and start RADIMCOM (connect the dongles first)
en.Launch=Start RADIMCOM
en.DataFolder=RADIMCOM data folder
en.SdrSetupIcon=RADIMCOM SDR setup
en.ServerConsole=RADIMCOM in a console (troubleshooting)
en.DevCopy=This folder is a RADIMCOM development copy (git). Choose another folder.
en.Running=RADIMCOM is running. Close it (tray icon, right click, Exit RADIMCOM) and click Retry.
en.DelData=Also delete your RADIMCOM data (settings, memories, logs, recordings) in%n%1?
en.Upgrade=Upgrade: RADIMCOM in this folder is upgraded to {#AppVersion}. Your data (data\ folder: settings, memories, logs, recordings) stays.
en.UpgradeZip=Upgrade: an older RADIMCOM (0.114 or older, installed from a zip) is in this folder. It is upgraded to {#AppVersion} and becomes the RADIMCOM app (own window, tray icon, own Python). Your data (data\ folder: settings, memories, logs, recordings) stays.
en.NewInstall=A new installation (no RADIMCOM in this folder). If you have an older RADIMCOM, choose its folder to upgrade it.
en.Console=RADIMCOM is running from this folder in a console window (start.bat). Close that window and click Retry.
en.DsdUpdate=Update the DSD-FME decoder to the version this RADIMCOM needs (shows a patent notice)
sk.Drivers=USB ovládače (vyžiadajú si práva správcu):
sk.Zadig=Spustiť Zadig: ovládač WinUSB pre RTL-SDR dongly (pre každý dongle raz)
sk.D3XX=Nainštalovať ovládač FTDI D3XX pre LimeSDR Mini
sk.Extras=Voliteľné:
sk.Dsd=Stiahnuť dekodér DSD-FME (režim DSD, digitálny hlas; zobrazí upozornenie na patenty)
sk.Autostart=Spúšťať RADIMCOM so štartom Windows (v oblasti oznámení)
sk.SdrSetup=Nastaviť SDR dongly a spustiť RADIMCOM (najprv dongly pripojte)
sk.Launch=Spustiť RADIMCOM
sk.DataFolder=Priečinok s dátami RADIMCOM
sk.SdrSetupIcon=RADIMCOM nastavenie SDR
sk.ServerConsole=RADIMCOM v konzole (riešenie problémov)
sk.DevCopy=Tento priečinok je vývojová kópia RADIMCOM (git). Zvoľte iný priečinok.
sk.Running=RADIMCOM je spustený. Ukončite ho (ikona v oblasti oznámení, pravé tlačidlo, Exit RADIMCOM) a kliknite na Opakovať.
sk.DelData=Vymazať aj vaše dáta RADIMCOM (nastavenia, pamäte, logy, nahrávky) v%n%1?
sk.Upgrade=Upgrade: RADIMCOM v tomto priečinku sa aktualizuje na {#AppVersion}. Vaše dáta (priečinok data\: nastavenia, pamäte, logy, nahrávky) zostanú.
sk.UpgradeZip=Upgrade: v tomto priečinku je staršia verzia RADIMCOM (0.114 alebo staršia, inštalovaná zo zipu). Aktualizuje sa na {#AppVersion} a stane sa z nej aplikácia RADIMCOM (vlastné okno, ikona v oblasti oznámení, vlastný Python). Vaše dáta (priečinok data\: nastavenia, pamäte, logy, nahrávky) zostanú.
sk.NewInstall=Nová inštalácia (v tomto priečinku nie je RADIMCOM). Ak máte staršiu verziu RADIMCOM, zvoľte jej priečinok a aktualizuje sa.
sk.Console=RADIMCOM z tohto priečinka beží v okne konzoly (start.bat). Zatvorte toto okno a kliknite na Opakovať.
sk.DsdUpdate=Aktualizovať dekodér DSD-FME na verziu, ktorú tento RADIMCOM potrebuje (zobrazí upozornenie na patenty)
cs.Drivers=USB ovladače (vyžádají si práva správce):
cs.Zadig=Spustit Zadig: ovladač WinUSB pro RTL-SDR dongly (pro každý dongle jednou)
cs.D3XX=Nainstalovat ovladač FTDI D3XX pro LimeSDR Mini
cs.Extras=Volitelné:
cs.Dsd=Stáhnout dekodér DSD-FME (režim DSD, digitální hlas; zobrazí upozornění na patenty)
cs.Autostart=Spouštět RADIMCOM se startem Windows (v oznamovací oblasti)
cs.SdrSetup=Nastavit SDR dongly a spustit RADIMCOM (nejprve dongly připojte)
cs.Launch=Spustit RADIMCOM
cs.DataFolder=Složka s daty RADIMCOM
cs.SdrSetupIcon=RADIMCOM nastavení SDR
cs.ServerConsole=RADIMCOM v konzoli (řešení problémů)
cs.DevCopy=Tato složka je vývojová kopie RADIMCOM (git). Zvolte jinou složku.
cs.Running=RADIMCOM běží. Ukončete ho (ikona v oznamovací oblasti, pravé tlačítko, Exit RADIMCOM) a klikněte na Opakovat.
cs.DelData=Smazat i vaše data RADIMCOM (nastavení, paměti, logy, nahrávky) v%n%1?
cs.Upgrade=Upgrade: RADIMCOM v této složce se aktualizuje na {#AppVersion}. Vaše data (složka data\: nastavení, paměti, logy, nahrávky) zůstanou.
cs.UpgradeZip=Upgrade: v této složce je starší verze RADIMCOM (0.114 nebo starší, instalovaná ze zipu). Aktualizuje se na {#AppVersion} a stane se z ní aplikace RADIMCOM (vlastní okno, ikona v oznamovací oblasti, vlastní Python). Vaše data (složka data\: nastavení, paměti, logy, nahrávky) zůstanou.
cs.NewInstall=Nová instalace (v této složce není RADIMCOM). Pokud máte starší verzi RADIMCOM, zvolte její složku a aktualizuje se.
cs.Console=RADIMCOM z této složky běží v okně konzole (start.bat). Zavřete toto okno a klikněte na Opakovat.
cs.DsdUpdate=Aktualizovat dekodér DSD-FME na verzi, kterou tento RADIMCOM potřebuje (zobrazí upozornění na patenty)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "{cm:Autostart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "zadig"; Description: "{cm:Zadig}"; GroupDescription: "{cm:Drivers}"; Flags: unchecked
Name: "d3xx"; Description: "{cm:D3XX}"; GroupDescription: "{cm:Drivers}"; Flags: unchecked
; DSD-FME: offered for a new installation; at an upgrade only when the installed one is of another version
Name: "dsd"; Description: "{cm:Dsd}"; GroupDescription: "{cm:Extras}"; Flags: unchecked; Check: (not IsUpgrade) and (not DsdInstalled)
Name: "dsdupdate"; Description: "{cm:DsdUpdate}"; GroupDescription: "{cm:Extras}"; Check: DsdOutdated

[InstallDelete]
; a clean Python and web interface on every upgrade (no leftovers of older package versions)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\static"
Type: filesandordirs; Name: "{app}\__pycache__"
; an older zip installation upgraded with the setup: its own Python environment and upgrade scripts are not needed
Type: filesandordirs; Name: "{app}\.venv"
Type: files; Name: "{app}\upgrade.bat"
Type: files; Name: "{app}\install.bat"
Type: files; Name: "{app}\UPGRADE.txt"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Excludes: "\data\*,\install.bat,\config.json"; Flags: ignoreversion recursesubdirs createallsubdirs
; the configuration template: only for a new installation (data\ belongs to the user)
Source: "{#BuildDir}\config.json"; DestDir: "{app}\data"; Flags: onlyifdoesntexist uninsneveruninstall

[Dirs]
Name: "{app}\data"; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\RADIMCOM"; Filename: "{app}\RADIMCOM.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\RADIMCOM"; Filename: "{app}\RADIMCOM.exe"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{autostartup}\RADIMCOM"; Filename: "{app}\RADIMCOM.exe"; Parameters: "--tray"; WorkingDir: "{app}"; Tasks: autostart
Name: "{group}\{cm:SdrSetupIcon}"; Filename: "{app}\RADIMCOM.exe"; Parameters: "--setup"; WorkingDir: "{app}"; IconFilename: "{sys}\shell32.dll"; IconIndex: 21
Name: "{group}\{cm:DataFolder}"; Filename: "{app}\data"
Name: "{group}\{cm:ServerConsole}"; Filename: "{app}\start.bat"; WorkingDir: "{app}"; IconFilename: "{sys}\shell32.dll"; IconIndex: 138
Name: "{group}\{cm:UninstallProgram,RADIMCOM}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\drivers\zadig.exe"; Tasks: zadig; Flags: shellexec waituntilterminated skipifsilent
Filename: "{app}\drivers\FTD3XXDriver_WHQLCertified_v1.3.0.4_Installer.exe"; Tasks: d3xx; Flags: shellexec waituntilterminated skipifsilent
Filename: "{cmd}"; Parameters: "/c install_dsd.bat"; WorkingDir: "{app}"; Tasks: dsd dsdupdate; Flags: waituntilterminated skipifsilent
; a new installation: the SDR setup in the RADIMCOM window, then RADIMCOM starts by itself; an upgrade: just RADIMCOM
Filename: "{app}\RADIMCOM.exe"; Parameters: "--setup"; WorkingDir: "{app}"; Description: "{cm:SdrSetup}"; Flags: postinstall nowait skipifsilent; Check: not IsUpgrade
Filename: "{app}\RADIMCOM.exe"; WorkingDir: "{app}"; Description: "{cm:Launch}"; Flags: postinstall nowait; Check: IsUpgrade or WizardSilent

[UninstallRun]
; a running RADIMCOM stops its server and ends (waits up to 30 s)
Filename: "{app}\RADIMCOM.exe"; Parameters: "--exit"; Flags: waituntilterminated; RunOnceId: "StopShell"

[UninstallDelete]
; created while running (compiled Python, the downloaded DSD-FME decoder, WebView2 cache stays in data\)
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\lib"
Type: filesandordirs; Name: "{app}\static"

[Code]
var
  Notes: array of TNewStaticText;
  Installing, WasThere: Boolean;     { fixed when the copying starts: then RADIMCOM.exe is always there }

{ the folder chosen on the folder page (before it: the default or the previous one) }
function Dir: String;
begin
  Result := AddBackslash(WizardDirValue);
end;

{ RADIMCOM is already in the folder: installed by this setup (RADIMCOM.exe) or from a zip (data\config.json) }
function IsUpgrade: Boolean;
begin
  if Installing then Result := WasThere
  else Result := FileExists(Dir + 'data\config.json') or FileExists(Dir + 'RADIMCOM.exe');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    WasThere := IsUpgrade;
    Installing := True;
  end;
end;

function IsZipInstall: Boolean;
begin
  Result := IsUpgrade and not FileExists(Dir + 'RADIMCOM.exe');
end;

function DsdInstalled: Boolean;
begin
  Result := FileExists(Dir + 'lib\dsd-fme\dsd-fme.exe');
end;

{ install_dsd.py writes lib\dsd-fme\VERSION.txt; without it: 20260715, the only version before }
function DsdOutdated: Boolean;
var
  V: AnsiString;
begin
  Result := False;
  if not DsdInstalled then Exit;
  if not LoadStringFromFile(Dir + 'lib\dsd-fme\VERSION.txt', V) then V := '20260715';
  Result := Trim(String(V)) <> '{#DsdVersion}';
end;

function NoteText: String;
begin
  if IsZipInstall then Result := CustomMessage('UpgradeZip')
  else if IsUpgrade then Result := CustomMessage('Upgrade')
  else Result := CustomMessage('NewInstall');
end;

procedure UpdateNotes;
var
  I: Integer;
begin
  for I := 0 to GetArrayLength(Notes) - 1 do
  begin
    Notes[I].Caption := NoteText;
    if IsUpgrade then Notes[I].Font.Color := clGreen else Notes[I].Font.Color := clWindowText;
  end;
end;

{ a note at the bottom of a page: new installation / upgrade }
function AddNote(Page: TWizardPage; Top: Integer): TNewStaticText;
begin
  Result := TNewStaticText.Create(Page);
  Result.Parent := Page.Surface;
  Result.AutoSize := False;
  Result.WordWrap := True;
  Result.Left := 0;
  Result.Width := Page.SurfaceWidth;
  Result.Top := Top;
  Result.Height := Page.SurfaceHeight - Top;
  Result.Font.Style := [fsBold];
end;

procedure DirChanged(Sender: TObject);
begin
  UpdateNotes;
end;

procedure InitializeWizard;
var
  D: Integer;
begin
  { the first page (licence): the licence text shorter, the note under it }
  D := ScaleY(66);
  WizardForm.LicenseMemo.Height := WizardForm.LicenseMemo.Height - D;
  WizardForm.LicenseAcceptedRadio.Top := WizardForm.LicenseAcceptedRadio.Top - D;
  WizardForm.LicenseNotAcceptedRadio.Top := WizardForm.LicenseNotAcceptedRadio.Top - D;
  SetArrayLength(Notes, 2);
  Notes[0] := AddNote(PageFromID(wpLicense), WizardForm.LicenseNotAcceptedRadio.Top + WizardForm.LicenseNotAcceptedRadio.Height + ScaleY(4));
  Notes[1] := AddNote(PageFromID(wpSelectDir), WizardForm.DiskSpaceLabel.Top + WizardForm.DiskSpaceLabel.Height + ScaleY(14));
  WizardForm.DirEdit.OnChange := @DirChanged;
  WizardForm.ReadyMemo.WordWrap := True;
  WizardForm.ReadyMemo.ScrollBars := ssVertical;
  UpdateNotes;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo, MemoComponentsInfo,
  MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := NoteText + NewLine + NewLine + MemoDirInfo;
  if MemoTasksInfo <> '' then Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

{ a RADIMCOM server of this folder without RADIMCOM.exe (start.bat of a zip installation: .venv or python\) }
function ConsoleRunning: Boolean;
var
  Wmi, Svc, List: Variant;
  Path: String;
begin
  Result := False;
  try
    Wmi := CreateOleObject('WbemScripting.SWbemLocator');
    Svc := Wmi.ConnectServer('.', 'root\CIMV2');
    Path := Lowercase(Dir);
    StringChangeEx(Path, '\', '\\', True);
    StringChangeEx(Path, #39, '\' + #39, True);
    StringChangeEx(Path, '_', '[_]', True);
    List := Svc.ExecQuery('SELECT ProcessId FROM Win32_Process WHERE Name LIKE ' + #39 + 'python%' + #39
      + ' AND ExecutablePath LIKE ' + #39 + Path + '%' + #39);
    Result := List.Count > 0;
  except
    Result := False;      { WMI not available: nothing to tell }
  end;
end;

{ the mutex of RADIMCOM.exe running from this folder (RADIMCOM.cs: "RADIMCOM-app-" + folder, lower case, \ and : as _);
  another RADIMCOM (e.g. a development copy elsewhere) does not matter }
function AppMutexName: String;
var
  S: String;
begin
  S := Lowercase(RemoveBackslashUnlessRoot(ExpandConstant('{app}')));
  StringChangeEx(S, '\', '_', True);
  StringChangeEx(S, ':', '_', True);
  Result := 'RADIMCOM-app-' + S;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and DirExists(AddBackslash(WizardDirValue) + '.git') then
  begin
    MsgBox(CustomMessage('DevCopy'), mbError, MB_OK);
    Result := False;
  end;
end;

function RunningText: String;
begin
  if CheckForMutexes(AppMutexName) then Result := CustomMessage('Running') else Result := CustomMessage('Console');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if DirExists(ExpandConstant('{app}\.git')) then
  begin
    Result := CustomMessage('DevCopy');
    Exit;
  end;
  while CheckForMutexes(AppMutexName) or ConsoleRunning do
  begin
    if WizardSilent then
    begin
      Sleep(3000);
      if CheckForMutexes(AppMutexName) or ConsoleRunning then begin Result := RunningText; Exit; end;
    end
    else if MsgBox(RunningText, mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := RunningText;
      Exit;
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  D: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    D := ExpandConstant('{app}\data');
    if DirExists(D) and not UninstallSilent then
      if MsgBox(FmtMessage(CustomMessage('DelData'), [D]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(D, True, True, True);
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
