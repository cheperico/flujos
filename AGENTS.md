# Flujos

Proyecto de **instalación interactiva**. Procesamiento, gestión y flujo de
medios audiovisuales (video, imágenes, audio, texto) con TouchDesigner como
motor principal.

## Stack

- **Motor**: TouchDesigner
- **Medios**: Video, imágenes, audio, texto (múltiples orígenes)
- **Base de datos**: SQLite (metadatos y configuración)
- **Procesamiento**: ffmpeg, ExifTool, Python
- **Lenguaje scripting**: Python (Pillow, mutagen, etc.)

## Estructura

```
/
├── opencode.json              # Configuración del proyecto
├── AGENTS.md                  # Este archivo
└── .opencode/
    ├── agents/                # Agentes y subagentes
    │   ├── orquestador.md     # Agente primario (orquestador)
    │   └── touchdesigner.md   # Subagente TouchDesigner
    └── skills/                # Skills reutilizables
        ├── sqlite/
        │   └── SKILL.md       # Base de datos SQLite
        ├── ffmpeg/
        │   └── SKILL.md       # Transcodificación y análisis
        ├── exiftools/
        │   └── SKILL.md       # Metadatos EXIF/IPTC/XMP
        └── python-media/
            └── SKILL.md       # Python para multimedia
```

## Agentes

| Agente | Tipo | Rol |
|--------|------|-----|
| `@orquestador` | primary | Orquestador principal — planea, delega, sintetiza |
| `@touchdesigner` | subagent | Experto en TouchDesigner — operadores, redes, Python/TD, OSC, MIDI, NDI, Spout |

## Skills

| Skill | Descripción |
|-------|-------------|
| `sqlite` | Base de datos embebida para metadatos de medios, configuración y almacenamiento local |
| `ffmpeg` | Transcodificación, análisis y extracción de metadata de archivos multimedia |
| `exiftools` | Lectura de metadatos EXIF, IPTC, XMP en imágenes, videos y audios |
| `python-media` | Scripting Python para procesamiento, ETL y automatización de pipelines de medios |

## Reglas

- Idioma principal: español
- El orquestador delega en subagentes, no implementa directamente
- Los skills se editan y ajustan según evoluciona el proyecto
