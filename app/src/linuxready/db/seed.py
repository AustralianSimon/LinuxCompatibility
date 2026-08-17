"""
Create a minimal compat.db for development and testing.
Run: python -m linuxready.db.seed [output_path]
"""
import sqlite3
import sys
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"


def create_seed_db(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    conn = sqlite3.connect(output)
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

    conn.executemany("INSERT INTO meta VALUES (?,?)", [
        ("build_date", "2026-08-14"),
        ("schema_version", "1"),
        ("source", "seed"),
    ])

    # fmt: off
    games = [
        # appid, name, native, deck, proton_tier, sample, anticheat, notes
        (570,       "Dota 2",                          1, "verified",   "platinum", 500,  "none",             None),
        (440,       "Team Fortress 2",                 1, "verified",   "platinum", 300,  "none",             None),
        (730,       "Counter-Strike 2",                1, "verified",   "platinum", 800,  "none",             None),
        (1091500,   "Cyberpunk 2077",                  0, "playable",   "gold",     4812, "none",             "Some mods may not work on Linux"),
        (271590,    "Grand Theft Auto V",              0, "playable",   "gold",     3000, "none",             None),
        (1174180,   "Red Dead Redemption 2",           0, "playable",   "gold",     2100, "none",             None),
        (526870,    "Satisfactory",                    0, "playable",   "gold",     1500, "none",             None),
        (252490,    "Rust",                            0, "playable",   "silver",   900,  "eac_linux_ok",     None),
        (578080,    "PUBG: Battlegrounds",             0, "unsupported","gold",     1200, "eac_linux_ok",     None),
        (1172470,   "Apex Legends",                    0, "unsupported","bronze",   200,  "eac_linux_ok",     "EAC Linux support varies by update"),
        (1938090,   "Call of Duty: Modern Warfare III",0, "unsupported","borked",   50,   "kernel_blocked",   "Kernel-level anticheat (Ricochet) blocks Linux"),
        (359550,    "Tom Clancy's Rainbow Six Siege",  0, "unsupported","borked",   80,   "kernel_blocked",   "BattlEye kernel-level anticheat blocks Linux"),
    ]
    # fmt: on
    conn.executemany(
        "INSERT INTO game VALUES (?,?,?,?,?,?,?,?,date('now'))",
        games,
    )

    # fmt: off
    apps = [
        # app_id, name, publisher, category, verdict, confidence, linux_native, notes
        ("mozilla.firefox",    "Firefox",              "Mozilla",           "utility",  "native",   "high",  1, "Available as Flatpak, .deb, and .rpm"),
        ("google.chrome",      "Google Chrome",        "Google",            "utility",  "native",   "high",  1, "Linux builds at google.com/chrome"),
        ("microsoft.vscode",   "Visual Studio Code",   "Microsoft",         "dev",      "native",   "high",  1, "Linux builds at code.visualstudio.com"),
        ("adobe.photoshop",    "Adobe Photoshop",      "Adobe",             "creative", "replace",  "high",  0, "No Linux version. Consider Krita, GIMP, or Photopea."),
        ("adobe.premiere",     "Adobe Premiere Pro",   "Adobe",             "creative", "replace",  "high",  0, "No Linux version. Consider DaVinci Resolve (free tier)."),
        ("adobe.illustrator",  "Adobe Illustrator",    "Adobe",             "creative", "replace",  "high",  0, "No Linux version. Consider Inkscape."),
        ("microsoft.office",   "Microsoft Office",     "Microsoft",         "office",   "web",      "high",  0, "Microsoft 365 web works on Linux. LibreOffice for offline use."),
        ("valve.steam",        "Steam",                "Valve",             "utility",  "native",   "exact", 1, "Steam Linux client is the primary platform"),
        ("discord.discord",    "Discord",              "Discord",           "utility",  "native",   "high",  1, "Flatpak and .deb available"),
        ("7zip.7zip",          "7-Zip",                "Igor Pavlov",       "utility",  "packaged", "high",  1, "p7zip in distro repos; 7-Zip 24.x also has an official Linux build"),
        ("vlc.vlc",            "VLC media player",     "VideoLAN",          "utility",  "native",   "high",  1, "Available on all major distros and Flathub"),
        ("obs.obs",            "OBS Studio",           "OBS Project",       "utility",  "native",   "high",  1, "Full-featured Linux version available"),
        ("spotify.spotify",    "Spotify",              "Spotify AB",        "utility",  "native",   "high",  1, "Flatpak and .deb available"),
        ("slack.slack",        "Slack",                "Slack Technologies","office",   "native",   "high",  1, "Linux client and Flatpak available"),
        ("notion.notion",      "Notion",               "Notion Labs",       "office",   "web",      "high",  0, "No desktop app needed; web version works well on Linux"),
        ("git.git",            "Git",                  "Software Freedom Conservancy","dev","native","high", 1, "First-class Linux support"),
        ("python.python",      "Python",               "Python Software Foundation","dev","native","high",    1, "First-class Linux support"),
        ("winrar.winrar",      "WinRAR",               "RARLAB",            "utility",  "packaged", "high",  1, "rar/unrar available in distro repos"),
        ("malwarebytes.mb",    "Malwarebytes",         "Malwarebytes",      "security", "replace",  "high",  0, "No Linux version. Use ClamAV or distro-provided security tools."),
        ("googledrive.backup", "Google Drive",         "Google",            "utility",  "web",      "high",  0, "Web interface works; Insync or rclone provide sync on Linux"),
    ]
    # fmt: on
    conn.executemany(
        "INSERT INTO app VALUES (?,?,?,?,?,?,?,?,date('now'))",
        apps,
    )

    aliases = [
        ("firefox",                     "mozilla.firefox",   "curated"),
        ("mozilla firefox",             "mozilla.firefox",   "upstream"),
        ("google chrome",               "google.chrome",     "upstream"),
        ("chrome",                      "google.chrome",     "curated"),
        ("visual studio code",          "microsoft.vscode",  "upstream"),
        ("vscode",                      "microsoft.vscode",  "curated"),
        ("vs code",                     "microsoft.vscode",  "curated"),
        ("adobe photoshop",             "adobe.photoshop",   "upstream"),
        ("photoshop",                   "adobe.photoshop",   "curated"),
        ("adobe premiere pro",          "adobe.premiere",    "upstream"),
        ("premiere pro",                "adobe.premiere",    "curated"),
        ("adobe illustrator",           "adobe.illustrator", "upstream"),
        ("illustrator",                 "adobe.illustrator", "curated"),
        ("microsoft office",            "microsoft.office",  "upstream"),
        ("office",                      "microsoft.office",  "curated"),
        ("microsoft 365",               "microsoft.office",  "curated"),
        ("steam",                       "valve.steam",       "upstream"),
        ("discord",                     "discord.discord",   "upstream"),
        ("7-zip",                       "7zip.7zip",         "upstream"),
        ("7zip",                        "7zip.7zip",         "curated"),
        ("vlc media player",            "vlc.vlc",           "upstream"),
        ("vlc",                         "vlc.vlc",           "curated"),
        ("obs studio",                  "obs.obs",           "upstream"),
        ("obs",                         "obs.obs",           "curated"),
        ("spotify",                     "spotify.spotify",   "upstream"),
        ("slack",                       "slack.slack",       "upstream"),
        ("notion",                      "notion.notion",     "upstream"),
        ("git",                         "git.git",           "upstream"),
        ("python",                      "python.python",     "upstream"),
        ("winrar",                      "winrar.winrar",     "upstream"),
        ("malwarebytes",                "malwarebytes.mb",   "upstream"),
        ("google drive",                "googledrive.backup","upstream"),
        ("google backup and sync",      "googledrive.backup","upstream"),
        ("google drive for desktop",    "googledrive.backup","curated"),
    ]
    conn.executemany("INSERT INTO app_alias VALUES (?,?,?)", aliases)

    packages = [
        ("mozilla.firefox",  "flatpak", "org.mozilla.firefox",       1, "flatpak install flathub org.mozilla.firefox"),
        ("mozilla.firefox",  "apt",     "firefox",                   1, "sudo apt install firefox"),
        ("google.chrome",    "apt",     "google-chrome-stable",      1, "wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo dpkg -i google-chrome-stable_current_amd64.deb"),
        ("microsoft.vscode", "flatpak", "com.visualstudio.code",     0, "flatpak install flathub com.visualstudio.code"),
        ("microsoft.vscode", "apt",     "code",                      1, "See https://code.visualstudio.com/docs/setup/linux"),
        ("discord.discord",  "flatpak", "com.discordapp.Discord",    0, "flatpak install flathub com.discordapp.Discord"),
        ("discord.discord",  "apt",     "discord",                   0, "Download .deb from discord.com/download"),
        ("7zip.7zip",        "apt",     "7zip",                      0, "sudo apt install 7zip"),
        ("7zip.7zip",        "dnf",     "7zip",                      0, "sudo dnf install 7zip"),
        ("vlc.vlc",          "flatpak", "org.videolan.VLC",          1, "flatpak install flathub org.videolan.VLC"),
        ("vlc.vlc",          "apt",     "vlc",                       1, "sudo apt install vlc"),
        ("obs.obs",          "flatpak", "com.obsproject.Studio",     1, "flatpak install flathub com.obsproject.Studio"),
        ("obs.obs",          "apt",     "obs-studio",                1, "sudo apt install obs-studio"),
        ("spotify.spotify",  "flatpak", "com.spotify.Client",        0, "flatpak install flathub com.spotify.Client"),
        ("slack.slack",      "flatpak", "com.slack.Slack",           0, "flatpak install flathub com.slack.Slack"),
        ("winrar.winrar",    "apt",     "unrar",                     0, "sudo apt install unrar"),
    ]
    conn.executemany("INSERT INTO app_package VALUES (?,?,?,?,?)", packages)

    alternatives = [
        ("adobe.photoshop",  "krita.krita",        "Krita",           1, "Excellent for digital painting and photo editing",         "No CMYK workflow"),
        ("adobe.photoshop",  "gimp.gimp",          "GIMP",            2, "Full-featured raster editor, opens PSDs",                  "Steeper learning curve; no CMYK"),
        ("adobe.photoshop",  "photopea.photopea",  "Photopea",        3, "Web-based Photoshop clone, opens .psd files natively",     "Requires internet"),
        ("adobe.premiere",   "davinci.resolve",    "DaVinci Resolve", 1, "Professional NLE with a full-featured free tier on Linux",  "Requires modern GPU for best performance"),
        ("adobe.premiere",   "kdenlive.kdenlive",  "Kdenlive",        2, "Full-featured open-source NLE",                            "Less After Effects integration"),
        ("adobe.illustrator","inkscape.inkscape",  "Inkscape",        1, "Full-featured open-source SVG/vector editor",             "No CMYK; different UX"),
        ("microsoft.office", "libreoffice.lo",     "LibreOffice",     1, "Full offline office suite — Writer, Calc, Impress",        "Macro compatibility may vary; formatting differences"),
        ("malwarebytes.mb",  "clamav.clamav",      "ClamAV",          1, "Open-source antivirus, distro-packaged",                  "Command-line focused; use ClamTk for GUI"),
    ]
    conn.executemany("INSERT INTO app_alternative VALUES (?,?,?,?,?,?)", alternatives)

    hardware = [
        # vendor_id, device_id, class, driver, support, min_kernel, notes
        ("10DE", None, "gpu",       "nvidia",      "needs_setup", None,  "NVIDIA GPU: install proprietary drivers via your distro's driver manager. Excellent once installed."),
        ("1002", None, "gpu",       "amdgpu",      "excellent",   "5.4", "AMD GPU: excellent open-source amdgpu driver, in-kernel since 5.4"),
        ("8086", None, "gpu",       "i915",        "excellent",   "4.14","Intel iGPU: excellent open-source i915 driver"),
        ("14E4", None, "wifi",      "proprietary", "poor",        None,  "Broadcom WiFi: requires firmware package (broadcom-sta or b43). May not work on first boot — plan on wired connection for initial setup."),
        ("8086", None, "wifi",      "iwlwifi",     "excellent",   None,  "Intel WiFi: excellent in-kernel iwlwifi driver, works out of the box"),
        ("10EC", None, "wifi",      "rtl8821ce",   "needs_setup", "5.9", "Realtek WiFi: driver may need DKMS installation. See your distro's wiki."),
        ("168C", None, "wifi",      "ath9k",       "excellent",   None,  "Qualcomm/Atheros WiFi: excellent open-source ath9k/ath10k driver"),
        ("8086", None, "storage",   "ahci",        "excellent",   None,  "Intel storage controller (AHCI mode): full support"),
        ("1022", None, "storage",   "ahci",        "excellent",   None,  "AMD storage controller: full support"),
        ("8086", None, "audio",     "snd_hda_intel","excellent",  None,  "Intel HDA audio: excellent in-kernel support"),
        ("1002", None, "audio",     "snd_hda_intel","excellent",  None,  "AMD HDA audio: excellent in-kernel support"),
    ]
    conn.executemany("INSERT INTO hardware VALUES (?,?,?,?,?,?,?)", hardware)

    conn.commit()
    conn.close()
    print(f"Seed DB written to {output}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "compat.db"
    create_seed_db(out)
