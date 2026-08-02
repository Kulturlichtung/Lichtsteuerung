# Kulturlichtung – Lichtsteuerung

Setup für eine Mehr-Spot-RGBW/RGBWW-Lichtanlage mit QLC+ (Q Light Controller+), inklusive
Sound-to-Light mit automatischer Takterkennung übers Mikrofon (kein manuelles Tempo-Tippen) und
optionaler Intensitäts-gesteuerter Ebenen-Automatik. Zielsystem ist ein unbeaufsichtigter
Raspberry Pi, bedient übers Tablet (QLC+ Web Access) über einen vom Pi selbst aufgespannten
WLAN-Hotspot (kein WLAN/Router am Aufführungsort nötig) — siehe Pi-Guide weiter unten.

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

## DMX-Adressierung (Stand `v5.qxw`, Produktionsdatei)

Alle Geräte hängen an **einem** Universum ("Universe 1", Ausgang "DMX USB" — reales DMX-USB-PRO-
Interface). Adressen unten sind die 1-indexierten DMX-Kanalnummern (wie in der QLC+-UI angezeigt,
= `<Address>` in der `.qxw` + 1):

| Gerät | Start-Adresse | Kanäle | Kanalbelegung |
|---|---|---|---|
| Fun-Generation LED Pot 12x1W QCL RGB WW #1 | 1 | 8 | 1=Master, 2=R, 3=G, 4=B, 5=W, 6–8 unbenutzt |
| Fun-Generation LED Pot 12x1W QCL RGB WW #2 | 9 | 8 | 9=Master, 10=R, 11=G, 12=B, 13=W, 14–16 unbenutzt |
| Fun-Generation LED Pot 12x1W QCL RGB WW #3 | 17 | 8 | 17=Master, 18=R, 19=G, 20=B, 21=W, 22–24 unbenutzt |
| Fun-Generation LED Pot 12x1W QCL RGB WW #4 | 25 | 8 | 25=Master, 26=R, 27=G, 28=B, 29=W, 30–32 unbenutzt |
| Eurolite LED Mini Strobe Cluster SMD 48 | 33 | 3 | genaue Kanalbelegung nicht in diesem Dokument verifiziert (Standard-Fixture-Profil) |

Fixture-Reihenfolge/Adressen sind fortlaufend ohne Lücken vergeben (Pot #1–4 dann Strobe direkt
danach) — beim Hinzufügen eines neuen Geräts entsprechend ab Adresse 36 weitermachen, um
Überlappungen zu vermeiden.

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

**Bug gefunden und gefixt 2026-08-02: Ebenen-Button blieb nach Auto-Aktivierung manchmal
inaktiv** (reproduziert nach Boot und nach Watchdog-Neustart). Ursache: `run_auto_layer_step`
lief jeden Audio-Loop-Tick (~23ms) neu, solange der bestätigte Zustand noch nicht mit dem
gewünschten übereinstimmte — die Web-Access-Bestätigung braucht aber länger als einen Tick,
wodurch mehrere Presses rausgingen, bevor die erste Bestätigung zurückkam. Die Ebenen-Buttons
sind `Action=Toggle` — jeder zusätzliche Press schaltet wieder um, bei gerader Anzahl Presses
landet der Button auf "aus" statt "an", reine Zufallssache je nach Timing. Fix: Presse pro Farbe
werden jetzt für 1s "gemerkt" (`last_layer_command`) und nicht erneut gesendet, solange auf
Bestätigung des exakt gleichen Ziels gewartet wird — reagiert weiterhin sofort, wenn sich das
gewünschte Ziel ändert oder ein Mensch manuell einen anderen Button drückt.

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
| WLAN-Hotspot-Profil (NetworkManager) | Pi-Root (`/etc/NetworkManager/...`), aber SSID/Passwort kommen bei jedem Boot aus `lichtsteuerung.conf` | Systemweite Netzwerkeinstellung, trotzdem übers Config-File änderbar wie alles andere |

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
sudo apt install -y vim
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

Test: `QT_QPA_PLATFORM=offscreen qlcplus --version` sollte `4.14.4` zeigen. `QT_QPA_PLATFORM=offscreen`
nötig, da ohne Display/X-Server sonst `qt.qpa.xcb: could not connect to display` — bestätigt auf
echter Pi-5-Hardware 2026-07-31 (siehe unten, "Bekannte offene Punkte").

### 3. Projekt-Code auf den Pi bringen

```
sudo mkdir -p /opt/lichtsteuerung
sudo chown "$(whoami):$(whoami)" /opt/lichtsteuerung
git clone https://github.com/Kulturlichtung/Lichtsteuerung.git /opt/lichtsteuerung
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
Davor jede Menge `ALSA lib ...`/`jack server is not running`-Zeilen sind normal (PortAudio testet
beim Init alle in der ALSA-Konfig gelisteten virtuellen PCM-Devices durch, die meisten existieren
auf einem USB-Mikro schlicht nicht; kein JACK installiert/nötig) — kein Fehler, ignorieren.
Relevant ist nur die letzte Zeile, z. B. `[0] USB AUDIO DEVICE: ... (in: 2, ...)` → Index `0` ist
der `MIC_DEVICE`-Wert für `lichtsteuerung.conf`.

### 4. USB-Stick vorbereiten und einbinden

Stick als **exFAT** formatieren (Windows-lesbar, falls die `.qxw`-Datei auch mal von einem
Windows-Rechner aus bearbeitet werden soll) — auf dem Pi. `DEV` einmal setzen (Gerätename vorher
mit `lsblk` prüfen!), danach übernehmen alle folgenden Befehle den Wert automatisch:

**Achtung:** Raspberry Pi OS hängt Sticks mit vorhandenem Dateisystem beim Einstecken automatisch
ein (Desktop-Umgebung), z. B. unter `/media/<nutzername>/<label>` — `lsblk` zeigt das unter
`MOUNTPOINTS`. Vor dem Formatieren prüfen, ob wichtige Daten drauf liegen
(`ls /media/<nutzername>/<label>`) und aushängen, sonst blockiert `mkfs`:
```
sudo apt install -y exfatprogs
DEV=/dev/sda1   # Gerätename vorher mit lsblk prüfen!
sudo umount "$DEV"   # falls automatisch gemountet -- siehe Achtung oben
sudo mkfs.exfat -n LICHTSTICK "$DEV"
```
Ist der Stick schon leer/passend exFAT-formatiert, kann dieser Schritt auch übersprungen werden
— dann direkt weiter mit dem Mount-Punkt unten (Stick vorher trotzdem aushängen, `mount -a`
später hängt ihn sauber unter `/mnt/usbdata` wieder ein).

Mount-Punkt anlegen, UUID ermitteln und automatisch (samt aktuellem Nutzernamen) in `/etc/fstab`
eintragen — kein manuelles Abtippen von UUID/Nutzername nötig:
```
sudo mkdir -p /mnt/usbdata
UUID=$(sudo blkid -s UUID -o value "$DEV")
echo "UUID=$UUID  /mnt/usbdata  exfat  defaults,nofail,uid=$(whoami),gid=$(whoami),umask=000  0  2" | sudo tee -a /etc/fstab
```
`nofail`: Boot hängt nicht, falls der Stick mal nicht steckt. `uid=$(whoami),gid=$(whoami)`:
exFAT hat keine echten Unix-Rechte, das synthetisiert sie auf den gewählten Nutzer.

Einhängen und Projektdaten drauf kopieren. `daemon-reload` nötig, da systemd `/etc/fstab` beim
Booten einliest und cacht — ohne den Reload sieht `mount -a` nur den alten Stand, egal wie
frisch die Zeile eben angehängt wurde:
```
sudo systemctl daemon-reload
sudo mount -a
mkdir -p /mnt/usbdata/qlcplus4
cp /opt/lichtsteuerung/qlcplus4/2026-07_kulturlichtung_v6.qxw /mnt/usbdata/qlcplus4/2026-07_kulturlichtung_v6.qxw
cp /opt/lichtsteuerung/pi-setup/lichtsteuerung.conf.example /mnt/usbdata/lichtsteuerung.conf
vim /mnt/usbdata/lichtsteuerung.conf   # QXW_FILE, AUTO_COLOR, MIC_DEVICE, WEB_PORT,
                                        # HOTSPOT_SSID, HOTSPOT_PASSWORD eintragen
```

`lichtsteuerung.conf` enthält außerdem alle Takterkennungs-/Intensitäts-Feintuning-Werte
(`SENSITIVITY`, `REFRACTORY_MS`, `INTENSITY_THRESHOLDS_DB`, `BASELINE_SECONDS`,
`INTENSITY_EMA_ALPHA`, `BAND_HOLD_MS` — je mit Kommentar, was sie tun) mit denselben
Standardwerten wie `beat_osc.py --help`. Anpassbar ohne Pi-Login, direkt auf dem USB-Stick.

### 5. WLAN-Hotspot einrichten

Kein WLAN/Router am Aufführungsort — der Pi spannt sein eigenes WLAN auf, das Tablet verbindet
sich direkt damit für QLC+ Web Access. Nutzt NetworkManager (Bookworm-Standard, kein
Zusatzpaket nötig). SSID/Passwort kommen aus `lichtsteuerung.conf` auf dem USB-Stick (siehe
Schritt 4) — änderbar wie jede andere Einstellung, ohne den Pi anzufassen.

**Wichtig:** Hotspot- und WLAN-Client-Betrieb teilen sich dieselbe Antenne (`wlan0`) — beides
gleichzeitig geht nicht. Für die Ersteinrichtung oben (SSH, `apt`, Build) deshalb
**Netzwerkkabel** nutzen, nicht die optionalen WLAN-Zugangsdaten aus Schritt 1 — sonst
blockiert später der Hotspot den Client-Modus oder umgekehrt.

`pi-setup/run-hotspot.sh` legt beim ersten Lauf die NetworkManager-Verbindung
`Lichtsteuerung-Hotspot` an (bzw. aktualisiert sie, falls sich SSID/Passwort geändert haben)
und aktiviert sie. Als `hotspot.service` in Schritt 6 zusammen mit den anderen beiden Services
eingerichtet — läuft ab dann bei jedem Boot automatisch, kein manueller Schritt mehr nötig.

### 6. Autostart einrichten (systemd)

**Vor** dem Schreibschutz (nächster Schritt), nicht danach — Unit-Dateien landen unter `/etc`,
und alles, was nach dem Overlay-aktivierenden Reboot dort neu geschrieben wird, ist beim
nächsten Neustart wieder weg (siehe Warnung unten). Erst hier rein, dann erst schützen.

`<nutzername>`-Platzhalter in den beiden User-gebundenen Units per `sed` durch den eigenen
(aktuell eingeloggten) Nutzernamen ersetzen, dabei direkt nach `/etc/systemd/system/` kopieren.
`hotspot.service` braucht das nicht (läuft als root, für die Netzwerk-Änderungen nötig):
```
sudo sed "s/<nutzername>/$(whoami)/g" /opt/lichtsteuerung/pi-setup/qlcplus.service | sudo tee /etc/systemd/system/qlcplus.service >/dev/null
sudo sed "s/<nutzername>/$(whoami)/g" /opt/lichtsteuerung/pi-setup/beat-osc.service | sudo tee /etc/systemd/system/beat-osc.service >/dev/null
sudo cp /opt/lichtsteuerung/pi-setup/hotspot.service /etc/systemd/system/hotspot.service
sudo systemctl daemon-reload
sudo systemctl enable --now hotspot.service
sudo systemctl enable --now qlcplus.service
sudo systemctl enable --now beat-osc.service
```

Status/Logs prüfen:
```
systemctl status hotspot.service qlcplus.service beat-osc.service
journalctl -u hotspot.service -u qlcplus.service -u beat-osc.service -f
```

**Reihenfolge/Robustheit:** `beat-osc.service` startet nach `qlcplus.service`, braucht es aber
nicht zwingend fertig verbunden zu haben — `beat_osc.py`s WebSocket-Client versucht jede
Sekunde neu zu verbinden, bis QLC+s Web Access wirklich bereit ist (siehe `CLAUDE.md`).
`hotspot.service` läuft vor `qlcplus.service` (`Before=` in der Unit), damit das WLAN beim
Verbinden vom Tablet aus schon steht.

### 7. Root-Dateisystem schreibschützen (overlayroot)

**Nicht** die `raspi-config`-eigene "Overlay File System"-Option nutzen — die macht auf
Bookworm pauschal *alle* eingehängten Dateisysteme read-only, würde also auch den USB-Stick
sperren (bekannter Bug, siehe `CLAUDE.md`-Recherche-Notiz). Stattdessen das `overlayroot`-Paket,
das gezielt nur `/` schützt:

```
sudo apt install -y overlayroot
sudo vim /etc/overlayroot.conf
```
Zeile `overlayroot=""` suchen und ersetzen durch:
```
overlayroot="tmpfs:recurse=0"
```
`recurse=0` ist der entscheidende Teil — ohne den würde auch hier wieder der USB-Stick mit
schreibgeschützt.

**Vor dem Reboot:** alles unter Schritt 2–6 muss fertig sein — insbesondere die systemd-Units
aus Schritt 6 (Overlay bedeutet: jede Änderung an `/` nach dem nächsten Neustart ist wieder weg,
bis explizit deaktiviert).

```
sudo reboot
```

**Schutz später wieder aufheben (Updates, Änderungen):** zwei Wege, je nach Umfang.

*Kurze/einzelne Änderung (z. B. `apt upgrade`), Overlay bleibt sonst aktiv:*
```
sudo overlayroot-chroot
```
Öffnet Chroot ins echte (nicht überlagerte) Root-Dateisystem. Änderungen dort (z. B. `apt
update && apt upgrade`) landen direkt auf der Platte, dauerhaft — kein Reboot, kein Deaktivieren
nötig. `exit` verlässt den Chroot, Pi läuft danach normal mit Overlay weiter aktiv.

*Länger/mehrere Änderungen, Overlay komplett zeitweise abschalten:*
```
sudo vim /etc/overlayroot.conf
```
`overlayroot="tmpfs:recurse=0"` zurück auf `overlayroot=""` setzen, dann:
```
sudo reboot
```
Nach dem Neustart ist `/` wieder normal beschreibbar (kein Overlay), Änderungen direkt
persistent. Danach zum erneuten Schützen wieder `overlayroot="tmpfs:recurse=0"` eintragen und
rebooten (Schritt oben wiederholen).

*Nur für den nächsten einen Boot deaktivieren, ohne Config anzufassen:* Kernel-Cmdline-Parameter
`overlayroot=disabled` anhängen (z. B. via `raspi-config` → Advanced → Bootloader/Cmdline, oder
direkt in `/boot/firmware/cmdline.txt`), einmal rebooten, Parameter danach wieder entfernen.

### 8. Test

Pi neu starten (echter Kaltstart, nicht nur Service-Neustart) und beobachten:
- `systemctl status hotspot.service qlcplus.service beat-osc.service` → alle drei `active (running)`.
- WLAN-Liste auf Tablet/Laptop zeigt die konfigurierte `HOTSPOT_SSID`, verbinden mit
  `HOTSPOT_PASSWORD` klappt.
- Nach Verbinden mit dem Hotspot: Browser auf `http://<Pi-IP>:9999` → Virtual Console sichtbar
  (Pi-IP z. B. `192.168.4.1`, NetworkManager-Standard-Gateway im Shared-Modus — genauer Wert
  noch nicht auf echter Hardware bestätigt, siehe unten).
- Konsole/Log von `beat-osc.service` zeigt `[ws] connected to ...` und (falls `AUTO_COLOR`
  gesetzt) `[state] Auto <farbe>: ON` kurz nach dem Start.
- Musik/Rhythmus vorspielen → Lautstärke ändern → passender Ebenen-Button sollte sich in der
  Web-UI als aktiv zeigen.

### Projekt/Konfiguration später ändern

Kein Pi-Login nötig für alltägliche Änderungen: USB-Stick an einem anderen Rechner
`lichtsteuerung.conf` bearbeiten (andere `.qxw`-Datei, andere `AUTO_COLOR`) oder die
`.qxw`-Datei selbst ersetzen, zurück in den Pi stecken, Pi neu starten (oder
`sudo systemctl restart hotspot.service qlcplus.service beat-osc.service`, falls er schon
läuft — z. B. nach Ändern von `HOTSPOT_SSID`/`HOTSPOT_PASSWORD`).

### Code-Updates (git pull) auf dem Pi einspielen

`/opt/lichtsteuerung` liegt auf dem overlay-geschützten Root (Schritt 7) — ein einfaches
`git pull` dort landet nur im flüchtigen tmpfs-Overlay und ist nach dem nächsten Reboot wieder
weg. Über `overlayroot-chroot` einspielen, das schreibt sofort aufs echte Root-Dateisystem:

```
sudo overlayroot-chroot
cd /opt/lichtsteuerung
git pull
exit
```

**Der `exit` endet praktisch immer mit `mount: /media/root-ro: mount point is busy` —
erwartet, kein Fehlerzustand zum Beheben.** Bestätigt 2026-08-02: kein hängender Prozess
dahinter (`fuser -vm /media/root-ro` leer, kein `/proc`/`/sys`/`/dev` mehr drunter gemountet,
manueller `mount -o remount,ro`-Retry scheitert ebenso). Grund ist strukturell: `/` läuft live
als Overlay mit `lowerdir=/media/root-ro` — jeder Prozess mit einer noch offenen, nicht ins
tmpfs hochkopierten Datei über `/` hält intern eine Referenz auf die echte Datei im ext4
darunter, was `fuser` (prüft nur den Mountpoint direkt) nicht anzeigt, der Kernel beim Remount
aber trotzdem als busy zählt. Mit laufendem System praktisch nie sauber vermeidbar — nicht
weiter nachjagen.

**Danach immer rebooten**, nicht nur Services neu starten — das Overlay ist nach jedem
Neustart ohnehin komplett frisch scharf, unabhängig vom Exit-Status davor, und ist der einzige
Weg, den Schreibschutz nach dem `exit`-Fehler zuverlässig wieder zu aktivieren:

```
sudo reboot
```

Falls overlayroot auf diesem Pi (noch) nicht aktiv ist, reicht `git pull` + Service-Neustart
direkt, ohne `overlayroot-chroot`/Reboot.

**Ändert sich dabei eine `.service`-Datei** (z. B. `pi-setup/beat-osc.service`), reicht der
`git pull` allein nicht — die *aktiv geladene* Kopie liegt unter `/etc/systemd/system/`, separat
vom Repo-Klon, und wurde beim Ersteinrichten einmalig dorthin kopiert (siehe Schritt 6). `git
pull` aktualisiert nur die Repo-Datei; ohne erneutes Kopieren bleibt die alte Unit-Version aktiv
(genau das ist einem echten Watchdog-Update am 2026-08-02 passiert — stundenlang unbemerkt, bis
`systemctl show ... | grep -i watchdog` `WatchdogUSec=0` statt des erwarteten Werts zeigte).
`/etc` liegt genauso unterm overlay-geschützten Root wie `/opt` — dieselbe
`overlayroot-chroot`+Reboot-Pflicht wie oben gilt auch hier:

```
sudo overlayroot-chroot
sed "s/<nutzername>/<echter-username>/g" /opt/lichtsteuerung/pi-setup/beat-osc.service > /etc/systemd/system/beat-osc.service
exit
```
(`mount point is busy` wieder erwartet, siehe oben)
```
sudo reboot
```

**Falle dabei: `$(whoami)` *innerhalb* der `overlayroot-chroot`-Sitzung liefert `root`**, nicht
den echten Servicenutzer (Prompt wechselt sichtbar zu `root@.../#`) — den echten Nutzernamen von
ausserhalb der Chroot-Sitzung einsetzen (z. B. der Name, der im normalen Shell-Prompt vor dem
`overlayroot-chroot`-Aufruf steht), nicht `$(whoami)` im Chroot selbst verwenden.

Danach verifizieren, dass die neue Unit-Version wirklich aktiv ist:
```
systemctl show beat-osc.service | grep -iE "type|watchdog"
```

### Bekannte offene Punkte

- Pi-Grundbetrieb (QLC+-Build, Projekt-Code, USB-Stick, systemd-Autostart, Beat-Detector) läuft
  inzwischen produktiv auf echter Pi-5-Hardware und wurde mehrfach live debuggt (Mikrofon-
  Geräteliste, `journalctl`-Pufferungs-Fix, Capture-Hang-Fix, WebSocket-Freeze-Fix — Stand
  2026-08-02, Details in `CLAUDE.md`). `overlayroot` (Schritt 7) läuft auf diesem Pi bestätigt
  aktiv (`mount` zeigt den Overlay-Root live, 2026-08-02). Weiterhin unbestätigt: WLAN-Hotspot
  (siehe eigener Punkt unten).
- Auto-Layer-Feature ist noch nicht über einen ganzen Abend/mit echter Musik durchgetestet.
  Drei zugehörige Bugs wurden zwischenzeitlich gefunden, keiner noch über eine längere Session
  bestätigt: ein WebSocket-Send-Hang (Auto-Button-Klick fror die komplette Audio-Erkennung ein,
  `beat_osc.py` commit `abc53f5`, 2026-08-02, gefixt) und ein Mikrofon-Capture-Hang (Prozess
  bleibt in einem ALSA-Read stecken, kein Crash, kein Log) — **trotz** des Stereo/S16-Fixes vom
  31.07. am 2026-08-02 live erneut reproduziert (Syscall-Diagnose bestätigt: Hauptthread hängt
  in `ppoll`, exakt gleiches Bild wie beim ersten Fund; `/proc/asound/card2/stream0` zeigte dabei
  `Status: Running` — ALSA/Hardware liefert nachweislich weiter, Bug sitzt sicher in
  PyAudio/PortAudio selbst). Ursache weiterhin ungeklärt, wird separat weiterverfolgt (siehe
  `CLAUDE.md`). Als Selbstheilung dagegen: `beat-osc.service` hat einen systemd-Watchdog
  (`Type=notify`, `WatchdogSec=15`, commit `d024d47`, 2026-08-02) — Skript schickt nach jedem
  Mikrofon-Read ein Herzschlag-Signal; bleibt der Read hängen, killt/restartet systemd den
  Dienst automatisch nach spätestens 15s. Beim ersten realen Hänger griff er nicht, weil die neue
  Unit-Datei nie nach `/etc/systemd/system/` re-installiert wurde (`git pull` aktualisiert nur
  die Repo-Kopie, siehe Update-Sektion oben) — nach korrektem Redeploy **live bestätigt
  funktionierend** (2026-08-02, `journalctl` zeigt zwei saubere Watchdog-Neustarts kurz
  hintereinander). Heilt aber nur das Symptom (kurze Beat-Lücke statt Totalausfall), nicht die
  eigentliche Ursache — und die tritt gerade auffällig häufig auf (alle ~30-100s statt der
  ursprünglich beschriebenen seltenen Fälle), macht aber auch die Ursachensuche leichter (schnell
  reproduzierbar statt stundenlangem Warten). Neu zur Bisection: `--audio-backend alsaaudio`
  (statt Standard `pyaudio`) umgeht PortAudio komplett, spricht ALSA direkt über `pyalsaaudio`
  an (`pip install pyalsaaudio`, braucht `libasound2-dev`) — Gerät über `--alsa-device hw:2,0`
  (ALSA-Kartennummer aus `arecord -l`, **nicht** der `--device`-Index aus `--list-devices`).
  Hängt dieser Pfad über dieselbe Zeitspanne nicht, sitzt der Bug sicher in PortAudio selbst,
  echter Fix (Backend dauerhaft wechseln) möglich. Noch nicht getestet.
- **WLAN-Hotspot (`hotspot.service`/`run-hotspot.sh`) ist neu und noch nicht auf echter
  Pi-Hardware getestet** — `nmcli`-Befehle gegen NetworkManager-Doku geprüft, aber nicht selbst
  durchgespielt (gleiche "erst live bestätigen"-Regel wie überall sonst in diesem Projekt). Beim
  ersten echten Durchlauf insbesondere prüfen: ob Pi 5 + eingebautes WLAN-Modul den `ap`-Modus
  tatsächlich unterstützt, ob `ipv4.method shared` die erwartete Pi-IP (üblich `192.168.4.1`)
  vergibt, und ob `Before=qlcplus.service` reicht oder das Tablet manchmal vor fertigem
  Hotspot-Start verbinden will.
