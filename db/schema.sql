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
    duration_secs     REAL,                   -- duración en segundos (videos, audios)
    end_time          TEXT,                   -- timestamp_utc + duration_secs (para consultas por rango)

    -- Geolocalización
    latitude          REAL,                   -- latitud (WGS84)
    longitude         REAL,                   -- longitud (WGS84)
    altitude          REAL,                   -- altitud en metros
    geolocation_source TEXT,                  -- 'metadata', 'inferido_tiempo', 'track_gps', 'manual'

    -- Geocodificación inversa (GPS → localidad/provincia)
    -- Jerarquía: provincia > municipio > localidad
    provincia         TEXT,                   -- provincia argentina (ej: "Ciudad Autónoma de Buenos Aires")
    departamento      TEXT,                   -- poco usado en Argentina (equivalente a municipio en algunos casos)
    municipio         TEXT,                   -- municipio (ej: "Tafí Viejo", "Luján de Cuyo")
    localidad         TEXT,                   -- localidad/ciudad (ej: "El Mollar", "La Banda")
    geocode_source    TEXT,                   -- 'georef_api', 'georef_offline', 'gazetteer', 'manual'
    geocode_date      TEXT,                   -- timestamp ISO de la geocodificación

    -- Gradientes / esfuerzo físico (calculado post-ingesta por scripts/gradiente.py)
    distance_from_prev_m  REAL,               -- distancia horizontal desde el medio anterior (Haversine, metros)
    elevation_gain_m      REAL,               -- cambio de elevación desde el medio anterior (+ subida, - bajada)
    gradient_pct          REAL,               -- pendiente porcentual = (elevation_gain / distance) * 100
    cumul_distance_m      REAL,               -- distancia acumulada desde el inicio del viaje (metros)
    cumul_elevation_gain_m REAL,              -- ganancia de elevación acumulada (metros)

    -- Astronomía / posición del sol (calculado post-ingesta por scripts/astronomia.py)
    sun_elevation         REAL,               -- altura del sol sobre el horizonte (grados, -90 a +90)
    sun_azimuth           REAL,               -- dirección del sol (grados, 0°=N, 90°=E)
    sun_distance_au       REAL,               -- distancia al sol en unidades astronómicas (~1.0)
    twilight_period       TEXT,               -- 'dia', 'golden_hour', 'blue_hour', 'crepuculo_civil', 
                                              -- 'crepuculo_nautico', 'crepuculo_astronomico', 'noche'
    sunrise_ts            TEXT,               -- hora UTC del amanecer (ISO 8601)
    sunset_ts             TEXT,               -- hora UTC del atardecer (ISO 8601)
    solar_noon_ts         TEXT,               -- hora UTC del cenit solar (ISO 8601)
    secs_since_sunrise    REAL,               -- segundos desde el amanecer (+ despues, - antes)
    secs_to_sunset        REAL,               -- segundos hasta el atardecer (+ antes, - despues)
    secs_since_noon       REAL,               -- segundos desde el cenit (+ tarde, - mañana)
    astronomy_source      TEXT,               -- 'noaa_calculator', 'manual'

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
    updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
    ingest_batch_id   INTEGER                 -- ID de la corrida de ingesta (para undo)
);

CREATE TABLE IF NOT EXISTS media_metadata (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    key      TEXT NOT NULL,
    value    TEXT,
    UNIQUE(media_id, key)
);

CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Keypoints: puntos de interés dentro de un medio continuo (video/audio)
CREATE TABLE IF NOT EXISTS media_keypoints (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id              INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    timestamp_offset_secs REAL NOT NULL,           -- offset desde el inicio del medio (segundos)
    timestamp_absolute    TEXT NOT NULL,            -- timestamp_utc + offset (para consulta por rango)
    key                   TEXT NOT NULL DEFAULT 'transcription',  -- 'transcription', 'scene_change', etc.
    value                 TEXT,                     -- contenido (texto de transcripción, descripción, etc.)
    source                TEXT DEFAULT 'whisper'    -- 'whisper', 'ollama', 'manual'
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_media_content_hash ON media(content_hash);
CREATE INDEX IF NOT EXISTS idx_media_type ON media(type);
CREATE INDEX IF NOT EXISTS idx_media_carpeta ON media(carpeta);
CREATE INDEX IF NOT EXISTS idx_media_timestamp_utc ON media(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_media_end_time ON media(end_time);
CREATE INDEX IF NOT EXISTS idx_media_latlon ON media(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_media_gps_time ON media(latitude, timestamp_utc) WHERE latitude IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_media_ingest_batch ON media(ingest_batch_id);
CREATE INDEX IF NOT EXISTS idx_metadata_key ON media_metadata(key);
CREATE INDEX IF NOT EXISTS idx_kp_absolute ON media_keypoints(timestamp_absolute);
CREATE INDEX IF NOT EXISTS idx_kp_media ON media_keypoints(media_id);
CREATE INDEX IF NOT EXISTS idx_kp_key ON media_keypoints(key);

-- ------------------------------------------------------------------------
-- Embeddings: vectores para búsqueda semántica
-- ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_embeddings (
    media_id    INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    embedding   BLOB NOT NULL,
    modelo      TEXT NOT NULL DEFAULT 'nomic-embed-text',
    fecha       TEXT DEFAULT (datetime('now')),
    UNIQUE(media_id, modelo)
);

CREATE INDEX IF NOT EXISTS idx_emb_media ON media_embeddings(media_id);

-- ------------------------------------------------------------------------
-- Tracks GPS: archivos GPX ingestados (rutas completas)
-- ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tracks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,             -- nombre del track (del GPX)
    filepath_absoluto TEXT NOT NULL,             -- ruta absoluta al archivo GPX
    filepath_relativo TEXT NOT NULL,             -- ruta relativa al proyecto
    source_url        TEXT,                      -- URL de origen (RideWithGPS, Strava, etc.)
    start_time        TEXT,                      -- timestamp del primer punto
    end_time          TEXT,                      -- timestamp del último punto
    total_points      INTEGER,                   -- cantidad de track points
    ingested_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ------------------------------------------------------------------------
-- Waypoints: puntos de interés extraídos de GPX u otras fuentes
-- ------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS waypoints (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id          INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    name              TEXT NOT NULL,             -- nombre del waypoint
    description       TEXT,                      -- descripción textual
    category          TEXT,                      -- cmt: bikeshare, stop, caution, food, etc.
    type              TEXT,                      -- type: checkpoint, service, danger, food, etc.
    latitude          REAL NOT NULL,             -- WGS84
    longitude         REAL NOT NULL,             -- WGS84
    timestamp         TEXT,                      -- si tiene timestamp asociado
    ingested_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_waypoints_loc ON waypoints(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_waypoints_track ON waypoints(track_id);
CREATE INDEX IF NOT EXISTS idx_waypoints_type ON waypoints(type);
CREATE INDEX IF NOT EXISTS idx_tracks_start ON tracks(start_time);
