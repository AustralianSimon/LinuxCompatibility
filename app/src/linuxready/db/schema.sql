-- LinuxReadyAmI compatibility database schema
-- Opened read-only by the app (?mode=ro). Never written by the app.

CREATE TABLE IF NOT EXISTS app (
    app_id        TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    publisher     TEXT,
    category      TEXT,
    verdict       TEXT NOT NULL,
    confidence    TEXT NOT NULL,
    linux_native  INTEGER DEFAULT 0,
    notes         TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS app_alias (
    alias_norm    TEXT NOT NULL,
    app_id        TEXT NOT NULL REFERENCES app(app_id),
    source        TEXT,
    PRIMARY KEY (alias_norm, app_id)
);
CREATE INDEX IF NOT EXISTS idx_alias_norm ON app_alias(alias_norm);

CREATE TABLE IF NOT EXISTS app_package (
    app_id        TEXT REFERENCES app(app_id),
    ecosystem     TEXT,
    package_id    TEXT,
    is_official   INTEGER,
    install_hint  TEXT
);

CREATE TABLE IF NOT EXISTS app_alternative (
    app_id        TEXT REFERENCES app(app_id),
    alt_app_id    TEXT,
    alt_name      TEXT,
    rank          INTEGER,
    rationale     TEXT,
    caveat        TEXT
);

CREATE TABLE IF NOT EXISTS game (
    steam_appid   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    native_linux  INTEGER DEFAULT 0,
    deck_verified TEXT,
    proton_tier   TEXT,
    proton_sample INTEGER,
    anticheat     TEXT,
    notes         TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS game_alias (
    alias_norm    TEXT NOT NULL,
    steam_appid   INTEGER REFERENCES game(steam_appid),
    launcher      TEXT,
    launcher_id   TEXT,
    PRIMARY KEY (alias_norm, launcher)
);

CREATE TABLE IF NOT EXISTS hardware (
    vendor_id     TEXT NOT NULL,
    device_id     TEXT,
    class         TEXT,
    driver        TEXT,
    support       TEXT NOT NULL,
    min_kernel    TEXT,
    notes         TEXT,
    PRIMARY KEY (vendor_id, device_id, class)
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
