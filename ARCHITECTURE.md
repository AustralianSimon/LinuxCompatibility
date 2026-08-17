# LinuxReadyAmI — Architecture

> Working name. A Windows desktop app that inventories a PC and tells the user, concretely,
> what it would cost them to switch to Linux: which apps have native/Flatpak equivalents or

> a Linux comparable alternative instead of Windows native,
> which games run under Proton, and which hardware will fight them.

**Status:** design spec, pre-implementation.
**Audience:** Claude Code (implementation), maintainers.

\---

## 1\. Purpose \& Scope

### Problem

People considering a Linux switch have no cheap way to answer "will my stuff work?" They get
told "just try it" or handed a wiki. The information exists (ProtonDB, WineHQ AppDB, Flathub,
distro repos) but nobody joins it to *their actual machine*.

### What this does

1. Inventories installed desktop apps, game libraries, and hardware on a Windows PC.
2. Matches each item against a bundled compatibility database.
3. Classifies every item: works natively / works via a compatibility layer / needs a
replacement / hard blocker.
4. Produces a readiness score, a prioritised blocker list, a distro recommendation, and an
exportable self-contained HTML report.

### Non-goals (explicit — do not build these)

* **Does not perform the migration.** No partitioning, no bootloader work, no ISO writing.
* **Does not modify the system.** Read-only. No registry writes, no service changes.
* **No telemetry, no account, no network calls during a scan.** See §11.
* Not a Wine/Proton configuration tool.
* Not a Windows-side backup tool (data migration is a possible Phase 3, see §14).

### Design principles

* **Read-only and non-admin by default.** A standard user account must get a useful scan.
Admin unlocks a few extra checks (§6.3), never required.
* **Offline-first.** A scan works on a machine with the network cable pulled.
* **Honest uncertainty.** Every verdict carries a confidence level. "I don't know about this
app" is a valid, visible outcome — never guess silently.
* **The user owns the output.** One HTML file, no external requests, shareable on a forum.

\---

## 2\. High-Level Architecture

Two separately-versioned deliverables:

```
┌─────────────────────────────────────────┐   ┌──────────────────────────────────┐
│  A. linuxready-app  (Windows desktop)   │   │  B. linuxready-harvester (Docker)│
│                                         │   │                                  │
│  PySide6 GUI                            │   │  Scheduled job (CI cron)         │
│    ↕                                    │   │    ├── protondb ingest           │
│  Scan orchestrator (QThread)            │   │    ├── winehq appdb ingest       │
│    ├── collectors/  (apps, games, hw)   │   │    ├── flathub / repology ingest │
│    ├── matcher/     (identity resolve)  │   │    ├── pci.ids + kernel driver   │
│    ├── verdict/     (rules + scoring)   │   │    └── curated overrides (YAML)  │
│    └── report/      (Jinja2 → HTML)     │   │            ↓                     │
│           ↑                             │   │      build + sign                │
│  compat.db (SQLite, read-only) ◄────────┼───┼──  compat-YYYY.MM.DD.db          │
└─────────────────────────────────────────┘   └──────────────────────────────────┘
```

The app never talks to ProtonDB or Flathub. It only ever reads a local SQLite file. The
harvester does all the crawling, on a schedule, in CI. This keeps scan latency at \~seconds,
keeps the app immune to upstream API changes and rate limits, and keeps the privacy story
trivially true.

**DB delivery:** a `compat.db` is bundled in the installer, and the app offers an *opt-in*,
explicit "Check for database update" button that fetches a newer `.db` + checksum from a
static host (GitHub Releases / S3). That button is the only outbound request the app ever
makes, and it is never automatic on first run.

\---

## 3\. Repository Layout

Monorepo, two packages:

```
linuxready/
├── app/
│   ├── src/linuxready/
│   │   ├── \_\_main\_\_.py
│   │   ├── config.py             # paths, feature flags, DB location
│   │   ├── collectors/
│   │   │   ├── base.py           # Collector ABC
│   │   │   ├── registry\_apps.py  # HKLM/HKCU Uninstall keys
│   │   │   ├── store\_apps.py     # MSIX / Appx
│   │   │   ├── portable\_apps.py  # heuristic .exe scan (opt-in)
│   │   │   ├── steam.py
│   │   │   ├── epic.py
│   │   │   ├── gog.py
│   │   │   ├── xbox.py
│   │   │   ├── hardware.py       # CIM/WMI via PS shim
│   │   │   └── firmware.py       # Secure Boot, BitLocker, storage mode
│   │   ├── ps/                   # PowerShell shims, JSON out
│   │   │   ├── hardware.ps1
│   │   │   └── firmware.ps1
│   │   ├── matcher/
│   │   │   ├── normalize.py      # name canonicalisation
│   │   │   ├── resolver.py       # exact → alias → fuzzy cascade
│   │   │   └── confidence.py
│   │   ├── verdict/
│   │   │   ├── rules.py          # verdict assignment
│   │   │   ├── score.py          # readiness score
│   │   │   └── distro.py         # distro recommendation
│   │   ├── report/
│   │   │   ├── render.py         # Jinja2 → single-file HTML
│   │   │   └── templates/
│   │   ├── db/
│   │   │   ├── schema.sql
│   │   │   ├── access.py         # read-only connection, queries
│   │   │   └── update.py         # opt-in DB refresh + checksum verify
│   │   ├── models.py             # dataclasses / pydantic
│   │   └── ui/
│   │       ├── main\_window.py
│   │       ├── scan\_worker.py    # QThread wrapper
│   │       ├── views/            # welcome, scanning, results, detail, settings
│   │       └── resources/
│   ├── tests/
│   │   └── fixtures/             # captured registry dumps, .acf, CIM JSON
│   └── pyproject.toml
├── harvester/
│   ├── src/harvester/
│   │   ├── sources/              # one module per upstream
│   │   ├── build\_db.py
│   │   └── validate.py           # sanity gates before publish
│   ├── data/
│   │   └── overrides/            # hand-curated YAML — the crown jewels
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── pyproject.toml
├── shared/
│   └── schema/                   # scan\_result.schema.json, compat db schema docs
└── docs/
```

\---

## 4\. The App: Component Detail

### 4.1 Collector interface

Every collector is independent and failure-isolated. One collector throwing must never abort
a scan — it reports a degraded status and the UI shows what was skipped.

```python
class Collector(ABC):
    id: str                       # "steam", "registry\_apps"
    display\_name: str
    requires\_admin: bool = False

    @abstractmethod
    def available(self) -> bool: ...          # is this relevant on this machine?

    @abstractmethod
    def collect(self, ctx: ScanContext) -> CollectorResult: ...
        # returns items + warnings + status(ok|partial|failed|skipped)
```

Collectors emit **raw observations**, not verdicts. They do no matching. This separation
matters: it makes collectors testable against static fixtures and lets the matcher be
re-run against a saved scan without re-scanning the machine.

### 4.2 Scan orchestration

* Runs on a `QThread` worker; the GUI thread never blocks.
* Collectors run concurrently in a thread pool (they're I/O bound on registry/disk/WMI).
* Per-collector timeout (default 30s, hardware 60s). Timeout → `status=partial`.
* Progress signalled per collector, not per item, so the progress bar doesn't lie.
* Full scan target: **under 20 seconds** on a typical machine.

### 4.3 Matcher

The hardest and most valuable part. Turning `"Adobe Photoshop 2024 (64-bit)"` from a registry
`DisplayName` into a canonical app identity.

Resolution cascade, first hit wins:

|Tier|Method|Confidence|
|-|-|-|
|1|**Exact key**: Steam AppID, Epic catalog ID, GOG product ID, MSIX PFN, PCI `VEN/DEV`|`exact`|
|2|**Override table**: curated `(name\_pattern, publisher) → app\_id` from `overrides/`|`exact`|
|3|**Normalised name + publisher** match on DB alias table|`high`|
|4|**Normalised name** alone, unique match|`medium`|
|5|**Fuzzy** (rapidfuzz token\_set\_ratio ≥ 88) against alias table|`low`|
|6|No match|`unknown`|

Games via Steam/Epic/GOG almost always land in Tier 1 — the launcher manifests carry stable
IDs. Desktop apps are the messy case, which is why the curated override layer exists.

`normalize.py` strips: trailing/leading version numbers, `(x64)`, `(64-bit)`, year suffixes,
™/®/©, `Microsoft ` vendor prefixes where unambiguous, and collapses whitespace/punctuation.
Keep the original string on the item for display and for the "report a bad match" flow.

**Never present a Tier 5 match as fact.** The UI must show low-confidence matches with a
visible "is this right?" affordance.

### 4.4 Verdict engine

Each matched item gets exactly one verdict:

|Verdict|Meaning|
|-|-|
|`native`|First-party Linux build exists (Steam native, .deb, official Flatpak)|
|`packaged`|Available via Flatpak/Snap/distro repo, not necessarily first-party|
|`layer\_excellent`|Runs under Proton/Wine essentially perfectly (ProtonDB Platinum/Gold, Wine Platinum)|
|`layer\_workable`|Runs with known tweaks (Silver, or Gold-with-caveats) — caveats surfaced|
|`layer\_poor`|Runs badly or partially (Bronze)|
|`blocked`|Known not to work. Anticheat-blocked games, hardware-locked software|
|`replace`|No path, but a credible Linux alternative exists (→ suggestion list)|
|`web`|A web version covers the use case (Office 365 web, Figma)|
|`unknown`|Not in DB. Counted separately, never folded into "fine"|

Verdicts derive from DB facts plus rules in `rules.py`. Rules must be **data-driven and
inspectable** — the report should be able to explain *why* an item got its verdict.

### 4.5 Blockers vs friction

A blocker isn't the same as an inconvenience, and conflating them is how these tools lose
trust. Classify separately:

* **Hard blockers** — the migration fails or the user loses something they can't replace.
Kernel-level anticheat games (Valorant, most Battlefield/CoD MP), Adobe CC as a
professional dependency, proprietary vertical software, a wifi chipset with no in-tree
driver, storage controller in RAID/IRST mode.
* **Friction** — solvable with effort. A Bronze-rated game, a niche utility needing a Flatpak
alternative, an NVIDIA GPU needing proprietary drivers.

The results screen leads with hard blockers.

### 4.6 Readiness score

A single 0–100 headline, but **always shown alongside the blocker count**, never alone.

```
base = weighted\_pass\_rate(apps, games, hardware)     # weights: hw 0.4, apps 0.35, games 0.25
score = base × blocker\_penalty
blocker\_penalty = 1.0 with no hard blockers, dropping sharply per blocker (floor \~0.3)
```

### 4.7 Distro recommendation

Rules over hardware + usage profile, presented as a ranked shortlist with reasons, not a
single decree:

* Heavy Steam library, modern AMD/NVIDIA GPU → **Bazzite** or **Nobara** (gaming-tuned)
* Windows-familiar UX priority, older hardware → **Linux Mint Cinnamon**
* Broad hardware support, mainstream default → **Ubuntu LTS**
* Very new hardware (recent GPU/wifi needing a fresh kernel) → **Fedora**

Flag when hardware needs a newer kernel than an LTS ships — this is a common first-boot
failure and a cheap win to catch.

\---

## 5\. The Compatibility Database

Read-only SQLite, shipped as a build artifact. **One comprehensive bundled DB — no lite/full split and no opt-in download for additional coverage.** The harvester targets all apps and games with quality upstream data (see §8); actual DB size is validated during the first harvester build rather than capped here. If size becomes a distribution problem, that is a harvester-compression or installer-choice decision, not an app-architecture decision.

```sql
CREATE TABLE app (
    app\_id        TEXT PRIMARY KEY,   -- canonical slug, e.g. "adobe.photoshop"
    name          TEXT NOT NULL,
    publisher     TEXT,
    category      TEXT,               -- creative|dev|office|utility|security|driver|game
    verdict       TEXT NOT NULL,      -- see §4.4
    confidence    TEXT NOT NULL,      -- data quality of the verdict itself
    linux\_native  INTEGER DEFAULT 0,
    notes         TEXT,               -- shown verbatim in report
    updated\_at    TEXT
);

CREATE TABLE app\_alias (
    alias\_norm    TEXT NOT NULL,      -- normalised form, indexed
    app\_id        TEXT NOT NULL REFERENCES app(app\_id),
    source        TEXT,               -- curated|registry\_observed|upstream
    PRIMARY KEY (alias\_norm, app\_id)
);
CREATE INDEX idx\_alias\_norm ON app\_alias(alias\_norm);

CREATE TABLE app\_package (          -- how to get it on Linux
    app\_id        TEXT REFERENCES app(app\_id),
    ecosystem     TEXT,               -- flatpak|snap|apt|dnf|appimage|web
    package\_id    TEXT,
    is\_official   INTEGER,
    install\_hint  TEXT                -- "flatpak install flathub org.gimp.GIMP"
);

CREATE TABLE app\_alternative (      -- for verdict='replace'
    app\_id        TEXT REFERENCES app(app\_id),
    alt\_app\_id    TEXT,
    alt\_name      TEXT,
    rank          INTEGER,
    rationale     TEXT,               -- "closest feature parity for raster editing"
    caveat        TEXT                -- "no CMYK workflow"
);

CREATE TABLE game (
    steam\_appid   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    native\_linux  INTEGER DEFAULT 0,
    deck\_verified TEXT,               -- verified|playable|unsupported|unknown
    proton\_tier   TEXT,               -- platinum|gold|silver|bronze|borked
    proton\_sample INTEGER,            -- report count — low sample = low confidence
    anticheat     TEXT,               -- none|eac\_linux\_ok|battleye\_linux\_ok|kernel\_blocked
    notes         TEXT,
    updated\_at    TEXT
);

CREATE TABLE game\_alias (           -- for non-Steam launchers
    alias\_norm    TEXT NOT NULL,
    steam\_appid   INTEGER REFERENCES game(steam\_appid),
    launcher      TEXT,               -- epic|gog|xbox
    launcher\_id   TEXT,
    PRIMARY KEY (alias\_norm, launcher)
);

CREATE TABLE hardware (
    vendor\_id     TEXT NOT NULL,      -- "10DE"
    device\_id     TEXT,               -- "2484", NULL = whole-vendor rule
    class         TEXT,               -- gpu|wifi|bluetooth|audio|printer|storage|nic
    driver        TEXT,               -- in-tree module name, or "proprietary"
    support       TEXT NOT NULL,      -- excellent|good|needs\_setup|poor|unsupported
    min\_kernel    TEXT,
    notes         TEXT,
    PRIMARY KEY (vendor\_id, device\_id, class)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
-- build\_date, schema\_version, source\_snapshot\_dates, record counts
```

The app opens this with `?mode=ro` and treats it as immutable.

\---

## 6\. Collectors — Implementation Notes

### 6.1 Desktop apps

* **Primary:** `winreg` over the Uninstall keys:

  * `HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall`
  * `HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall`
  * `HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall`
Capture `DisplayName`, `Publisher`, `DisplayVersion`, `InstallDate`, `InstallLocation`,
`SystemComponent` (filter these out), `ParentKeyName` (filter update entries).
* **Store apps:** `Get-AppxPackage` via the PS shim. Package Family Name is a stable exact key.
* **Portable apps (opt-in, Phase 2):** scan `%LOCALAPPDATA%\\Programs`, Desktop shortcuts and
Start Menu `.lnk` targets. Noisy — off by default.

> \*\*Do not use `Win32\_Product`.\*\* Querying it triggers an MSI consistency check on every
> installed product, which is slow and can cause repair/reconfigure events. This is a
> well-known Windows footgun. Registry enumeration only.

### 6.2 Games

* **Steam:** read `steamapps/libraryfolders.vdf` for library roots (users move games to other
drives — handle multi-library), then parse `appmanifest\_\*.acf` in each for `appid`, `name`,
`SizeOnDisk`, `LastPlayed`. Small VDF parser, no external service.
* **Epic:** `%ProgramData%\\Epic\\EpicGamesLauncher\\Data\\Manifests\\\*.item` — plain JSON, has
`DisplayName`, `AppName`, `InstallLocation`.
* **GOG:** `HKLM\\SOFTWARE\\WOW6432Node\\GOG.com\\Games\\<id>` for `gameName`, `path`. Galaxy's
SQLite DB is a richer but more fragile fallback.
* **Xbox / Game Pass:** Appx packages + `WindowsApps` folder. Note in the report that Game
Pass PC has no Linux path at all — that's a category-level blocker.
* **Battle.net / EA / Ubisoft:** Phase 2, via registry + install-dir heuristics.

### 6.3 Hardware \& firmware

PowerShell shim invoked via `subprocess`, returning JSON (`ConvertTo-Json -Depth 4`). CIM
coverage is better and less brittle than the Python WMI bindings, and it keeps the queries
readable.

Collect:

* `Win32\_VideoController` → GPU name + `PNPDeviceID`
* `Win32\_PnPEntity` → **all** `PCI\\VEN\_xxxx\&DEV\_xxxx` and `USB\\VID\_xxxx\&PID\_xxxx` IDs. These
vendor/device pairs are the real matching key against the `hardware` table — product
marketing names are useless for driver lookup.
* `Win32\_NetworkAdapter` (physical only) → wifi/ethernet chipsets. **Broadcom wifi is the
classic first-boot blocker** — flag it loudly.
* `Win32\_Printer` → model names, matched against a CUPS/Gutenprint/driver support table.
* `Win32\_ComputerSystem`, `Win32\_Processor`, `Win32\_PhysicalMemory` → system summary.

Firmware/boot checks (these produce the highest-value blockers):

* `Confirm-SecureBootUEFI` — Secure Boot state affects out-of-tree module signing.
* `Get-BitLockerVolume` — encrypted volumes must be handled before repartitioning.
* Storage controller mode — **Intel RST / RAID-on mode makes Linux installers not see the
disk at all.** Detect via storage controller PNP ID and flag with a remediation note.
* Free space on the target disk + partition count (MBR 4-primary limit).
* `Get-Disk` partition style: GPT vs MBR.

Admin-only extras: some BitLocker detail, some firmware queries. Degrade cleanly and label
the gap in the report rather than failing.

\---

## 7\. Scan Result Format

Collector output and matched results serialise to a versioned JSON (`shared/schema/`). Saved
to `%LOCALAPPDATA%\\LinuxReady\\scans\\`. This makes the pipeline replayable: re-run matching
and verdicts against a newer `compat.db` without touching the machine again, and lets users
attach a scan to a bug report.

```json
{
  "schema\_version": "1.0",
  "scan\_id": "uuid",
  "scanned\_at": "2026-08-14T10:22:31+10:00",
  "db\_build": "2026-08-01",
  "app\_version": "0.3.0",
  "system": { "os\_version": "...", "cpu": "...", "ram\_gb": 32, "secure\_boot": true },
  "collectors": \[ { "id": "steam", "status": "ok", "duration\_ms": 412, "warnings": \[] } ],
  "items": \[
    {
      "source": "steam",
      "raw\_name": "Cyberpunk 2077",
      "raw\_keys": { "steam\_appid": 1091500 },
      "matched\_id": "steam:1091500",
      "match\_tier": 1,
      "match\_confidence": "exact",
      "verdict": "layer\_excellent",
      "is\_blocker": false,
      "evidence": \["ProtonDB Gold, 4812 reports", "Steam Deck Verified"],
      "actions": \["Install via Steam, enable Proton Experimental"]
    }
  ],
  "score": { "value": 87, "hard\_blockers": 1, "unknown\_count": 6 }
}
```

\---

## 8\. The Harvester

Python + Docker, runs in CI on a schedule (weekly), publishes a versioned `compat.db`.

**Sources:**

|Source|Feeds|Notes|
|-|-|-|
|ProtonDB|`game.proton\_tier`, `proton\_sample`|Respect rate limits; cache aggressively|
|Steam Web API / SteamDB|game names, native Linux flag|AppID is the canonical game key|
|Steam Deck verification|`deck\_verified`|Strong signal, often better than ProtonDB|
|WineHQ AppDB|desktop app ratings|Scraped; brittle — validate hard|
|Flathub API|`app\_package` rows|Official-vs-community flag matters|
|Repology|distro package presence|Good breadth for `packaged` verdicts|
|`pci.ids` + kernel driver data|`hardware` table|Vendor/device → in-tree module|
|AreWeAntiCheatYet|`game.anticheat`|The single most decisive game field|
|**`data/overrides/\*.yaml`**|everything|Hand-curated. Always wins.|

**The overrides layer is the product.** Automated sources give breadth; the curated YAML gives
the judgement calls — "Photoshop → GIMP/Krita/Photopea, but no CMYK", "Office → LibreOffice or
web, macro compatibility is the risk". Treat these files as reviewed source, PR-gated.

**Validation gates before publish** (`validate.py` — fail the build, don't ship silently):

* Record counts within ±20% of the previous build.
* No verdict regressions on a golden set of \~200 well-known apps/games.
* Schema conformance; no orphan foreign keys.
* Every `verdict='replace'` row has ≥1 alternative.

**Publish:** `compat-YYYY.MM.DD.db` + `.sha256` to a static host. The app verifies the checksum
before swapping the DB, and keeps the previous file for rollback.

**Legal/etiquette:** honour robots.txt and ToS, identify with a real User-Agent and contact
URL, cache hard, and credit every source in the report footer and README.

\---

## 9\. GUI (PySide6)

Five screens, wizard-flavoured but non-linear:

1. **Welcome** — what this does, explicit "nothing leaves your PC", Start Scan.
2. **Scanning** — per-collector progress, live item count, cancellable.
3. **Results** — score + hard blockers up top, then tabbed Apps / Games / Hardware, filterable
by verdict. Blockers pinned.
4. **Item detail** — evidence, install hints, alternatives, "this match is wrong" link.
5. **Settings** — DB version + refresh button, enable portable-app scan, export path.

Notes:

* All scan work in `scan\_worker.py` on a `QThread`, communicating by signals. No blocking calls
on the GUI thread, ever.
* **Theme: `qdarktheme` (PyQtDarkTheme).** Single dependency, first-class PySide6 support,
runtime-switchable. Default: dark. Toggle in Settings persisted to
`%LOCALAPPDATA%\LinuxReady\settings.json` under key `"theme"` (`"dark"` | `"light"` |
`"auto"`). Applied at startup and on toggle:
  ```python
  import qdarktheme
  qdarktheme.setup_theme(settings.theme)   # re-call on toggle to refresh live
  ```
* **Accent colour: teal (#00B4D8).** The verdict palette owns red/yellow/green; teal sits
outside that range. Pass via `qdarktheme.setup_theme(..., custom_colors={"primary": "#00B4D8"})`.
* **Typography: system default (Segoe UI).** Qt picks this on Windows automatically; do not
override the font family.
* **Branding: logotype text only.** "LinuxReadyAmI" rendered in the window title and Welcome
screen header. No icon required for MVP; add a `.ico` before first public release for
taskbar/installer presentation.
* Accessibility: keyboard navigable, real labels on all controls.
* **License: GPL-3.0** (see §15.4). Add `LICENSE` to the repo root before the first public
commit; set `license = {text = "GPL-3.0-only"}` in both `pyproject.toml` files.
* **PySide6 is LGPL** — dynamic linking only, ship the license text, document how a user can
replace the Qt libs. Straightforward with PyInstaller's default one-dir layout; don't
statically bind Qt. GPL-3.0 on the app is compatible with PySide6's LGPL-3.0.

\---

## 10\. Report Output

Jinja2 → **one self-contained `.html` file**. Inline CSS, inline JS, no CDN, no external fonts,
no network requests when opened. It must render correctly on a machine with no internet, and be
safe to paste into a forum thread.

Sections: summary + score → hard blockers with remediation → recommended distro(s) with
reasons → apps table → games table → hardware table → unknowns → methodology \& sources →
scan metadata (app version, DB build date).

Escape all collected strings — app names come from the registry and are untrusted input.
Offer a "redact machine identifiers" toggle before export.

\---

## 11\. Privacy \& Security

* No telemetry. No analytics. No crash reporting without an explicit opt-in prompt.
* The only outbound request is the user-initiated DB update check.
* Scan results never leave the machine unless the user exports them.
* App runs as standard user; admin optional and clearly justified in-UI when requested.
* Read-only registry and filesystem access. No writes outside `%LOCALAPPDATA%\\LinuxReady`.
* Verify DB downloads by SHA-256 against a signature published alongside the release.
* Treat all collected strings as untrusted when rendering.

\---

## 12\. Packaging \& Distribution

* **License: GPL-3.0** — `LICENSE` file in repo root; `license = {text = "GPL-3.0-only"}` in
both `pyproject.toml` files. See §15.4 for compatibility notes.
* **PyInstaller** one-dir build (not one-file — respects LGPL dynamic linking and starts faster).
* Optional MSI/Inno wrapper for a conventional install experience; also ship a portable ZIP.
* Code signing strongly recommended — an unsigned exe that reads your registry and enumerates
your hardware is exactly what SmartScreen exists to warn about. Budget for a cert.
* Version the app and the DB independently; show both in the UI and the report.
* CI: build on Windows runner, run tests, produce signed artifacts, attach to GitHub Release.

\---

## 13\. Testing

* **Collector fixtures.** Capture real registry exports, `appmanifest\_\*.acf`, Epic `.item`
files, and CIM JSON into `tests/fixtures/`. Every collector must be testable with zero
Windows API access so tests run in CI/Linux containers.
* **Matcher golden set.** A CSV of \~300 real-world `DisplayName` strings → expected `app\_id`.
This is the regression net for the messiest part of the system; grow it from every bad-match
report.
* **Verdict rules:** table-driven unit tests.
* **DB validation:** the harvester's `validate.py` runs in CI on every build.
* **Report rendering:** snapshot test + assert zero external URLs in output HTML.
* Manual matrix: Win10/Win11, admin/non-admin, multi-drive Steam, no-games machine,
no-network machine.

\---

## 14\. Phasing

**Phase 1 — MVP**
Registry apps + Steam + GPU/wifi/storage-mode hardware. Full bundled DB (one comprehensive DB,
no coverage cap — see §5 and §15.2). Score, blockers, HTML report. Ships without the update
button or bad-match link.

**Phase 2**
Epic/GOG/Xbox collectors, MSIX apps, printers, DB opt-in refresh, alternatives with rationale,
distro recommendation, bad-match reporting via pre-filled GitHub Issue URL (§15.1).

**Phase 3**
User data migration sizing (browser profiles, Documents, mail stores), dual-boot feasibility
(partition/free-space analysis), export a personalised post-install setup script
(`flatpak install ...` for everything matched), community-contributed overrides.

\---

## 15\. Decisions

### 15.1 Bad-match reporting: pre-filled GitHub Issue URL

**Decision:** The app generates a pre-filled GitHub Issue URL that the user clicks manually.
The app makes no network request — the user's browser opens the issue form. Mechanism:

```python
# config.py
GITHUB_REPO = "linuxreadyami/linuxready"   # update once repo is created

# matcher/resolver.py, called from item-detail UI
def bad_match_url(item: ScanItem) -> str:
    params = urlencode({
        "labels": "bad-match",
        "template": "bad-match.yml",
        "title": f'Bad match: "{item.raw_name}"',
        "app_id": item.matched_id or "none",
        "match_tier": item.match_tier,
        "confidence": item.match_confidence,
        "app_version": __version__,
        "db_build": db_meta("build_date"),
    })
    return f"https://github.com/{GITHUB_REPO}/issues/new?{params}"
```

**Privacy constraint (§11):** the URL carries only the raw name string, the wrong matched ID,
the match tier/confidence, app version, and DB build date. It must not include hardware IDs,
scan file paths, or any other machine-identifying fields. Per §10, the raw name comes from
the registry and is already visible in the report; no additional redaction step is needed
for this URL specifically.

**Repo asset required:** `.github/ISSUE_TEMPLATE/bad-match.yml` with fields that map to the
URL parameters above. This makes the pre-fill land in structured form fields rather than a
free-text body and makes triage programmatic.

**Phasing:** Item-detail UI wire-up is Phase 2 (§14). The `bad_match_url()` helper and the
issue template can be committed in Phase 1 so the infrastructure is ready.

---

### 15.2 DB bundling strategy: one full DB, no split

**Decision:** Ship one comprehensive SQLite DB with the installer. There is no "lite" DB and
no opt-in download for additional coverage. Coverage is constrained only by data quality from
upstream sources, not by an artificial size cap.

**Scope intent:** all apps and games for which we have quality verdict data — expected to be
the full ProtonDB-rated game set, all Flathub/WineHQ-listed desktop apps, and the full
`pci.ids` hardware table. The harvester's `validate.py` is the right place to gate on
coverage minimums, not a size ceiling in this document.

**Size:** measured and decided during first harvester build. If the installer becomes
impractically large, the right lever is harvester-side SQLite compression (e.g. `VACUUM`,
page-size tuning) or installer compression, not splitting coverage.

---

### 15.3 Anticheat update cadence: standard weekly for now, revisit in Phase 3

**Decision:** `game.anticheat` refreshes on the same weekly harvester schedule as all other
fields. A dedicated higher-cadence anticheat channel is deferred.

**Rationale:** EAC and BattlEye Linux support does toggle per-game without warning. However,
building a separate update mechanism before the primary update flow (Phase 2, §14) even
exists is premature. The right mitigation for v1 is a visible staleness note in the UI:

> "Anticheat status as of {db\_build\_date}. Status can change without notice — check
> [AreWeAntiCheatYet.com](https://areweanticheatyet.com/) for the current state of a
> specific game."

Revisit a shorter anticheat-only refresh cadence in Phase 3, once the opt-in DB update
button (Phase 2) is live and the operational cost of running the harvester more frequently
is understood.

---

### 15.4 License: GPL-3.0

**Decision:** GPL-3.0. Add `LICENSE` (full GPL-3.0 text) to the repo root before the first
public commit. Set `license = {text = "GPL-3.0-only"}` in both `pyproject.toml` files.

**Compatibility note:** PySide6 is LGPL-3.0. GPL-3.0 on the application code is compatible
with LGPL-3.0 on the library — the app is more restrictive, which is permitted. Dynamic
linking (already required by §9's PyInstaller one-dir constraint) satisfies the LGPL
requirement. No conflict with the rest of the stack (ProtonDB data, pci.ids, WineHQ scrape
content have their own terms; the DB build artifact is a factual compilation, not a GPL
work). See §12 for the LGPL ship requirement on Qt libs.

