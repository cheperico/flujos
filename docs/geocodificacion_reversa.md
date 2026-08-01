# Estrategia de geocodificación inversa — GPS a localidad/provincia

## Contexto

El proyecto necesita convertir coordenadas GPS (latitud, longitud) —presentes
en metadatos EXIF de fotos y videos— a **localidad y provincia** de Argentina.

**Volumen estimado:** ~5000 coordenadas (puede crecer).

**Requisitos:**
- Gratuito ($0)
- Open source / datos abiertos
- Sin registros ni API keys
- Que funcione desde Python
- Prioridad: Argentina (por ahora)

---

## Opciones evaluadas y descartadas

| Opción | Motivo de descarte |
|--------|-------------------|
| **Nominatim / geopy** | Rate limit de 1 req/s → ~83 min para 5000 coords. Inviable para el volumen. Requiere internet. |
| **reverse-geocode** (richardpenman) | Point-based: no respeta límites administrativos. No devuelve provincia. Da ciudad más cercana, no la que contiene el punto. |
| **reverse_geocoder** (thampiman) | Abandonado desde 2016. Misma limitación point-based que el anterior. |
| **geopandas + shapefile** | Instalación compleja en Windows (GDAL, Fiona). Overkill (~150 MB de dependencias) para lo que necesitamos. |
| **Geoapify / Google / Bing** | Requieren API key y registro. |

---

## Estrategia seleccionada: 3 opciones complementarias

No hay una bala de plata. La mejor cobertura se logra con **tres opciones**
que se complementan según contexto de uso:

| Prioridad | Opción | Tipo | Velocidad (5000 coords) | Precisión AR |
|:---------:|--------|:----:|:-----------------------:|:------------:|
| **A** | **Georef API batch** | Online | **~7.5 seg** ⚡ | Óptima (datos IGN+INDEC) |
| **B** | **Georef offline** (GeoJSON) | Offline | **~2-5 seg** 🚀 | Óptima (mismos datos) |
| **C** | **python-gazetteer** | Offline global | **~1 seg** 🚀 | Alta (boundary-aware, 145K+ boundaries) |

### Opción A — Georef API batch (online)

**¿Qué es?**
API pública del Estado argentino (`apis.datos.gob.ar/georef/api/ubicacion`)
que devuelve datos oficiales de IGN + INDEC.

**Endpoint batch:** acepta hasta 100 coordenadas por request POST.

**⚠️ Qué devuelve realmente:** el endpoint `/api/ubicacion` (georreferencia
inversa) **NO devuelve `localidad`**. Devuelve **solo**:

| Campo | Ejemplo real (Inriville, Córdoba) |
|-------|----------------------------------|
| `provincia` | Córdoba |
| `departamento` | Marcos Juárez |
| `municipio` | Inriville |

Verificado empíricamente (Jul 2026) contra la API:
- `?campos=localidad` → HTTP 400 Bad Request
- `POST` con `campos` en el cuerpo → 400
- `?campos=completo` → solo agrega `fuente` a las entidades, no localidad
- Georef **v2.1** (`/api/v2.1/ubicacion`) → renombra `municipio` → `gobierno_local`,
  pero **tampoco** devuelve `localidad`

La columna `localidad` de la DB queda entonces siempre NULL con esta opción.

**Ventajas:**
- Sin API key, sin registro, sin rate limit observable
- Devuelve: provincia + departamento + municipio exactos (oficiales IGN/INDEC)
- ~7.5 segundos para 5000 coordenadas (50 requests batch de 100)
- Solo usa `urllib` (no requiere `pip install`)

**Desventajas:**
- Requiere internet
- Depende de un servicio público externo
- **No provee localidad** en georreferencia inversa (para eso, ver "Cómo obtener
  localidad" más abajo)

**Métricas reales medidas (desde el entorno del proyecto):**

| Prueba | Tiempo |
|--------|:------:|
| Consulta individual | 34–69 ms (promedio 45 ms) |
| Batch de 10 coords | 86 ms (8.6 ms/coord) |
| Batch de 50 coords | 111 ms (2.2 ms/coord) |
| **Batch de 100 coords** | **125–158 ms (1.3–1.6 ms/coord)** |
| 500 coords (5 batches de 100) | ~1.2 seg (estable ~130 ms/batch) |

### Opción B — Georef offline (GeoJSON descargados)

**¿Qué es?**
Los mismos datos de la API Georef pero descargados como archivos GeoJSON
para operar sin internet.

**Datos disponibles (Georef v2.0):**

| Dataset | GeoJSON | CSV | Features |
|---------|:-------:|:---:|:--------:|
| Provincias | 600 KB | 2 KB | 24 |
| Departamentos | 1.1 MB | 61 KB | 529 |
| Localidades | 1.9 MB | 671 KB | 4.028 |
| Asentamientos (BAHRA) | 6.8 MB | 2.1 MB | 14.466 |
| **Total** | **~10 MB** | | |

**Ventajas:**
- Misma precisión que la API (fuente oficial IGN+INDEC)
- Funciona 100% offline
- Liviano (~10 MB en disco)
- Point-in-polygon con `shapely` (rápido, preciso)

**Desventajas:**
- Solo Argentina (no sirve para otros países)
- Hay que mantener los datos actualizados (descarga manual periódica)

### Opción C — python-gazetteer (offline global)

**¿Qué es?**
Librería Python open source (LGPL v2.1), publicada Dic 2025, muy activa
(último commit Ene 2026). Usa datos de [Geoboundaries](https://www.geoboundaries.org/)
con 145.000+ límites reales de 210+ países.

**Características:**
- **Boundary-aware:** verifica si el punto está DENTRO del polígono, no solo el más cercano
- 3 niveles administrativos: ADM0 (país), ADM1 (provincia/estado), ADM2/ADM3 (ciudad/distrito)
- Usa KDTree (scipy) para nearest-neighbor + validación por polígono desde SQLite
- Modo multiprocesamiento (`Gazetteer(mode=2)`)
- Requiere Python ≥3.12 ✅ (tenemos 3.13.14)

**Ventajas:**
- Precisión alta cerca de fronteras (boundary-aware)
- Global (si en el futuro se usan coordenadas de otros países)
- ~1 segundo para 5000 coordenadas
- Sin límites, sin internet, sin API key

**Desventajas:**
- Dependencias: `scipy`, `shapely`, `pydantic` (~20 MB instalación)
- Consumo de memoria: ~200-500 MB (dataset en SQLite + KDTree)
- Relativamente nuevo (riesgo de cambios de API, comunidad chica: ~163 stars)
- Los datos de Argentina pueden no estar tan actualizados como Georef

---

## Organización territorial de Argentina (contexto necesario)

Para interpretar correctamente lo que devuelve Georef hay que entender cómo se
divide el territorio argentino. Fuente: [Wikipedia — Organización territorial
de Argentina](https://es.wikipedia.org/wiki/Organizaci%C3%B3n_territorial_de_Argentina).

| Nivel | Entidad | Detalle |
|:-----:|---------|---------|
| **1** | 23 **provincias** + CABA | Jurisdicciones de primer orden |
| **2** | **departamentos** (22 provincias), **partidos** (Buenos Aires, 135), **comunas** (CABA, 15) | División catastral/estadística. **Sí se usan en Argentina** (ej: "departamento Marcos Juárez"). No tienen gobierno propio |
| **3** | **municipios** (1.218) + comunas rurales, comisiones de fomento, etc. | Gobierno local (intendente + concejo deliberante). **Dentro de los departamentos hay localidades** que pueden tener municipio propio o no |
| — | **localidades** | Poblados dentro de un departamento. Un municipio puede contener varias localidades; en pueblos chicos municipio ≈ localidad |

**Consecuencia práctica para la DB:**

- `provincia` = "Córdoba" ✅
- `departamento` = "Marcos Juárez" ✅ (división real de segundo nivel)
- `municipio` = "Inriville" ✅ (el gobierno local del pueblo)
- `localidad` = NULL con Georef `/ubicacion` (no lo provee)

La confusión habitual (y de la que hay que cuidarse en el proyecto) es creer
que "localidad" y "municipio" son intercambiables, o que el "departamento" es
un municipio. No lo son: **provincia → departamento → localidad**, y el
municipio es el gobierno local (que en pueblos coincide con la localidad).

---

## Cómo obtener `localidad` si se necesita

La API Georef `/ubicacion` no la da, pero la localidad está disponible por
otras vías dentro del mismo ecosistema Georef:

| Vía | Cómo | Precisión |
|-----|------|-----------|
| **Dataset offline de localidades** | Descargar `localidades.csv` o GeoJSON de [datos.gob.ar — dataset Georef](https://datos.gob.ar/dataset/ign-georef). Point-in-polygon con shapely, o nearest-neighbor con nombre | Exacta (INDEC, 4.028 localidades censales) |
| **Dataset de asentamientos (BAHRA)** | 14.466 asentamientos del INDEC, cubre zonas rurales | Exacta (mejor cobertura rural) |
| **Georef `/api/localidades`** | Busca localidades por **nombre/provincia/departamento**, NO por punto. No sirve para georreferencia inversa directa | — |
| **Nominatim / OSM** | Reverse geocoding con campo `localidad`/`village`/`town`/`city` | Buena, pero rate limit 1 req/s (inviable para 5000 coords) |

**Recomendación:** si la instalación necesita mostrar "localidad" exacta,
la vía oficial es el dataset offline (opción B de este doc) o un post-proceso
con el CSV de localidades INDEC. Para la mayoría de los usos, `municipio`
(Georef) es suficiente y es lo que el proyecto tiene hoy.

---

## Diagrama de decisión

```
                    ┌──────────────────────────────┐
                    │  ¿Hay internet?               │
                    └──────────┬───────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                                 ▼
    ┌──────────────────┐             ┌──────────────────────────┐
    │  A: Georef API   │             │  ¿Solo Argentina o       │
    │  batch (~7.5s)   │             │  potencialmente global?  │
    │  prov+depto+muni │             └────────────┬─────────────┘
    │  (sin localidad) │                          │
    └──────────────────┘              ┌───────────┴───────────┐
                                      ▼                       ▼
                            ┌──────────────────┐   ┌──────────────────────┐
                            │ B: Georef offline│   │ C: python-gazetteer │
                            │ (~2-5s, ~10MB)   │   │ (~1s, 200-500MB)    │
                            │ misma precisión  │   │ global, boundary-    │
                            │ que A, offline   │   │ aware, offline      │
                            └──────────────────┘   └──────────────────────┘
```

---

## Comparativa de precisión para Argentina

| Aspecto | Georef (A/B) | python-gazetteer (C) |
|---------|:------------:|:--------------------:|
| Provincia | ✅ Exacta (fuente IGN) | ✅ ADM1 (Geoboundaries) |
| Departamento | ✅ Exacto | ⚠️ ADM2 cuando existe |
| Localidad | ⚠️ **No vía API `/ubicacion`** (solo con dataset offline) | ⚠️ ADM3 o ADM2 |
| Zonas rurales | ✅ Sí (cubre asentamientos BAHRA offline) | ⚠️ Puede no cubrir |
| Fronteras entre provincias | ✅ Correctas (polígonos IGN) | ✅ Boundary-aware |
| Actualización de datos | ✅ Oficial (continua) | ⚠️ Según releases de Geoboundaries |

---

## Recomendación de implementación

### Fase 1 — Georef API (prioritaria)
Implementar script que use la API batch de Georef. Es la que mejor relación
velocidad/precisión/simplicidad ofrece. Sin dependencias nuevas.

### Fase 2 — Fallback offline
Elegir según necesidades futuras:
- **Solo Argentina** → descargar GeoJSON de Georef (~10 MB) + shapely
- **Potencialmente global** → `pip install python-gazetteer`

Ambas pueden convivir: intentar A, si no hay internet caer en B o C.

### Integración con SQLite
Extender la tabla `media` con columnas para almacenar el resultado de la
geocodificación:
- `provincia`
- `departamento`
- `municipio`
- `localidad` (⚠️ queda NULL con Georef `/ubicacion`; ver "Cómo obtener
  localidad" para fuentes alternativas)
- `geocode_source` (origen: `georef_api`, `georef_offline`, `gazetteer`)
- `geocode_date` (timestamp de la consulta)

Esto evita tener que volver a consultar coordenadas ya resueltas.

---

## Recursos

- [API Georef Argentina — documentación](https://datosgobar.github.io/georef-api/)
- [API Georef — OpenAPI / endpoints](https://datosgobar.github.io/georef-ar-api/open-api)
- [Georef — datasets descargables (localidades, asentamientos)](https://datos.gob.ar/dataset/ign-georef)
- [Organización territorial de Argentina — Wikipedia](https://es.wikipedia.org/wiki/Organizaci%C3%B3n_territorial_de_Argentina)
- [python-gazetteer — PyPI](https://pypi.org/project/python-gazetteer/)
- [python-gazetteer — GitHub](https://github.com/SOORAJTS2001/gazetteer)
- [Geoboundaries](https://www.geoboundaries.org/)
