# LinuxReadyAmI

A Windows desktop app that scans your installed apps, games, and hardware, then tells you concretely what would happen if you switched to Linux: what works natively, what works via a compatibility layer, what needs a replacement, and what would block you entirely.

No account. No telemetry. No network requests during a scan. Produces a single self-contained HTML file you can share on a forum.

---

## Quickstart

### Prerequisites

- Windows 10/11
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for package management

### Install

```powershell
cd app
uv venv
uv pip install -e ".[dev]"
```

### Generate the compatibility database

The app ships with a seed database for development. Generate it before first run:

```powershell
.venv\Scripts\python.exe -m linuxready.db.seed
```

This writes `app/src/linuxready/db/compat.db`. In a production build, this file is bundled in the installer and updated separately via the harvester.

### Run

**CLI — saves an HTML report automatically:**
```powershell
.venv\Scripts\python.exe -m linuxready
```
Report is saved to `%LOCALAPPDATA%\LinuxReady\scans\scan_<id>.html`.

**CLI — specify output paths:**
```powershell
.venv\Scripts\python.exe -m linuxready --report my-report.html --json my-scan.json
```

**GUI:**
```powershell
.venv\Scripts\python.exe -m linuxready --gui
```

**Run tests:**
```powershell
.venv\Scripts\python.exe -m pytest
```

---

## CLI reference

```
linuxready [--db PATH] [--report FILE] [--json FILE] [--gui]
```

| Flag | Description |
|------|-------------|
| `--db PATH` | Use a specific `compat.db` instead of the bundled one |
| `--report FILE` | Write the HTML report to `FILE` |
| `--json FILE` | Write the raw scan result as JSON to `FILE` |
| `--gui` | Launch the desktop GUI instead of running a CLI scan |

You can also point at a different database via environment variable:

```powershell
$env:LINUXREADY_DB = "C:\path\to\compat.db"
linuxready
```

---

## Understanding the report

### Readiness score (0–100)

Weighted pass rate across three groups:

| Group | Weight |
|-------|--------|
| Hardware & firmware | 40% |
| Apps | 35% |
| Games | 25% |

Each hard blocker applies a 15% penalty on top of the pass-rate calculation (minimum multiplier: 0.30). A group with no recognised items contributes a neutral 1.0 rather than penalising the score.

### Verdict meanings

| Verdict | Meaning |
|---------|---------|
| **native** | A Linux-native version exists (Steam Linux, Flatpak, distro package) |
| **packaged** | Available in a distro package manager or Flatpak |
| **layer_excellent** | Runs via Wine/Proton with ProtonDB Gold/Platinum rating |
| **layer_workable** | Runs via Wine/Proton with Silver rating; may need tweaking |
| **layer_poor** | Runs with significant issues (Bronze or worse) |
| **web** | No desktop Linux app; the web version covers the same use case |
| **replace** | No Linux equivalent; the report lists alternatives |
| **blocked** | Cannot run on Linux at all (kernel-level anticheat, RST/RAID storage, <30 GB free disk) |
| **unknown** | Not in the compatibility database |

### Hard blockers

Items flagged as hard blockers appear at the top of the report and include actionable notes. Common blockers:

- **Kernel-level anticheat** — games using Ricochet, FACEIT, or BattlEye kernel mode; cannot be worked around
- **RST/RAID storage mode** — Linux installers cannot see the disk; must switch to AHCI in BIOS/UEFI first
- **Low disk space** — less than 30 GB free on the system drive
- **Adobe Creative Cloud** — no Linux path; the report suggests open-source and web alternatives

### Unknown items

"Unknown" means the item isn't in the compatibility database yet — not that it won't work. The seed database covers common software; the full harvester-built database covers thousands more entries.

---

## Project layout

```
LinuxCompatibility/
├── app/                        # Windows desktop app (this package)
│   ├── src/linuxready/
│   │   ├── collectors/         # Steam, registry apps, hardware/firmware
│   │   ├── matcher/            # 6-tier name resolution cascade
│   │   ├── verdict/            # Rules engine + 0-100 score
│   │   ├── report/             # Jinja2 HTML report renderer
│   │   ├── ui/                 # PySide6 GUI (Welcome → Scanning → Results)
│   │   ├── db/                 # Schema, seed script, read-only access layer
│   │   └── ps/                 # PowerShell shims for hardware/firmware data
│   └── tests/                  # 29 unit tests; all run without Windows API access
├── harvester/                  # Docker CI job that builds the production compat.db
│   └── data/overrides/         # Curated YAML entries (always win over automated sources)
├── shared/schema/              # JSON Schema for the scan output format
└── ARCHITECTURE.md             # Full design spec (authoritative)
```

---

## Adding compatibility data

### Curated YAML overrides (recommended)

Curated entries always take priority over automated harvester data. Edit the YAML files in `harvester/data/overrides/`:

**`apps.yaml`** — desktop apps:
```yaml
- app_id: vendor.appname
  name: App Name
  publisher: Vendor
  verdict: replace          # native | packaged | layer_excellent | layer_workable | layer_poor | web | replace | blocked
  confidence: high
  linux_native: false
  notes: "Optional context"
  packages:
    - ecosystem: flatpak
      package_id: org.example.App
      is_official: true
      install_hint: "flatpak install flathub org.example.App"
  alternatives:             # for verdict: replace
    - alt_name: Open-Source Alternative
      rationale: "Covers 90% of common use cases"
      caveat: "No CMYK support"
      rank: 1
  aliases:
    - alias: "App Name"
      source: curated
```

**`games.yaml`** — Steam games:
```yaml
- steam_appid: 1234567
  name: Game Name
  native_linux: false
  deck_verified: playable
  proton_tier: gold
  proton_sample: 1200
  anticheat: none           # none | eac_linux_ok | kernel_blocked
  notes: "Optional context"
```

### Hardware entries

Hardware matching uses PCI vendor/device IDs. Add entries to the `hardware` table in the DB or contribute to the harvester's `pci.ids` ingest (Phase 2).

### Running the harvester locally

```powershell
cd harvester
uv venv
uv pip install -e .
harvest --output compat.db --skip-network   # applies curated overrides only
```

---

## How matching works

The app uses a 6-tier cascade to match installed software against the database:

1. **Steam app ID** — exact match via Steam's numeric app ID (most reliable)
2. **Curated alias** — hand-maintained name mappings (`source='curated'`)
3. **Normalised name + publisher** — strips version numbers, arch tags (x64/ARM), trademark symbols, then matches by name and publisher
4. **Unique normalised name** — same normalisation, but only if the name is unambiguous in the DB
5. **Fuzzy** — `token_set_ratio ≥ 88` across all known aliases (rapidfuzz)
6. **Unknown** — item appears in the report but contributes no signal to the score

Match tier and confidence are included in the JSON output for every item.

---

## JSON output format

The JSON output conforms to `shared/schema/scan_result.schema.json`. Top-level fields:

```json
{
  "schema_version": "1.0",
  "scan_id": "<uuid>",
  "scanned_at": "<iso8601>",
  "db_build": "2026-08-14",
  "app_version": "0.1.0",
  "system": { "os_version": "...", "cpu": "...", "ram_gb": null, "secure_boot": null },
  "collectors": [{ "id": "steam", "status": "ok", "duration_ms": 120, "warnings": [] }],
  "items": [
    {
      "source": "steam",
      "raw_name": "Cyberpunk 2077",
      "raw_keys": { "steam_appid": 1091500 },
      "matched_id": "steam:1091500",
      "match_tier": 1,
      "match_confidence": "exact",
      "verdict": "layer_excellent",
      "verdict_reason": null,
      "is_blocker": false,
      "evidence": ["ProtonDB: Gold (4,812 reports)", "Steam Deck: playable"],
      "actions": ["Enable Proton in Steam › Settings › Compatibility"]
    }
  ],
  "score": { "value": 87, "hard_blockers": 1, "unknown_count": 42 }
}
```

---

## Privacy

- **No network requests during a scan.** The app reads the local filesystem and registry only.
- **No telemetry.** Nothing is transmitted anywhere.
- **No account required.**
- The HTML report is a local file. Sharing it is your choice.
- The optional "Update database" button (Phase 2, not yet implemented) will download a new `compat.db` over HTTPS — opt-in only, no scan data is sent.

---

## License

GPL-3.0-only. PySide6 is used under LGPL-3.0 via dynamic linking.

Data sources credited in each report: ProtonDB, Steam, Flathub, WineHQ AppDB, AreWeAntiCheatYet, pci.ids, Repology.
