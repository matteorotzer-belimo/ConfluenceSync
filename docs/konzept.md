# ConfluenceSync – Konzept (Entwurf v0.5)

Stand: 02.11.2026 · Basis: `knowledge-bridge-idea.md` · Status: **Entwurf, offene Fragen siehe Abschnitt 12**

## 1. Kurzfassung

ConfluenceSync ist eine **einfache Desktop-App für Kolleginnen und Kollegen**. Sie wird aus dem Git-Repo (GitHub Releases) heruntergeladen, jede Person verbindet **ihr eigenes** Confluence- und OneNote- bzw. Notion-Konto, wählt Notizen aus und veröffentlicht sie als sauber formatierte **Confluence**-Seiten.

Inhalte werden nicht 1:1 kopiert, sondern in ein neutrales Block-Modell übersetzt und daraus Confluence-Storage-Format erzeugt. Jede Veröffentlichung zeigt zuerst eine **Vorschau**; in Confluence von Hand geänderte Seiten werden **nie still überschrieben**.

Die Richtung ist **einseitig**: Quelle → Confluence. Ein Rückweg (Confluence → Notion/OneNote) ist kein Ziel.

## 1a. Zielbild: App für das Team

**Zielgruppe:** Kolleginnen und Kollegen ohne Programmierkenntnisse. Kein Python, kein Git, keine Kommandozeile nötig.

**So soll es sich anfühlen**

1. **Herunterladen:** Im Repo unter *Releases* `ConfluenceSync.exe` (bzw. Setup) laden und starten.
2. **Verbinden (einmalig, Assistent mit 3 Schritten):**
   - **Confluence:** URL ist vorausgefüllt; persönliches Zugriffstoken einfügen (mit Anleitung und Link zur Profilseite) → «Verbindung testen».
   - **OneNote:** «Mit Microsoft anmelden» → normales Belimo-Login im Browser.
   - **Notion:** Token einfügen und Seiten für die Integration freigeben (Anleitung mit Screenshots) – siehe Frage 6.
3. **Nutzen:** Notiz auswählen → Ziel in Confluence wählen (Space + Elternseite) → **Vorschau** → «Veröffentlichen». Später: «Aktualisieren», wenn die Quelle geändert wurde.

**Hauptansichten der UI**

| Ansicht | Inhalt |
|---|---|
| Verbindungen | Status je Dienst (grün/rot), Verbinden/Trennen, Verbindung testen |
| Quellen | Notizbücher/Abschnitte/Seiten (OneNote) bzw. freigegebene Seiten (Notion) durchsuchen und auswählen |
| Vorschau | Seite so, wie sie in Confluence aussehen wird; Hinweise zu nicht übertragbaren Inhalten; Diff bei Aktualisierung |
| Meine Veröffentlichungen | Liste der Zuordnungen mit Status (aktuell / Quelle geändert / in Confluence geändert / Prüfung nötig), Knopf «Aktualisieren» |

**Grundsätze für die Verteilung**

- **Pro Person eigene Anmeldung**, keine geteilten Tokens; die App sieht und schreibt nur, was die Person selbst darf (Confluence-Berechtigungen gelten unverändert).
- **Geheimnisse** (Tokens, Anmeldedaten) nur im Windows-Anmeldeinformationsspeicher (Credential Manager), nie in Dateien oder im Repo.
- **Läuft lokal**, keine Server-Komponente, keine Daten an Dritte ausser den verbundenen Diensten (und optional Azure OpenAI im Belimo-Tenant).
- **Updates:** Die App prüft beim Start, ob es ein neueres Release gibt, und zeigt einen Hinweis mit Link.

## 1b. Bisherige Entscheide (02.11.2026)

| Thema | Entscheid |
|---|---|
| Zielgruppe | Kolleginnen und Kollegen; App herunterladen, eigene Konten verbinden, einfache UI |
| Name | ConfluenceSync (App, exe, Repo) |
| Erste Quelle | OneNote; Notion folgt später |
| Confluence | gleiche Data-Center-Instanz wie Ticket Analytics, persönliches PAT, Space frei wählbar |
| Umfang Verwaltung | ganze Seiten (v1), verwaltete Bereiche später |
| Bilder | ab v1 |
| KI | nicht in v1 |
| IT-Freigaben (Entra-App, exe-Verteilung) | Matteo klärt mit der IT |

## 2. Ausgangslage

- Die Projektdoku von *Belimo Ticket Analytics* wurde im Oktober 2026 von Notion nach Confluence migriert (einmalig, halb von Hand bzw. per KI/Atlassian-MCP).
- Im Repo `belimo_ticket-analytics` existiert mit `scripts/confluence_sync.py` bereits ein erprobter Zwei-Wege-Sync **Repo ↔ Confluence**:
  - Confluence **Data Center** REST API (`/rest/api/content`), Login per Personal Access Token
  - Seiten im Storage-Format (XHTML), Mapping in `pages.json`, Basisstand für 3-Wege-Merge in `.base/`
  - Probelauf als Standard, `--apply` erst nach OK; Versionsprüfung (HTTP 409)
  - Schutzregeln: App-Makros, Bilder/Anhänge, Inline-Kommentare bleiben unverändert; nur erlaubte Gestaltungselemente
- Grundsatz dort: **«Confluence ist führend, das Repo spiegelt.»**

**Folgerung:** ConfluenceSync muss das Rad für Confluence nicht neu erfinden. Neu sind vor allem die **Quell-Connectoren** und der **Formatter** (Quelle → Storage-Format).

## 3. Ziele und Nicht-Ziele

**Ziele**

0. **Einfach für alle:** herunterladen, Konten verbinden, nutzen – ohne Installation von Python o. Ä. und ohne Kommandozeile.
1. Ausgewählte OneNote- bzw. Notion-Seiten per Knopfdruck als Confluence-Seite anlegen oder aktualisieren.
2. Struktur erhalten: Überschriften, Absätze, Listen, Aufgaben, Tabellen, Links, Code, Hinweisblöcke.
3. Einheitliches Seitenbild nach den bestehenden Gestaltungsregeln (Info-Panels, Status-Labels, Inhaltsverzeichnis …).
4. Keine Duplikate: eine Quellseite ↔ genau eine Zielseite.
5. Kein Datenverlust: manuelle Änderungen in Confluence werden erkannt und zur Prüfung gemeldet.
6. Nachvollziehbarkeit: wann wurde was von wo nach wo synchronisiert, mit welchem Ergebnis.

**Nicht-Ziele (vorerst)**

- Zwei-Wege-Sync oder Rückschreiben nach Notion/OneNote
- Löschen oder Verschieben von Confluence-Seiten (nur melden)
- Kommentare, Labels, Berechtigungen, Seitenhistorie der Quelle
- Echtzeit; zuerst manuell, später zeitgesteuert
- Zentraler Server oder gemeinsame Datenbank für das Team (jede Installation ist eigenständig)
- macOS/Linux (zuerst nur Windows)

## 4. Hauptanwendungsfälle

| # | Fall | Beispiel |
|---|---|---|
| A | Notiz → neue Seite | Besprechungsnotiz in OneNote wird Unterseite von «Besprechungen» |
| B | Quelle geändert → Seite aktualisieren | Notiz ergänzt, Confluence-Seite zieht per «Aktualisieren» nach |
| C | Seite wurde in Confluence bearbeitet | App hält an, zeigt Unterschiede, die Person entscheidet |
| D | Vorschau | Vor dem Veröffentlichen sehen, wie die Seite aussehen wird |

## 5. Architektur

```text
                ┌──────────────┐     ┌──────────────┐
OneNote (Graph)▶│ Connectoren  │     │              │
                │ (lesen)      │──▶  │ Inhaltsmodell│──▶ Formatter ──▶ (opt. KI) ──▶ Prüfungen ──▶ Confluence-Client
Notion (API) ──▶│              │     │ (Blöcke)     │     (Storage)                   (Schutzregeln)   (Vorschau/Veröffentlichen)
                └──────────────┘     └──────────────┘                                                     │
                       ▲                                                                                  ▼
                 UI (lokales Fenster) ─────────────── steuert alles ───────────────────▶   SQLite (lokal): Zuordnungen, Verlauf
```

Prinzipien:

- **Quellenunabhängig ab dem Inhaltsmodell** (analog zum Importer-Prinzip in Ticket Analytics): eine neue Quelle = ein neuer Connector, sonst nichts.
- **Python formatiert, KI formuliert höchstens um.** Struktur und Fakten kommen aus der Quelle; ein KI-Schritt darf nichts erfinden und ist abschaltbar.
- **Vorschau ist Pflicht.** Geschrieben wird erst nach «Veröffentlichen» bzw. «Aktualisieren».

## 6. Internes Inhaltsmodell

Das Beispiel aus der Ideenbeschreibung (Abschnitte mit Text-Strings) verliert Formatierung (fett, Links, Verschachtelung, Aufgabenstatus). Vorschlag: ein **Block-Baum** mit Inline-Formatierung, als Pydantic-Modelle.

```json
{
  "source": "notion",
  "source_id": "1a2b…",
  "source_url": "https://www.notion.so/…",
  "title": "Neue Ideen & Verbesserungen",
  "source_edited_at": "2026-11-02T10:15:00Z",
  "blocks": [
    {"type": "heading", "level": 2, "text": [{"text": "Neue Funktionen"}]},
    {"type": "bulleted_list", "items": [
      {"text": [{"text": "KI-Ticketanalyse", "bold": true}]},
      {"text": [{"text": "Dashboard, siehe "}, {"text": "Anleitung", "link": "https://…"}]}
    ]},
    {"type": "task_list", "items": [{"done": false, "text": [{"text": "Mit Uli besprechen"}]}]},
    {"type": "callout", "kind": "info", "children": [ … ]},
    {"type": "unsupported", "source_type": "child_database", "note": "Datenbank-Ansicht nicht übertragbar"}
  ]
}
```

Blocktypen v1: `heading`, `paragraph`, `bulleted_list`, `numbered_list`, `task_list`, `quote`, `callout`, `code`, `table`, `divider`, `toggle`, `image`, `link_to_page`, `unsupported`.

`unsupported` ist wichtig: Nicht übertragbare Inhalte werden **sichtbar** markiert (Hinweis-Panel in der Vorschau), nicht still weggelassen.

## 7. Abbildung Quelle → Confluence (Storage-Format)

### 7.1 OneNote

Microsoft Graph liefert den Seiteninhalt als **HTML** (`GET /me/onenote/pages/{id}/content`). Der Connector übersetzt dieses HTML in das Inhaltsmodell:

| OneNote (HTML) | Confluence | Bemerkung |
|---|---|---|
| `h1`–`h6` | `<h2>`–`<h4>` | Stufen zusammenfassen |
| `p`, `b`/`strong`, `i`/`em`, `a` | `<p>`, `<strong>`, `<em>`, `<a>` | Schriftart/Farben weglassen |
| `ul`/`ol` | `<ul>`/`<ol>` | |
| `p data-tag="to-do"` / `to-do:completed` | `ac:task-list` | OneNote-Kategorien («Aufgabe») |
| andere `data-tag` (wichtig, Frage …) | Status-Label oder Hinweis-Panel | Zuordnung festlegen |
| `table` | `<table>` | |
| `img` | Anhang + `ac:image` | Bild über Graph laden (`data-fullres-src`), **ab v1** |
| `object` (Dateianhang), Freihand/Ink, frei positionierte Container | `unsupported` (gelber Hinweis) | Freiform-Layout geht verloren; Reihenfolge nach Position oben → unten |

### 7.2 Notion

| Notion-Block | Confluence | Bemerkung |
|---|---|---|
| `heading_1/2/3` | `<h2>/<h3>/<h4>` | Seitentitel ist keine Inhaltsüberschrift, darum eine Stufe tiefer |
| `paragraph` + Annotations | `<p>`, `<strong>`, `<em>`, `<code>`, `<a>` | Farben/Hintergrund vorerst weglassen |
| `bulleted/numbered_list_item` | `<ul>/<ol>` (verschachtelt) | |
| `to_do` | `ac:task-list` | `task-id` pro Seite eindeutig |
| `toggle` | Makro `expand` | |
| `callout` | Makro `info`/`note`/`tip`/`warning` | Zuordnung über Emoji/Farbe, Standard `info` |
| `quote` | `<blockquote>` | |
| `code` | Makro `code` (Sprache übernehmen) | |
| `table` | `<table>` | erste Zeile als `<th>`, falls in Notion so markiert |
| `divider` | `<hr/>` | |
| `link_to_page` / Erwähnung | Link auf Confluence-Seite, falls veröffentlicht, sonst Notion-URL | |
| `image` | Anhang + `ac:image` | Phase 5 (Notion-Datei-URLs laufen nach ca. 1 h ab → herunterladen und hochladen) |
| `child_page` | eigene Unterseite (optional) | |
| `child_database`, `synced_block`, `embed`, `column_list` | `unsupported` bzw. vereinfacht | Spalten evtl. später als `ac:layout` |

Erlaubt sind nur die Elemente aus der Gestaltungsliste in `docs/confluence/README.md` (Ticket Analytics).

## 8. Synchronisation und Schutz vor Überschreiben

### 8.1 Zustand pro Mapping (SQLite)

| Feld | Zweck |
|---|---|
| `source`, `source_id`, `source_edited_at`, `source_hash` | Hat sich die Quelle geändert? |
| `confluence_page_id`, `space`, `parent_id` | Ziel (über **IDs**, nicht Titel) |
| `published_version`, `published_hash` | Was hat ConfluenceSync zuletzt hochgeladen? |
| `status` | `synced` / `pending` / `review` / `error` |
| `last_run_at`, `last_error` | Fehlerverfolgung |

Zusätzlich Tabelle `sync_runs` (Lauf-ID, Zeit, Modus Probelauf/apply, Ergebnis je Seite).

### 8.2 Entscheidungslogik

| Quelle geändert? | Confluence seit letztem Upload geändert? | Aktion |
|---|---|---|
| nein | nein | nichts |
| ja | nein | «Quelle geändert» anzeigen; nach Vorschau aktualisieren |
| nein | ja | nichts, als «in Confluence geändert» melden |
| ja | ja | **Prüfung nötig**: nichts schreiben, Unterschiede zeigen, die Person entscheidet (Confluence behalten / mit Quelle überschreiben) |

«In Confluence geändert» = aktuelle Version ≠ `published_version` **und** Inhalt-Hash ≠ `published_hash` (Versionen ohne Inhaltsänderung, z. B. nur Titel/Labels, lösen keinen Review aus).

### 8.3 Verwaltete Bereiche (Option)

Statt ganzer Seiten verwaltet ConfluenceSync nur einen markierten Abschnitt (z. B. zwischen zwei `anchor`-Makros `kb-start`/`kb-end`). Inhalte ausserhalb, etwa eine manuelle Bewertung unten auf der Ideen-Seite, bleiben unangetastet. **Empfehlung:** v1 ganze Seiten, verwaltete Bereiche als erste Erweiterung.

### 8.4 Kennzeichnung

Oben auf jeder erzeugten Seite ein kleines Info-Panel: «Erstellt mit ConfluenceSync aus OneNote/Notion (Link zur Quelle) · Änderungen bitte in der Quelle vornehmen · Stand: …».

## 9. Technik der App

**Empfehlung:** gleicher Stack wie Ticket Analytics, verpackt als Windows-App.

| Baustein | Wahl | Warum |
|---|---|---|
| Kern | Python 3.12, Pydantic v2, `requests`/`httpx` | bekannt, Confluence-Code aus `confluence_sync.py` wiederverwendbar |
| UI | FastAPI + schlichtes HTML/CSS/JS (ohne Build-Schritt), angezeigt in einem eigenen Fenster mit **pywebview** (nutzt Edge WebView2, auf Windows 10/11 vorhanden) | wie Ticket Analytics; fühlt sich wie eine normale App an, kein Browser-Tab |
| Verpackung | **PyInstaller** → eine `ConfluenceSync.exe` (oder kleiner Installer) | Kolleginnen brauchen kein Python |
| Verteilung | **GitHub Actions** baut bei jedem Versions-Tag die exe und legt sie unter *Releases* ab | «aus dem Git-Repo herunterladen» ohne Git-Kenntnisse |
| Microsoft-Login | **MSAL** (öffentlicher Client, interaktive Anmeldung, Token-Cache verschlüsselt) | Standard für Microsoft Graph |
| Geheimnisse | **keyring** → Windows-Anmeldeinformationsspeicher | keine Tokens in Dateien |
| Lokale Daten | `%APPDATA%\ConfluenceSync\` (`settings.json`, `kb.db` mit Zuordnungen und Verlauf) | pro Person, kein Server |

Alternativen (nicht empfohlen für v1): Electron/Tauri (schöner, aber neue Sprache und grösserer Aufwand), PySide6/Qt (nativ, aber viel mehr UI-Code).

### 9.1 Anmeldung pro Dienst

| Dienst | Verfahren | Was die Person tun muss | Voraussetzung Belimo-IT |
|---|---|---|---|
| Confluence (Data Center) | persönliches Zugriffstoken (PAT) | Token im Profil erstellen und einfügen (Anleitung in der App) | keine (Funktion ist bereits nutzbar) |
| OneNote (Microsoft Graph) | Microsoft-Anmeldung, delegierte Rechte `Notes.Read`, `User.Read` | «Mit Microsoft anmelden» | **App-Registrierung in Entra ID** (öffentlicher Client), evtl. Admin-Zustimmung |
| Notion | Token einer Notion-Integration | Token einfügen, Seiten mit der Integration teilen | Notion-Integration erstellen (meist nur Workspace-Owner); OAuth würde ein Client-Secret und damit einen Server brauchen → siehe Frage 6 |

### 9.2 Einstellungen

Firmenweite Vorgaben werden **mit der App ausgeliefert** (Confluence-URL, Entra-Client-ID, erlaubte Gestaltungselemente). Persönliches (Zuordnungen, bevorzugter Space, letzte Elternseiten) speichert die App lokal. Zuordnungen über **IDs**, damit Umbenennungen nichts kaputt machen.

## 10. Bedienung

**Für Kolleginnen und Kollegen: nur die UI** (siehe Abschnitt 1a). Typischer Ablauf «Veröffentlichen»:

1. Quelle wählen (Notizbuch → Abschnitt → Seite).
2. Ziel wählen: Space und Elternseite (Suche mit Vorschlägen, zuletzt verwendete oben).
3. Vorschau prüfen: Seite gerendert, gelbe Hinweise für nicht übertragbare Inhalte.
4. «Veröffentlichen» → Link zur neuen Confluence-Seite.

«Aktualisieren» zeigt zusätzlich, was sich ändert. Wurde die Seite in Confluence von Hand geändert, bietet die App drei Wege an: *Confluence-Version behalten*, *mit Quelle überschreiben* (mit Warnung), *Abbrechen*.

**Für die Entwicklung:** zusätzlich ein kleines CLI (`csync preview`, `csync sync --apply`) zum Testen ohne UI.

## 11. Phasenplan

| Phase | Inhalt | Ergebnis |
|---|---|---|
| **0 – Klären** | offene Fragen (Abschnitt 12); Freigaben bei der IT: App-Registrierung, Verteilung einer exe, Notion | entschiedenes Konzept, Freigaben beantragt |
| **1 – Kern** | Inhaltsmodell, Formatter, Confluence-Client (aus `confluence_sync.py`), Connector für **OneNote** (erste Quelle) inkl. **Bilder als Anhänge**, SQLite, Entwickler-CLI, Tests mit synthetischen Daten | eine Seite zuverlässig nach Confluence (nur auf deinem Rechner) |
| **2 – UI** | Fenster mit Verbinden-Assistent, Quellen-Auswahl, Vorschau, Veröffentlichen, «Meine Veröffentlichungen» | bedienbar ohne Kommandozeile |
| **3 – Verteilen** | exe mit PyInstaller, Release per GitHub Actions, Update-Hinweis, Kurzanleitung; **Pilot mit 2–3 Kolleginnen/Kollegen** | erste Nutzer, Rückmeldungen |
| **4 – Zweite Quelle** | Notion | beide Quellen |
| **5 – Robust** | ganze Abschnitte/Unterseiten, verwaltete Bereiche, Links zwischen veröffentlichten Seiten, Notion-Bilder | Alltagstauglich |
| **6 – Extras** | KI-Schritt (Azure OpenAI im Tenant), automatisches Aktualisieren, weitere Quellen | |

## 12. Offene Fragen

**Zweck und Abgrenzung**

1. ~~Wer schreibt künftig in Notion?~~ **Beantwortet:** Die App wird für Kolleginnen und Kollegen gebaut: herunterladen, eigene Konten verbinden, einfache UI.
1b. ~~Welche Quelle zuerst?~~ **Entschieden: OneNote zuerst** (Microsoft-Login, bei Belimo verbreitet). Notion folgt in Phase 4.
1c. **Wie viele Personen** etwa, und nutzen sie Notion überhaupt (eigener Belimo-Workspace oder privat)?
2. **Verhältnis zu `confluence_sync.py`:** Seiten, die ConfluenceSync verwaltet, sollten im Ticket-Analytics-Spiegel ausgenommen werden (`exclude_ids`), damit nicht zwei Werkzeuge dieselbe Seite schreiben.
3. **Gemeinsamer Code:** Confluence-Client und Prüfungen aus `confluence_sync.py` kopieren oder als gemeinsames Paket herauslösen? (Empfehlung v1: kopieren.)
4. ~~Name?~~ **Entschieden: ConfluenceSync** (App, exe und Repo).

**IT, Verteilung und Zugang**

5. ~~Confluence-Instanz und Spaces?~~ **Entschieden:** gleiche Data-Center-Instanz wie Ticket Analytics, Anmeldung mit persönlichem PAT; jede Person wählt Space und Elternseite selbst (nur, wo sie Schreibrechte hat).
6. Notion: Gibt es einen Belimo-Workspace und eine Person mit Owner-Rechten, die eine Integration anlegt? Hinweis: Eine interne Notion-Integration hat **einen** Token pro Workspace und sieht alles, was mit ihr geteilt wurde, nicht die Rechte der einzelnen Person.
7. OneNote: Wer bei der IT macht die **Entra-App-Registrierung** (öffentlicher Client, delegiert `Notes.Read`)? Braucht es Admin-Zustimmung? → **Grundsätzlich möglich, Matteo klärt mit der IT** (zusammen mit Frage 8).
8. **Darf eine selbst gebaute exe verteilt werden?** Unsignierte exe lösen eine SmartScreen-Warnung aus und können durch Endpoint-Schutz/AppLocker blockiert werden. Gibt es ein Code-Signing-Zertifikat oder einen Weg über die Softwareverteilung (Intune/Company Portal)?
9. **Repo-Zugriff:** Das Repo liegt unter `matteorotzer-belimo`. Haben die Kolleginnen einen GitHub-Zugang, bzw. soll das Repo/Release für sie sichtbar sein? Alternative: exe über Teams/SharePoint verteilen.

**Inhalt und Verhalten**

10. ~~Ganze Seiten oder verwaltete Bereiche?~~ **Entschieden:** v1 verwaltet **ganze Seiten** (manuelle Änderungen → Warnung beim Aktualisieren); verwaltete Bereiche in Phase 5.
11. Sollen ganze OneNote-**Abschnitte** auf einmal veröffentlicht werden können (Übersichtsseite + je Seite eine Unterseite)? **Annahme v1: nur einzelne Seiten**, Abschnitte später – noch offen.
12. Wird eine Quellseite gelöscht: Confluence-Seite nur melden oder mit Status-Label «ARCHIVIERT» versehen? (Vorschlag v1: nur in «Meine Veröffentlichungen» melden.)
13. ~~Bilder im ersten Release?~~ **Entschieden: ja**, Bilder/Screenshots ab v1 (aus OneNote laden, als Anhang hochladen, mit `ac:image` einbinden). Andere Dateianhänge (PDF, Office) als Hinweis.

**KI und Datenschutz**

14. Welche Inhalte werden veröffentlicht? Gelten die Regeln aus Ticket Analytics (keine echten Ticketdaten, keine Personendaten)? Braucht es einen Hinweis in der App?
15. ~~KI in v1?~~ **Entschieden: kein KI-Schritt in v1.** Falls später: nur Azure OpenAI im Belimo-Tenant, standardmässig aus, jede Änderung in der Vorschau sichtbar.

## 13. Risiken

| Risiko | Auswirkung | Massnahme |
|---|---|---|
| exe wird von Windows/Endpoint-Schutz blockiert | Kolleginnen können die App nicht starten | früh mit IT klären (Signierung, Intune), Pilot vor breiter Verteilung |
| Fehlende Freigabe für Entra-App bzw. Notion-Integration | Quelle nicht nutzbar | in Phase 0 beantragen; Kern zuerst mit der freigegebenen Quelle bauen |
| Manuelle Confluence-Änderung wird überschrieben | Datenverlust | Versions- + Hash-Prüfung, Vorschau, Warnung vor Überschreiben |
| Tokens werden unsicher gespeichert oder geteilt | Sicherheitsvorfall | nur Credential Manager, jede Person eigene Anmeldung, nie Logs mit Tokens |
| Quell-Inhalte ohne Entsprechung (OneNote-Freiform, Notion-Datenbanken) | Inhalt fehlt still | `unsupported`-Block, gelber Hinweis in der Vorschau |
| Unterschiedliche Versionen bei den Nutzern | Fehler schwer nachvollziehbar | Versionsnummer in der App, Update-Hinweis, Log-Datei zum Mitschicken (ohne Inhalte/Tokens) |
| Rate-Limits (Notion ca. 3 Anfragen/s, Graph-Drosselung) | langsame oder abgebrochene Läufe | Drosselung, Wiederholung mit Backoff |
| Support-Aufwand für dich | Zeit | gute Fehlermeldungen in der App, Kurzanleitung in Confluence, Pilotgruppe klein halten |
| KI verändert Aussagen | falsche Doku | KI standardmässig aus, nur Formulierung, Diff in Vorschau |

## 14. Vorgeschlagene Repo-Struktur

```text
ConfluenceSync/
├─ confluencesync/
│  ├─ connectors/               onenote.py, notion.py
│  ├─ model.py                  Inhaltsmodell (Pydantic)
│  ├─ formatter/                storage.py (Modell → XHTML), html_preview.py
│  ├─ confluence/               client.py, checks.py (aus confluence_sync.py)
│  ├─ auth/                     msal_login.py, secrets.py (keyring)
│  ├─ sync/                     planner.py (Entscheidungslogik), publisher.py
│  ├─ store.py                  SQLite: Zuordnungen, Verlauf
│  └─ cli.py                    Entwickler-CLI
├─ app/
│  ├─ server.py                 FastAPI (nur 127.0.0.1)
│  ├─ main.py                   startet Server + pywebview-Fenster
│  └─ static/                   HTML/CSS/JS
├─ packaging/                   PyInstaller-Spec, Icon
├─ .github/workflows/release.yml   exe bauen und als Release veröffentlichen
├─ tests/                       nur synthetische API-Antworten (JSON-Fixtures)
├─ requirements.txt
└─ README.md                    Anleitung für Nutzer + Entwickler
```
