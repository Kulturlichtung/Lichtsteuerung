# Kulturlichtung – Lichtsteuerung

Setup für eine Mehr-Spot-RGBW/RGBWW-Lichtanlage mit QLC+ (Q Light Controller+), inklusive
Sound-to-Light mit automatischer Takterkennung übers Mikrofon (kein manuelles Tempo-Tippen) und
optionaler Intensitäts-gesteuerter Ebenen-Automatik. Zielsystem ist ein unbeaufsichtigter
Raspberry Pi, bedient übers Tablet (QLC+ Web Access) — siehe Pi-Guide weiter unten.

Für tiefere technische Details, Bugs, Testergebnisse und Design-Entscheidungen (inkl. warum
bestimmte Ansätze verworfen wurden) siehe `CLAUDE.md` — dieses README ist die praktische
Kurzanleitung, `CLAUDE.md` das ausführliche Entwickler-Logbuch.

## Dateien in diesem Repo

- **`qlcplus5/`** — QLC+5-Ordner. `2026-07_kulturlichtung_v2.qxw` ist ein eingefrorenes Backup
  (letzter stabiler Stand, fester Zeittakt statt Musiksynchronisation).
  `2026-07_kulturlichtung_v3.qxw` war der erste Cue-List/OSC-Prototyp, mittlerweile durch die
  QLC+4-Linie überholt. **QLC+5 ist auf dem aktuellen Windows-Testrechner nicht mehr
  installiert** (Stand 2026-07-30) — dieser Ordner ist historisch, nicht mehr die aktive
  Arbeitsumgebung.
- **`qlcplus4/`** — die aktive Linie, läuft auf QLC+4.14.4 (klassische Qt-Widgets-UI):
  - `2026-07_kulturlichtung_v4.qxw` — 1:1-Port von v3 auf QLC+4.
  - **`2026-07_kulturlichtung_v5.qxw` — die echte Produktions-/Venue-Datei.** Vom Nutzer selbst
    in QLC+4 erstellt und gepflegt (`<Author>reich</Author>`), reale Fixtures, reales DMX-USB-
    Interface, Beat-OSC bereits live verdrahtet. **Höheres Risiko beim Bearbeiten** als alle
    anderen Dateien hier — echter Show-Content, kein Test/Prototyp.
  - `2026-07_kulturlichtung_v6.qxw` — Claude-Fork von v5, fügt eine 4. Sound-to-Light-Ebene
    ("Alternierend mit Aus") sowie das **Auto-Layer-Feature** (Intensitäts-gesteuerte
    automatische Ebenen-Auswahl, siehe unten) hinzu. **Noch Entwurf**, kein bestätigter Ersatz
    für `v5.qxw` — Details/Teststand in `CLAUDE.md`.
- **`beat-detector/`** — Python-Skript (`beat_osc.py`) mit zwei unabhängigen Features:
  1. Takterkennung übers Mikrofon → OSC an eine QLC+ Cue-List ("Next Cue").
  2. Auto-Layer: Lautstärke-basierte automatische Ebenen-Auswahl über QLC+ Web Access'
     WebSocket-Protokoll (siehe eigener Abschnitt unten).
- **`pi-setup/`** — Config-Vorlage, Start-Skripte und systemd-Units für den unbeaufsichtigten
  Raspberry-Pi-Betrieb (siehe Pi-Guide unten).
- **`CLAUDE.md`** — technische Entwickler-Doku (Design-Entscheidungen, gefundene Bugs,
  Quellcode-Verifikationen gegen `mcallegari/qlcplus`).

## Wie das Zusammenspiel funktioniert

```
Mikrofon → beat_osc.py (erkennt Beat) → OSC → QLC+ (Cue-List "Next Cue")
                                                    → Chaser schaltet Farbe weiter

Mikrofon → beat_osc.py (misst Lautstärke) → WebSocket → QLC+ Web Access
                                                    → Ebenen-Button wird gedrückt
Tablet   → QLC+ Web Access (Browser)      → derselbe WebSocket, beide Richtungen
```

QLC+s eigene interne Takterkennung (`TempoType`/`BeatGenerator`) funktioniert auf keiner
getesteten Version zuverlässig — deshalb übernimmt `beat_osc.py` die Takterkennung komplett
extern (Details/Belege in `CLAUDE.md`).

## Lokal testen (Windows)

**Voraussetzungen:**
- Python 3.9+
- QLC+4.14.4, `qlcplus4/2026-07_kulturlichtung_v6.qxw` geöffnet (zum Testen des Auto-Layer-
  Features; für reine Takterkennung tut's auch `v5.qxw`)

**1. Python-Abhängigkeiten installieren**
```
cd beat-detector
pip install -r requirements.txt
```
Falls `pip install pyaudio` unter Windows fehlschlägt (fehlender Compiler): fertiges Wheel
über `pip install pipwin && pipwin install pyaudio` nachziehen.

**2. Audiogerät finden**
```
python beat_osc.py --list-devices
```

**3. Takterkennung einrichten (einmalig, in QLC+)**
1. Input/Output Manager → OSC-Input-Zeile, Port **7700**.
2. Input-Profil für die OSC-Zeile anlegen, Auto-Detect bei laufendem `beat_osc.py` (fängt
   `/beat` live ein).
3. Cue-List-Widget → External Input für "Next Cue" → Auto Detect.

**4. Takterkennung starten**
```
python beat_osc.py --device <Index>
```
Konsole zeigt bei jedem erkannten Beat eine Zeile.

Bei Bedarf `--sensitivity` (niedriger = empfindlicher) und `--refractory-ms` anpassen.

## Auto-Layer: Intensitäts-gesteuerte Ebenen-Auswahl

Zusätzlich zur Takterkennung: `beat_osc.py --auto` schaltet pro Farbkombo automatisch zwischen
4 Ebenen (Fade/Direkt/Alternierend/Alternierend mit Aus) je nach Musik-Lautstärke. Bedienung
läuft komplett über **QLC+ Web Access** (Tablet-Browser) — passt zum unbeaufsichtigten Betrieb,
keine Tastatur am Pi nötig.

**Voraussetzungen:**
- QLC+ mit `-w` (bzw. `-wp <port>` für abweichenden Port, Standard `9999`) gestartet.
- `websocket-client` installiert (in `requirements.txt` enthalten).

**Start:**
```
python beat_osc.py --auto --device <Index>
```
Verbindet sich mit `ws://127.0.0.1:9999/qlcplusWS` (Host/Port über `--host`/`--web-port`
änderbar). Farbauswahl passiert **im Tablet/Browser** über die "Auto `<Farbe>`"-Buttons in der
Virtual Console. `--startup-auto-color <farbe>` presst diesen Button einmalig automatisch beim
Verbindungsaufbau — für den unbeaufsichtigten Boot auf dem Pi (siehe unten), ohne dass wer ans
Tablet muss.

**Kein OSC-Wiring nötig** — läuft komplett über Web Access' eigenes WebSocket-Protokoll
(Widget-IDs direkt aus der `.qxw`), kein Auto-Detect, kein Input/Output Manager. Details, warum
der ursprüngliche OSC-Feedback-Ansatz verworfen wurde: `CLAUDE.md`.

**Stand 2026-07-30:** Toggle-Verhalten und WebSocket-Anbindung live getestet, funktionieren.
Noch kein vollständiger End-to-End-Test mit echter Musik über einen ganzen Abend. `v6.qxw` ist
weiterhin ein Entwurf, kein bestätigter Ersatz für `v5.qxw`.

---

## Raspberry Pi: Schritt-für-Schritt-Einrichtung

Zielbild: Pi steckt an Strom, fährt hoch, startet automatisch QLC+ (mit dem auf dem USB-Stick
konfigurierten Projekt) + `beat_osc.py --auto` + eine vorgewählte Auto-Farbe — ganz ohne
Bedienperson. Bedienung danach übers Tablet (QLC+ Web Access). Root-Dateisystem ist
schreibgeschützt (übersteht abruptes Trennen der Stromversorgung ohne SD-Karten-Korruption); der
USB-Stick bleibt normal beschreibbar für Projektdatei + Konfiguration.

**Hardware-Hinweis:** Getestet/dokumentiert für Raspberry Pi 5 (4GB), Raspberry Pi OS
(Bookworm, 64-bit) — z. B. das Bundle mit vorinstallierter SD-Karte, wie
[hier](https://www.reichelt.de/de/de/shop/produkt/das_raspberry_pi_5_b_4gb_black_bundle-362101)
erhältlich. Andere 64-bit-Pi-Modelle (4, 400, Zero 2W) sollten mit denselben Schritten
funktionieren, ungetestet.

**Alternative, ungenutzt hier:** QLC+ bietet ein fertiges, kostenpflichtiges (~20€) Pi-Image
mit vorinstalliertem QLC+ und eigenem Autostart-Mechanismus
([qlcplus.org/discover/raspberry-pi](https://www.qlcplus.org/discover/raspberry-pi)). Nicht
verwendet, weil: anderes Basis-OS (RaspiOS Trixie statt des mitgelieferten Bookworm), weniger
Kontrolle über das eigene Config-Datei-/USB-Stick-/`beat_osc.py`-Setup unten. Für wen "einfach
ein fertiges Image" reicht, ist das trotzdem eine legitime Abkürzung.

### 0. Was am Ende wo liegt

| Was | Wo | Warum |
|---|---|---|
| QLC+ (Programm), `beat_osc.py`-Code + venv | Pi-Root (`/opt/lichtsteuerung`) | Überlebt Reboot durch Overlay-Schutz, ändert sich zur Laufzeit eh nicht |
| `.qxw`-Projektdateien, `lichtsteuerung.conf` | USB-Stick (`/mnt/usbdata`) | Muss editierbar bleiben, ohne den Pi anzufassen |

### 1. Raspberry Pi OS vorbereiten

**SSH ist nicht von Haus aus aktiv** (seit 2016 standardmäßig aus) und **es gibt seit 2022 kein
Standard-Login mehr** (kein `pi`/`raspberry` automatisch) — Nutzername/Passwort + SSH müssen
einmal explizit gesetzt werden, sonst braucht's für den allerersten Start Monitor+Tastatur am
Pi. Am saubersten dafür der [Raspberry Pi Imager](https://www.raspberrypi.com/software/), auch
wenn die mitgelieferte SD-Karte schon ein Image drauf hat — Neuflashen erledigt SSH- und
Zugangsdaten-Setup in einem Rutsch, damit ab dem ersten Boot alles per SSH geht:

1. Raspberry Pi Imager installieren (Windows/macOS/Linux).
2. Gerät **Raspberry Pi 5**, Betriebssystem **"Raspberry Pi OS (64-bit)"** (Bookworm-basiert)
   auswählen, Ziel-SD-Karte wählen.
3. **Vor** dem Schreiben: Zahnrad-Symbol (erweiterte Optionen) → Hostname setzen (z. B.
   `lichtsteuerung`), **SSH aktivieren** (Passwort-Auth reicht, kein eigenes Schlüsselpaar
   nötig), **Nutzername + Passwort** setzen (frei wählbar, kein `pi`/`raspberry` mehr),
   optional WLAN-Zugangsdaten falls kein LAN-Kabel am Zielort. Schreiben.
4. SD-Karte in den Pi, Strom dran, ~30–60s warten, dann von einem anderen Rechner im selben
   Netz:
   ```
   ssh <gewählter-Nutzername>@<hostname>.local
   ```
   (oder IP aus der Router-Oberfläche, falls `.local`/mDNS nicht auflöst). Ab hier läuft der
   komplette Rest dieser Anleitung remote — kein Monitor/Tastatur am Pi mehr nötig.

**Alternative: mitgelieferte SD-Karte unverändert lassen, Ersteinrichtungs-Assistent nutzen**
(einmalig Monitor+Tastatur+Maus am Pi nötig, danach auch remote):

1. Pi mit Monitor/Tastatur/Maus starten — der Assistent (`piwiz`) fragt Land/Sprache/Zeitzone,
   lässt ein Passwort setzen, verbindet WLAN, prüft Updates.
2. **Wichtig: der Assistent aktiviert SSH nicht automatisch** — danach zusätzlich manuell:
   ```
   sudo raspi-config
   ```
   → Interface Options → SSH → Yes → Finish. (Oder GUI: Menü → Einstellungen →
   Raspberry Pi Configuration → Reiter "Interfaces" → SSH aktivieren.)
3. Prüfen, ob's an ist: `sudo systemctl status ssh` (`active (running)` = läuft).
4. Hostname/IP ermitteln (`hostname` bzw. `hostname -I` im Terminal am Pi), dann von einem
   anderen Rechner: `ssh <nutzername>@<hostname>.local` oder mit der IP. Ab hier auch hier
   alles remote.

Erststart, dann per SSH:
```
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

### 2. QLC+ 4.14.4 aus Quellcode bauen

Kein fertiges arm64-Paket öffentlich verfügbar (Stand 2026-07-30, geprüft gegen das offizielle
OBS-Repo) — Bauen aus Quellcode ist der saubere Weg, kein Umweg. Auf dem Pi:

```
sudo apt install -y g++ make cmake git build-essential qtchooser qt5-qmake qtbase5-dev \
  qtbase5-dev-tools qtscript5-dev qtmultimedia5-dev libqt5multimedia5-plugins \
  qttools5-dev-tools qtdeclarative5-dev libqt5svg5-dev qttools5-dev \
  libqt5serialport5-dev libqt5websockets5-dev fakeroot debhelper devscripts \
  pkg-config libxml2-utils libglib2.0-dev libpulse-dev libxkbcommon-dev \
  libasound2-dev libusb-1.0-0-dev libftdi1-dev libudev-dev libmad0-dev \
  libsndfile1-dev libfftw3-dev

git clone https://github.com/mcallegari/qlcplus.git
cd qlcplus
git checkout QLC+_4.14.4

mkdir build && cd build
cmake -DCMAKE_PREFIX_PATH="/usr/lib/aarch64-linux-gnu/cmake/Qt5" ..
make -j4
sudo make install
```
(`-j4` nutzt alle 4 Kerne des Pi 5 — Build dauert trotzdem eine Weile, einplanen.)

Test: `qlcplus --version` sollte `4.14.4` zeigen.

### 3. Projekt-Code auf den Pi bringen

```
sudo mkdir -p /opt/lichtsteuerung
sudo chown pi:pi /opt/lichtsteuerung
git clone <dieses-Repo-URL> /opt/lichtsteuerung
cd /opt/lichtsteuerung/beat-detector
python3 -m venv --system-site-packages venv
sudo apt install -y python3-pyaudio python3-numpy
./venv/bin/pip install python-osc websocket-client
```
`--system-site-packages` + `apt install python3-pyaudio python3-numpy`: vermeidet, `pyaudio`
selbst gegen PortAudio-Header zu kompilieren (auf dem Pi über apt deutlich unkomplizierter,
gleicher Grund wie schon für die Windows-Installation in diesem README).

Mikrofon-Geräteindex ermitteln:
```
./venv/bin/python3 beat_osc.py --list-devices
```

### 4. USB-Stick vorbereiten und einbinden

Stick als **exFAT** formatieren (Windows-lesbar, falls die `.qxw`-Datei auch mal von einem
Windows-Rechner aus bearbeitet werden soll) — auf dem Pi:
```
sudo apt install -y exfatprogs
sudo mkfs.exfat -n LICHTSTICK /dev/sda1   # Gerätename vorher mit lsblk prüfen!
```

Mount-Punkt anlegen, UUID ermitteln, dauerhaft einbinden:
```
sudo mkdir -p /mnt/usbdata
sudo blkid /dev/sda1   # UUID kopieren
sudo nano /etc/fstab
```
Zeile anhängen (UUID ersetzen):
```
UUID=XXXX-XXXX  /mnt/usbdata  exfat  defaults,nofail,uid=pi,gid=pi,umask=000  0  2
```
`nofail`: Boot hängt nicht, falls der Stick mal nicht steckt. `uid=pi,gid=pi`: exFAT hat keine
echten Unix-Rechte, das synthetisiert sie auf den `pi`-Nutzer.

Einhängen und Projektdaten drauf kopieren:
```
sudo mount -a
cp /opt/lichtsteuerung/qlcplus4/2026-07_kulturlichtung_v6.qxw /mnt/usbdata/qlcplus4/2026-07_kulturlichtung_v6.qxw   # Pfad ggf. anlegen
cp /opt/lichtsteuerung/pi-setup/lichtsteuerung.conf.example /mnt/usbdata/lichtsteuerung.conf
nano /mnt/usbdata/lichtsteuerung.conf   # QXW_FILE, AUTO_COLOR, MIC_DEVICE, WEB_PORT eintragen
```

`lichtsteuerung.conf` enthält außerdem alle Takterkennungs-/Intensitäts-Feintuning-Werte
(`SENSITIVITY`, `REFRACTORY_MS`, `INTENSITY_THRESHOLDS_DB`, `BASELINE_SECONDS`,
`INTENSITY_EMA_ALPHA`, `BAND_HOLD_MS` — je mit Kommentar, was sie tun) mit denselben
Standardwerten wie `beat_osc.py --help`. Anpassbar ohne Pi-Login, direkt auf dem USB-Stick.

### 5. Root-Dateisystem schreibschützen (overlayroot)

**Nicht** die `raspi-config`-eigene "Overlay File System"-Option nutzen — die macht auf
Bookworm pauschal *alle* eingehängten Dateisysteme read-only, würde also auch den USB-Stick
sperren (bekannter Bug, siehe `CLAUDE.md`-Recherche-Notiz). Stattdessen das `overlayroot`-Paket,
das gezielt nur `/` schützt:

```
sudo apt install -y overlayroot
sudo nano /etc/overlayroot.conf
```
Zeile `overlayroot=""` suchen und ersetzen durch:
```
overlayroot="tmpfs:recurse=0"
```
`recurse=0` ist der entscheidende Teil — ohne den würde auch hier wieder der USB-Stick mit
schreibgeschützt.

**Vor dem Reboot:** alles unter Schritt 2–4 muss fertig sein (Overlay bedeutet: jede Änderung
an `/` nach dem nächsten Neustart ist wieder weg, bis explizit deaktiviert). Zum Deaktivieren
(z. B. für ein späteres Update): `sudo overlayroot-chroot`, Änderungen machen, dann normal
rebooten.

```
sudo reboot
```

### 6. Autostart einrichten (systemd)

```
sudo cp /opt/lichtsteuerung/pi-setup/qlcplus.service /etc/systemd/system/
sudo cp /opt/lichtsteuerung/pi-setup/beat-osc.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qlcplus.service
sudo systemctl enable --now beat-osc.service
```

Status/Logs prüfen:
```
systemctl status qlcplus.service beat-osc.service
journalctl -u qlcplus.service -u beat-osc.service -f
```

**Reihenfolge/Robustheit:** `beat-osc.service` startet nach `qlcplus.service`, braucht es aber
nicht zwingend fertig verbunden zu haben — `beat_osc.py`s WebSocket-Client versucht jede
Sekunde neu zu verbinden, bis QLC+s Web Access wirklich bereit ist (siehe `CLAUDE.md`).

### 7. Test

Pi neu starten (echter Kaltstart, nicht nur Service-Neustart) und beobachten:
- `systemctl status qlcplus.service beat-osc.service` → beide `active (running)`.
- Tablet/Laptop im selben Netz, Browser auf `http://<Pi-IP>:9999` → Virtual Console sichtbar.
- Konsole/Log von `beat-osc.service` zeigt `[ws] connected to ...` und (falls `AUTO_COLOR`
  gesetzt) `[state] Auto <farbe>: ON` kurz nach dem Start.
- Musik/Rhythmus vorspielen → Lautstärke ändern → passender Ebenen-Button sollte sich in der
  Web-UI als aktiv zeigen.

### Projekt/Konfiguration später ändern

Kein Pi-Login nötig für alltägliche Änderungen: USB-Stick an einem anderen Rechner
`lichtsteuerung.conf` bearbeiten (andere `.qxw`-Datei, andere `AUTO_COLOR`) oder die
`.qxw`-Datei selbst ersetzen, zurück in den Pi stecken, Pi neu starten (oder
`sudo systemctl restart qlcplus.service beat-osc.service`, falls er schon läuft).

### Bekannte offene Punkte

- Dieser komplette Pi-Abschnitt ist **nicht auf echter Pi-Hardware verifiziert** (Stand
  2026-07-30) — Befehle/Paketnamen gegen offizielle QLC+-Wiki-Doku und aktuelle Web-Recherche
  geprüft, aber nicht selbst durchgespielt. Beim ersten echten Durchlauf Schritt für Schritt
  bestätigen, nicht blind vertrauen (gleiche Regel wie überall sonst in diesem Projekt).
- `QT_QPA_PLATFORM=offscreen` für den Headless-Betrieb (kein Display) ist Standard-Qt-Praxis,
  aber nicht gegen dieses spezifische QLC+-Build getestet — falls QLC+ trotzdem einen Display-
  Server verlangt, ersatzweise `xvfb-run` oder ein minimaler Autologin-X11-Session als
  Workaround (dann aber echter Hack, nicht die saubere Lösung — erst berichten, dann
  entscheiden).
- Auto-Layer-Feature selbst ist laut `CLAUDE.md` noch nicht über einen ganzen Abend/mit echter
  Musik durchgetestet.
