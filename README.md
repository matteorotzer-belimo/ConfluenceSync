# ConfluenceSync

ConfluenceSync ist eine Windows-App, die Notizen aus **OneNote** und **Notion** als sauber formatierte Seiten in **Confluence (Data Center)** veröffentlicht. Sie richtet sich an alle, die nicht programmieren: herunterladen, starten, der Anleitung folgen.

- Läuft lokal auf deinem Laptop. Python, Git oder Kommandozeile brauchst du nicht.
- Du verbindest deine eigenen Konten und trägst alle Zugangsdaten direkt in der App ein.
- Vor jedem Veröffentlichen siehst du eine Vorschau.
- Wurde eine veröffentlichte Seite in Confluence von Hand geändert, wird sie nicht still überschrieben. Die App fragt dich.
- Die Richtung ist immer Quelle → Confluence.

Das Fachkonzept steht in [`docs/konzept.md`](docs/konzept.md).

---

## Für Anwenderinnen und Anwender

### 1. Herunterladen

1. Öffne die Seite [**Releases**](../../releases/latest) dieses Repos.
2. Lade `ConfluenceSync.exe` herunter und lege die Datei an einen festen Ort, z. B. `Dokumente\ConfluenceSync\`. Installieren musst du nichts.
3. Starte die App mit einem Doppelklick.

> **Windows-SmartScreen:** Die exe ist noch nicht digital signiert. Darum kann beim ersten Start die Meldung «Der Computer wurde durch Windows geschützt» erscheinen. Klicke auf **Weitere Informationen** und dann auf **Trotzdem ausführen**. Falls dein Gerät das nicht erlaubt, wende dich an die IT.
>
> Prüfsumme (optional): Jedes Release enthält die Datei `ConfluenceSync.exe.sha256`. Zum Vergleichen führst du in PowerShell `Get-FileHash .\ConfluenceSync.exe` aus.

### 2. Erster Start: die Anleitung

Beim ersten Start führt dich eine Anleitung in fünf Schritten durch die Einrichtung:

1. **Willkommen:** Was die App macht und was du brauchst.
2. **Confluence verbinden:** Du trägst die Adresse deines Confluence und einen **persönlichen Zugriffstoken** ein. Die App zeigt dir, wo du den Token erstellst: Profilbild → Einstellungen → Persönliche Zugriffstoken.
3. **Zielort wählen:** In welchen Bereich (Space) und unter welche Seite neue Seiten kommen. Es erscheinen nur Bereiche, in denen du schreiben darfst.
4. **Notizen verbinden:** OneNote, Notion oder beides (siehe unten).
5. **Fertig:** Eine kurze Erklärung der Status-Anzeigen.

Du kannst die Anleitung jederzeit wieder starten: **Einstellungen → Anleitung erneut starten**.

### 3. Notizen veröffentlichen

1. **Notizen:** Wähle Notizbuch → Abschnitt → Seite.
2. **Vorschau:** So sieht die Seite in Confluence aus. Elemente, die nicht übernommen werden können, sind markiert.
3. **Veröffentlichen:** Prüfe Titel und Zielort und veröffentliche die Seite.
4. **Meine Veröffentlichungen:** Alle veröffentlichten Seiten mit ihrem Status:

| Status | Bedeutung |
|---|---|
| Aktuell | Confluence und Quelle stimmen überein. |
| Quelle geändert | Die Notiz wurde geändert. «Aktualisieren» übernimmt die Änderung. |
| In Confluence geändert | Jemand hat die Seite in Confluence bearbeitet. Du entscheidest: Confluence behalten, mit der Quelle überschreiben oder abbrechen. |
| Prüfung nötig | Beides wurde geändert, oder die Seite fehlt. Entscheide in der Vorschau. |

### OneNote: Was die IT einmalig einrichten muss

Für OneNote braucht die App eine App-Registrierung in Microsoft Entra ID. Den folgenden Text zeigt die App auch selbst an, mit einem Button «Text kopieren». So kannst du ihn direkt an die IT weitergeben:

- Unterstützte Kontotypen: nur Konten in diesem Organisationsverzeichnis
- Plattform «Mobile und Desktopanwendungen», Umleitungs-URI `http://localhost`
- «Öffentliche Clientflows zulassen»: Ja (ohne Client-Geheimnis)
- API-Berechtigungen, Microsoft Graph, delegiert: `Notes.Read`, `User.Read`

Danach gibt dir die IT zwei Werte: die **Anwendungs-ID (Client-ID)** und die **Verzeichnis-ID (Tenant-ID)**. Trage beide in der App unter **Verbindungen → OneNote** ein. Anschliessend meldest du dich wie gewohnt mit deinem Microsoft-Konto an.

### Notion

1. Erstelle unter <https://www.notion.so/my-integrations> eine **interne Integration**.
2. Kopiere das Token und trage es in der App ein.
3. Gib die gewünschten Notion-Seiten für die Integration frei: Seite → «•••» → Verbindungen.

### Demo-Modus

Mit `ConfluenceSync.exe --demo` probierst du die App ohne echte Konten aus. Am einfachsten legst du dafür eine Verknüpfung an und hängst `--demo` hinten an das Ziel an. Die App verwendet dann Beispiel-Notizen und ein simuliertes Confluence, und es wird nichts gesendet.

### Datenschutz und Sicherheit

- **Wo die Zugangsdaten liegen:**
  - Confluence- und Notion-Token: nur in der **Windows-Anmeldeinformationsverwaltung**.
  - Microsoft-Anmeldung: in einem verschlüsselten Cache.
  - Zugangsdaten stehen nie in Klartextdateien oder in Logs.
- **Lokale Daten** in `%APPDATA%\ConfluenceSync\`:
  - Einstellungen
  - Zuordnungen Notiz ↔ Confluence-Seite und Verlauf (SQLite)
  - Log, ohne Zugangsdaten
- **Verbindungen:** Die App verbindet sich nur mit
  - deinem Confluence
  - Microsoft Graph
  - Notion
  - GitHub (für den Update-Hinweis)

### Updates

Beim Start prüft die App, ob es auf GitHub eine neuere Version gibt, und zeigt dann einen Hinweis. Diese Prüfung kannst du in den Einstellungen abschalten. Für ein Update lädst du die neue exe herunter und ersetzt die alte. Deine Einstellungen bleiben erhalten.

---

## For developers

Code, comments and docstrings are in English. UI texts are in German with Swiss spelling: «ss» instead of «ß», informal «du».

### Architecture

```
confluencesync/
  model.py            source-independent content model (block tree + inline marks)
  connectors/         OneNote (Graph HTML -> model), Notion (blocks -> model), demo data
  formatter/          model -> Confluence storage format; model -> preview HTML (QTextBrowser)
  confluence/         Data Center REST client (PAT bearer) + storage-format safety checks
  sync/               planner (status / change detection) and publisher (create, update, images)
  auth/               MSAL public-client login (encrypted cache), keyring secrets
  store.py            SQLite mappings + history;  settings.py  JSON settings (no secrets)
  services.py         Qt-free application facade used by the UI (and tests)
  ui/                 PySide6 desktop UI (tutorial, sources, preview, publications, connections, settings)
```

**Deviation from the concept:** The concept proposed FastAPI with pywebview and an HTML UI. The user decided on a **native PySide6 (Qt) app** instead. The core and the connectors don't depend on the UI.

### Run from source

Use Python **3.12**. Create the venv in a **short path**. PySide6 contains very long file paths, so installing it inside a deep worktree fails unless Windows long paths are enabled.

```powershell
py -3.12 -m venv $env:LOCALAPPDATA\csvenv
& $env:LOCALAPPDATA\csvenv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt

python -m confluencesync --demo          # demo mode: sample notes, simulated Confluence
python -m confluencesync                 # real mode
```

To use a different data folder than `%APPDATA%\ConfluenceSync`, set `CONFLUENCESYNC_HOME`. Demo mode never touches the Windows Credential Manager.

### Tests

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
```

The tests use only synthetic fixtures and mocked HTTP. Network access is blocked and there are no real credentials.

### Screenshots

```powershell
python tools/screenshots.py <output-folder>
```

The script walks through the demo flow and saves a PNG of every view.

### Build the exe locally

```powershell
$env:QT_QPA_PLATFORM = "offscreen"; python tools/make_icon.py; Remove-Item Env:QT_QPA_PLATFORM
pyinstaller packaging/ConfluenceSync.spec --noconfirm
.\dist\ConfluenceSync.exe --demo
```

`--smoke-test` opens the window, closes it after 2 s and writes `smoke test ok` to the log. CI relies on this.

### Release

1. Bump `__version__` in `confluencesync/__init__.py` (e.g. `0.2.0`) and commit.
2. Tag the commit and push the tag: `git tag v0.2.0` followed by `git push origin v0.2.0`.
3. `.github/workflows/release.yml` then runs on `windows-latest`. It runs the tests, builds `ConfluenceSync.exe`, smoke-tests it, and publishes a GitHub Release with the exe and its SHA-256 checksum. The tag must match `__version__`.

`.github/workflows/tests.yml` runs the test suite on every push and pull request.

### Rules for this public repository

- Never commit company-internal URLs, host names, tokens or real note content.
- Tests and fixtures must be synthetic.
