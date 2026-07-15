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

**Ventajas:**
- Sin API key, sin registro, sin rate limit observable
- Devuelve: provincia + departamento + municipio + localidad exactos
- Datos oficiales (misma fuente que el INDEC)
- ~7.5 segundos para 5000 coordenadas (50 requests batch de 100)
- Solo usa `urllib` (no requiere `pip install`)

**Desventajas:**
- Requiere internet
- Depende de un servicio público externo

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
    │  provincia+local │             └────────────┬─────────────┘
    │  datos oficiales │                          │
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
| Localidad | ✅ Exacta (INDEC, 14k+ asentamientos) | ⚠️ ADM3 o ADM2 |
| Zonas rurales | ✅ Sí (cubre asentamientos BAHRA) | ⚠️ Puede no cubrir |
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
- `localidad`
- `geocode_source` (origen: `georef_api`, `georef_offline`, `gazetteer`)
- `geocode_date` (timestamp de la consulta)

Esto evita tener que volver a consultar coordenadas ya resueltas.

---

## Recursos

- [API Georef Argentina — documentación](https://datosgobar.github.io/georef-api/)
- [Georef — datasets descargables](https://datos.gob.ar/dataset/ign-georef)
- [python-gazetteer — PyPI](https://pypi.org/project/python-gazetteer/)
- [python-gazetteer — GitHub](https://github.com/SOORAJTS2001/gazetteer)
- [Geoboundaries](https://www.geoboundaries.org/)
