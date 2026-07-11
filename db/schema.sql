-- Schema para Flujos
-- Base de datos de medios del viaje Buenos Aires → Tucumán
-- Los archivos físicos NO se mueven. La DB es el índice.

CREATE TABLE IF NOT EXISTS media (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    filename_original TEXT NOT NULL,          -- nombre original del archivo
    filepath_absoluto TEXT NOT NULL,          -- ruta completa en disco
    filepath_relativo TEXT NOT NULL,          -- ruta relativa a la raíz de ingest
    carpeta           TEXT,                   -- nombre de la carpeta contenedora
    type              TEXT NOT NULL,          -- image, video, audio, text, other
    subtype           TEXT,                   -- 360, entrevista, paisaje, etc.

    -- Fingerprints
    size_bytes        INTEGER,
    file_hash         TEXT NOT NULL UNIQUE,   -- SHA-256 del archivo completo
    content_hash      TEXT,                   -- SHA-256 del contenido puro (sin metadatos)

    -- Sidecar XML SONY
    sidecar_xml       TEXT,                   -- ruta al XML sidecar (relativo a root si aplica)
    sidecar_parsed    INTEGER DEFAULT 0,      -- 1 si ya se procesó el XML
    sidecar_hash      TEXT,                   -- SHA-256 del XML (para detectar cambios)

    -- Tiempos
    timestamp_original TEXT,                  -- timestamp tal cual viene del archivo
    timestamp_utc     TEXT,                   -- normalizado a UTC
    timezone_note     TEXT,                   -- cómo se determinó: "EXIF offset -03:00", "asumido ART", etc.

    -- Geolocalización
    latitude          REAL,                   -- latitud (WGS84)
    longitude         REAL,                   -- longitud (WGS84)
    altitude          REAL,                   -- altitud en metros
    geolocation_source TEXT,                  -- 'metadata', 'inferido_tiempo', 'track_gps', 'manual'

    -- Autor
    author            TEXT,                   -- nombre de quien creó el medio
    author_source     TEXT,                   -- 'exif', 'carpeta', 'modelo_camara', 'combinado'

    -- Paleta de colores (imágenes)
    color_1_hex       TEXT,                   -- color dominante 1 en hex
    color_1_name_css  TEXT,                   -- nombre CSS en español
    color_1_name_basic TEXT,                  -- nombre básico (rojo, azul, etc.)
    color_2_hex       TEXT,                   -- color dominante 2
    color_2_name_css  TEXT,
    color_2_name_basic TEXT,
    color_3_hex       TEXT,                   -- color dominante 3
    color_3_name_css  TEXT,
    color_3_name_basic TEXT,

    -- Control
    ingested_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media_metadata (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    TEXT,
    UNIQUE(media_id, key)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_media_content_hash ON media(content_hash);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(type);
CREATE INDEX IF NOT EXISTS idx_media_carpeta ON media(carpeta);
CREATE INDEX IF NOT EXISTS idx_media_timestamp_utc ON media(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_media_latlon ON media(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_metadata_key ON media_metadata(key);
