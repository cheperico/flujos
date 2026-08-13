# web3 — Prototipo web de visualización

> **⚠️ Estado: PROTOTIPO (iteración de la serie webN).**
> `web3/` es la **3ª prueba** de la visualización web; NINGÚN nombre `webN` es el
> definitivo. Es una serie de **prototipos iterativos/experimentales**: puede haber
> `web4`, `web5`, … hasta dar con un **modelo adecuado**. Cuando eso pase, el
> proyecto será **una sola** web (sin sufijo de versión). Tratar cualquier
> referencia a `webN/` como una experimentación, no como un componente definitivo.
> Este archivo documenta el `web3` actual; cada iteración nueva debería tener su
> propia doc bajo el mismo patrón (p. ej. `docs/web4.md`) o reemplazar esta si
> la hace obsoleta.

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
web3/
├── index.html                 # Página "Lienzo" (SPA)
├── prueba_loop.html           # Reproductor de prueba del motor de loop
├── .htaccess                  # Seguridad Apache (protege .db/.json/.md/.py)
├── spec.json                  # Spec compilada del motor de loop (generada)
├── includes/
│   └── db.php                 # Conexión PDO a web3/db/visualizacion.db
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
```
> El exportador es **genérico** (sirve a cualquier implementación web, no solo
> web3) y vive en `scripts/exportar_visualizacion.py` (fuera de `web3/`). El
> deploy por defecto escribe en `deploy/` en la raíz del proyecto; el modo
> `--snapshot-local` escribe `web3/db/visualizacion.db` (dev web3 sin copiar
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
   - **Snapshot local (dev web3)**: `--snapshot-local` escribe
     `web3/db/visualizacion.db` con rutas absolutas de Windows, **sin** copiar
     medios ni transcodificar (comportamiento original del prototipo).

2. **Regenerar el spec del motor de loop** (en PowerShell forzar UTF-8 por
   caracteres de caja `─`):
   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida web3/spec.json
   ```
   `loop_db.py` lee `db/flujos.db` (solo lectura), calcula la hora de día de cada
   medio, genera los chiches y produce `spec.json` (portable: web y TouchDesigner).
   Los `--horas` definen los arcos; los del prototipo actual son `7 16 13 18`.

> Al regenerar con los datos limpios (translategemma aplicado en la DB principal)
> se propagan las descripciones ES correctas y los 1522 medios completos a los prototipos
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
> `scripts/puente_td.py` / `scripts/elecciones.py`) las frases se respetan y el
> ruido desaparece. Requiere que el snapshot tenga la columna `keywords`
> (agregada al exportador).
| `recorrido.php` | — | `{total, puntos, colores}` (colores = UNION de color_1..3) |
| `puntos.php` | — | `{total, puntos}` (embeddings) — **hoy 0 puntos** |
| `mensajes_telegram.php` | `municipio` (obligatorio), `limite` (def 200), `fotos` (bool) | `{total, rango, mensajes + fotos JSON}` |
| `loop.php` | — | Contenido crudo de `web3/spec.json` (503 si falta) |

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

Cualquier Apache con PHP (PDO SQLite) apuntando a `web3/`. El `.htaccess`:
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
- Este prototipo web es un **renderizador alternativo** a TouchDesigner
  (ver `docs/motor_loop.md`); no reemplaza el pipeline.