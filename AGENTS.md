# Flujos

Proyecto de **instalación interactiva**. Procesamiento, gestión y flujo de
medios audiovisuales (video, imágenes, audio, texto) con TouchDesigner como
motor principal.

## Stack

- **Motor**: TouchDesigner
- **Medios**: Video, imágenes, audio, texto (múltiples orígenes)
- **Base de datos**: SQLite (metadatos y configuración)
- **Procesamiento**: ffmpeg, ExifTool, Python
- **Lenguaje scripting**: Python (Pillow, mutagen, faster-whisper, etc.)

## Herramientas del sistema

| Herramienta | Versión | Ruta / comando |
|-------------|---------|----------------|
| **Python** | 3.13.14 | `python` |
| **ffmpeg** | 8.1.2 (full build) | `ffmpeg`, `ffprobe` |
| **ExifTool** | 13.59 | `exiftool` |
| **Ollama** | 0.31.2 | `ollama` (servicio en segundo plano) |
| **faster-whisper** | 1.2.1 | `faster_whisper` (Python) |

### Modelos Ollama disponibles

| Modelo | Tamaño | Uso |
|--------|--------|-----|
| `qwen2.5vl:latest` | 6.0 GB | Visión + lenguaje (imágenes) |
| `qwen2.5vl:3b` | 3.2 GB | Visión + lenguaje (liviano) |
| `llama3.2-vision:latest` | 7.8 GB | Análisis visual |
| `moondream:latest` | 1.7 GB | Visión rápido y pequeño |
| `gemma4:e4b` | 9.6 GB | Multimodal |
| `qwen3.5:9b` / `qwen3.5:4b` | 6.6 / 3.4 GB | Texto / análisis |
| `deepseek-r1:latest` | 5.2 GB | Razonamiento |
| `llama3.1:8b` / `llama3.2:3b` | 4.9 / 2.0 GB | Propósito general |
| `deepseek-coder-v2:16b` | 8.9 GB | Código |
| `qwen3-coder:latest` | 18 GB | Código (grande) |
| `nomic-embed-text` / `-v2-moe` | 274 / 957 MB | Embeddings / búsquedas semánticas |

## Estructura

```
/
├── opencode.json              # Configuración del proyecto
├── AGENTS.md                  # Este archivo
└── .opencode/
    ├── agents/                # Agentes y subagentes
    │   ├── orquestador.md     # Agente primario (orquestador)
    │   ├── touchdesigner.md   # Subagente TouchDesigner
    │   ├── gis.md             # Subagente GIS
    │   ├── gis.md             # Subagente GIS
    │   └── ia-media.md        # Subagente IA para medios
    └── skills/                # Skills reutilizables
        ├── sqlite/
        │   └── SKILL.md       # Base de datos SQLite
        ├── ffmpeg/
        │   └── SKILL.md       # Transcodificación y análisis
        ├── exiftools/
        │   └── SKILL.md       # Metadatos EXIF/IPTC/XMP
        ├── ia-media/
        │   └── SKILL.md       # Procesamiento de medios con IA
        └── python-media/
        │   └── SKILL.md       # Python para multimedia
        └── ia-media/
            └── SKILL.md       # Procesamiento de medios con IA
```

## Scripts (Python)

```
scripts/
├── __init__.py                # Paquete raíz
├── ai_media/                  # Procesamiento con IA
│   ├── __init__.py
│   ├── ollama_client.py       # Cliente Ollama (visión + texto)
│   ├── transcribe.py          # Transcripción audio (faster-whisper)
│   ├── image_analysis.py      # Keywords y descripción de imágenes
│   ├── video_analysis.py      # Keywords y descripción de videos
│   └── batch_selector.py      # Selección de mejor imagen de tanda
├── ingest.py                  # Ingesta de medios
├── check_db.py               # Verificación BD
├── check_gps.py              # Verificación GPS
├── color_utils.py            # Utilidades de color
└── query.py                  # Consultas a BD
```

## Agentes

| Agente | Tipo | Rol |
|--------|------|-----|
| `@orquestador` | primary (default) | Orquestador principal — agente predeterminado para todas las sesiones |
| `@touchdesigner` | subagent | Experto en TouchDesigner — operadores, redes, Python/TD, OSC, MIDI, NDI, Spout |
| `@gis` | subagent | Experto en GIS — geolocalización de medios, conversión de coordenadas, cálculos de distancia y ubicación relativa |
| `@ia-media` | subagent | Experto en IA para medios — visión (Ollama), transcripción (faster-whisper), análisis de imágenes y videos, selección inteligente |

## Skills

| Skill | Descripción |
|-------|-------------|
| `sqlite` | Base de datos embebida para metadatos de medios, configuración y almacenamiento local |
| `ffmpeg` | Transcodificación, análisis y extracción de metadata de archivos multimedia |
| `exiftools` | Lectura de metadatos EXIF, IPTC, XMP en imágenes, videos y audios |
| `ia-media` | Procesamiento de medios con IA — transcripción (faster-whisper), análisis de imágenes y videos (Ollama visión), selección inteligente de imágenes |
| `python-media` | Scripting Python para procesamiento, ETL y automatización de pipelines de medios |

## Documentos de diseño

| Documento | Descripción |
|-----------|-------------|
| `docs/limpieza_tandas_resultados.md` | Comparativa de 4 estrategias de limpieza de tandas (temporal, pHash, tags, embeddings). Decantó por embeddings como favorita. |
| `docs/geocodificacion_reversa.md` | Estrategia de geocodificación inversa (GPS → localidad/provincia). 3 opciones: Georef API batch, Georef offline, python-gazetteer. |

## Reglas

- Idioma principal: español
- El orquestador delega en subagentes, no implementa directamente
- Los skills se editan y ajustan según evoluciona el proyecto
