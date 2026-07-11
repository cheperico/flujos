---
name: sqlite
description: SQLite — base de datos embebida para metadatos de medios, configuración y almacenamiento local. Creación de esquemas, consultas, migraciones y optimización.
---

# Skill: SQLite para medios

## Alcance
Este skill cubre el uso de SQLite en el contexto del proyecto **Flujos**:
base de datos de metadatos de archivos multimedia, configuración del proyecto
y almacenamiento local de estados.

## Operaciones principales

### 1. Crear / abrir base
```python
import sqlite3
conn = sqlite3.connect("ruta/al/flujos.db")
conn.row_factory = sqlite3.Row
```

### 2. Esquema sugerido para metadatos de medios
```sql
CREATE TABLE IF NOT EXISTS medios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    archivo TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL,                -- 'video', 'imagen', 'audio', 'texto'
    sha256 TEXT,
    tamano_bytes INTEGER,
    -- metadatos generales
    fecha_creacion TEXT,
    fecha_modificacion TEXT,
    -- video / audio
    duracion_seg REAL,
    codec TEXT,
    bitrate INTEGER,
    -- video
    resolucion_ancho INTEGER,
    resolucion_alto INTEGER,
    fps REAL,
    -- imagen
    exif_camara TEXT,
    exif_lente TEXT,
    exif_iso INTEGER,
    exif_apertura TEXT,
    exif_velocidad TEXT,
    exif_fecha_disparo TEXT,
    exif_geolocalizacion TEXT,        -- "lat,lng"
    iptc_palabras_clave TEXT,         -- JSON array
    iptc_descripcion TEXT,
    iptc_autor TEXT,
    -- audio
    canales INTEGER,
    sample_rate INTEGER,
    -- estado
    procesado INTEGER DEFAULT 0,
    fecha_ingreso TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_medios_tipo ON medios(tipo);
CREATE INDEX idx_medios_archivo ON medios(archivo);
CREATE INDEX idx_medios_procesado ON medios(procesado);
```

### 3. Consultas típicas
```python
# Todos los videos de más de 30 seg
cur.execute("SELECT * FROM medios WHERE tipo='video' AND duracion_seg > 30")

# Imágenes con geolocalización
cur.execute("SELECT * FROM medios WHERE tipo='imagen' AND exif_geolocalizacion IS NOT NULL")

# Medios no procesados aún
cur.execute("SELECT * FROM medios WHERE procesado=0")

# Búsqueda por palabras clave IPTC
cur.execute("SELECT * FROM medios WHERE iptc_palabras_clave LIKE ?", ('%"naturaleza"%',))
```

### 4. Inserción / actualización
```python
# Insertar o ignorar si ya existe
cur.execute("""
    INSERT OR IGNORE INTO medios (archivo, tipo, sha256, tamano_bytes, fecha_creacion)
    VALUES (?, ?, ?, ?, ?)
""", (archivo, tipo, sha256, tamano, f_creacion))

# Marcar como procesado
cur.execute("UPDATE medios SET procesado=1 WHERE archivo=?", (archivo,))
```

### 5. Migraciones
Usar tabla `_migraciones` para trackear cambios de esquema:
```sql
CREATE TABLE IF NOT EXISTS _migraciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT UNIQUE,
    aplicada_en TEXT DEFAULT (datetime('now'))
);
```

## Buenas prácticas
- Usar `WAL` mode para mejor concurrencia: `PRAGMA journal_mode=WAL;`
- Usar `BEGIN TRANSACTION` / `COMMIT` para inserciones batch
- No almacenar archivos binarios grandes en SQLite (guardar path)
- Normalizar metadatos repetitivos (ej: tabla separada de palabras clave)
- Hacer backup periódico de `flujos.db`
