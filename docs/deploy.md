# deploy — Visualización web

> **Estado: web consolidada en `deploy/`.**
> La serie de prototipos `webN` terminó en la 3ª prueba iterativa; su
> contenido se movió a `deploy/`, que es ahora **la** ubicación definitiva de la
> visualización web (sin sufijo de versión). `deploy/` es a la vez la **fuente**
> del sitio (HTML/PHP/JS versionados en git) y el **destino** del exportador
> (medios copiados, snapshot `visualizacion.db` y `spec.json` generados —
> ignorados por git).

## Propósito

Desde el pipeline Python (SQLite) → la **instalación** (TouchDesigner), esta capa
web es un **renderizador alternativo / prototipo** del motor de loop y del
lienzo explorable. Consume un **snapshot exportado** de la DB principal, NO la
DB real del pipeline — es un snapshot desacoplado para la web.

- Lienzo interactivo (`index.html` + `app.js`): bloques en coordenadas mundo,
  paletas por hora, nube de tags, slideshow de medios, mensajes Telegram.
- Reproductor del loop (`prueba_loop.html`): valida `spec.json` sin TouchDesigner.
- 7 endpoints PHP que sirven el snapshot (`visualizacion.db`) a la SPA.

---

## Estructura

```
deploy/
├── index.html                 # Página "Lienzo" (SPA)
├── prueba_loop.html           # Reproductor de prueba del motor de loop
├── .htaccess                  # Seguridad Apache (protege .db/.json/.md/.py)
├── spec.json                  # Spec compilada del motor de loop (generada)
├── includes/
│   └── db.php                 # Conexión PDO a deploy/db/visualizacion.db
├── api/                       # 7 endpoints JSON
│   ├── medios_filtrados.php   # Medios con filtros (municipio/color/provincia/tipo)
│   ├── servir_medio.php       # Archivo binario del medio (con thumbnails GD)
│   ├── tags.php               # Nube de tags desde keywords (ia_keywords), no descripciones
│   ├── recorrido.php          # Puntos + colores del recorrido
│   ├── puntos.php             # Embeddings del lienzo (⚠️ hoy vacío, ver "Gaps")
│   ├── mensajes_telegram.php   # Mensajes de Telegram de un municipio
│   └── loop.php               # Sirve spec.json en crudo
├── css/estilos.css
├── js/app.js                   # Lógica del lienzo (bloques, paletas, FLOW)
├── db/visualizacion.db         # SNAPSHOT exportado (generado, no versionar)
├── media/                      # Medios copiados por el deploy (generado)
```
> El exportador es **genérico** (sirve a cualquier implementación web, no solo
> esta) y vive en `scripts/exportar_visualizacion.py` (fuera de `deploy/`). El
> deploy por defecto escribe en `deploy/` en la raíz del proyecto; el modo
> `--snapshot-local` escribe `deploy/db/visualizacion.db` (dev local sin copiar
> medios).

---

## Cómo regenerar (2 pasos, tras tocar la DB principal)

El snapshot se genera desde `db/flujos.db` (FUENTE de verdad). Pasos:

1. **Re-exportar el snapshot SQLite**
   ```bash
   python scripts/exportar_visualizacion.py
   ```
   Lee `db/flujos.db` y **recrea** `visualizacion.db` por completo (medios,
   categorias, telegram_messages).
   - **Deploy genérico (default)**: escribe en `deploy/` (raíz del proyecto)
     copiando los medios a `deploy/media/...` y transcodificando videos
     grandes/360° a MP4/H.264 web (por defecto activo; `--no-transcode` solo
     copia). `--deploy-dir <carpeta>` cambia el destino; `--dry-run`
     previsualiza sin escribir.
   - **Snapshot local (dev)**: `--snapshot-local` escribe
     `deploy/db/visualizacion.db` con rutas absolutas de Windows, **sin** copiar
     medios ni transcodificar. ⚠️ Al compartir archivo con el modo deploy, el
     último export gana — para subir a hosting usar siempre el modo deploy.

2. **Regenerar el spec del motor de loop** (en PowerShell forzar UTF-8 por
   caracteres de caja `─`):
   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida deploy/spec.json
   ```
   `loop_db.py` lee `db/flujos.db` (solo lectura), calcula la hora de día de cada
   medio, genera los chiches y produce `spec.json` (portable: web y TouchDesigner).
   Los `--horas` definen los arcos; los del prototipo actual son `7 16 13 18`.

> Al regenerar con los datos limpios (translategemma aplicado en la DB principal)
> se propagan las descripciones ES correctas y los 1522 medios completos a la web
> — verificable: 0 medias con `"!!!!"`, 0 con tailandés.

---

## Endpoints API (todos contra el snapshot, NO contra el pipeline `db/flujos.db`)

| Endpoint | Recibe (GET) | Devuelve |
|---|---|---|
| `medios_filtrados.php` | `limite` (1–20), `tipo` (csv), `municipio`, `color`, `provincia` | resultados agrupados por tipo |
| `servir_medio.php` | `id` (obligatorio), `thumb` (opcional) | archivo binario (MIME, cache 86400 s) |
| `tags.php` | `limite` (10–100, default 40) | `{total, tags:[{tag, frecuencia, peso}]}` |

> **Nota — nube de tags**: `tags.php` arma la nube contando las **keywords**
> (`ia_keywords` → columna `keywords` del snapshot), **no** las descripciones.
> Originalmente tokenizaba `ia_description` en bruto, lo que inyectaba ruido de
> redacción de la IA ("sugiere", "indica", "entorno", "general") y recortaba las
> frases compuestas ("entorno rural", "general mendoza"). Al contar keywords
> completas + filtro `KEYWORDS_A_IGNORAR` (mismo criterio que
> `scripts/td/puente_td.py` / `scripts/td/elecciones.py`) las frases se respetan y el
> ruido desaparece. Requiere que el snapshot tenga la columna `keywords`
> (agregada al exportador).
| `recorrido.php` | — | `{total, puntos, colores}` (colores = UNION de color_1..3) |
| `puntos.php` | — | `{total, puntos}` (embeddings) — **hoy 0 puntos** |
| `mensajes_telegram.php` | `municipio` (obligatorio), `limite` (def 200), `fotos` (bool) | `{total, rango, mensajes + fotos JSON}` |
| `loop.php` | — | Contenido crudo de `deploy/spec.json` (503 si falta) |

---

## Gaps y pendientes conocidos

- **`puntos.php` devuelve 0**: `visualizacion.db.medios.embedding_x/embedding_y/cluster`
  quedan como placeholder (el exportador los prevé pero **nunca los puebla**). La
  generación de embeddings está en `generate_embeddings.py` y el modelo `nomic-embed-text`;
  no se volcaron a 2 dims en el snapshot.
- **`medio_categoria` vacío**: tabla puente creada pero sin uso.
- **El snapshot de la web** está desincronizado del pipeline hasta re-exportar
  (ver "Cómo regenerar"). Fuera de sincronía, la web muestra datos viejos/basura
  (p. ej. descripciones pre-translategemma).
- **`descripcion`** de todos los medios en el snapshot depende de `ia_description`
  (clave `ia_description` de `media_metadata` en la principal).

---

## Servir

Cualquier Apache con PHP (PDO SQLite) apuntando a `deploy/`. El `.htaccess`:
- `Options -Indexes`
- Deniega `.db|sqlite|sqlite3|json` (protege `visualizacion.db` y `spec.json`)
- Deniega `.htaccess|htpasswd|md|py|sh`
El snapshot y el spec son lo único que se sirve (vía PHP), los fuentes `.py/.md`
quedan fuera de alcance por HTTP.

---

## Notas de diseño

- La estructura de bloques, paletas horarias, colocación aleatoria y botón "Fluir"
  están documentadas en `docs/visualizaciones.md` (sesión 28 Jul 2026).
- El spec del motor (segmentos, arcos, chiches) en `docs/motor_loop.md`.
- Esta web es un **renderizador alternativo** a TouchDesigner
  (ver `docs/motor_loop.md`); no reemplaza el pipeline.
