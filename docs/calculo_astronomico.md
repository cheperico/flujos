# Cálculo Astronómico — Sol y Luna

## Objetivo

Enriquecer la base de datos con información astronómica para cada registro geolocalizado:
- **Posición del sol**: elevación (altura sobre horizonte) y azimut (dirección, 0°=N)
- **Posición de la luna**: elevación, azimut, fase, iluminación
- **Eventos solares**: salida, puesta, twilight (crepúsculo civil/náutico/astronómico)
- **Clasificación temporal**: golden hour, blue hour, día, noche

---

## Opciones evaluadas

### 1. Astral (librería Python)

| Aspecto | Detalle |
|---------|---------|
| **Instalación** | `pip install astral` (~200KB, 0 deps) |
| **Qué hace** | Sol/luna, salida/puesta, twilight, fase lunar |
| **API** | `LocationInfo()`, `sun()`, `moon_phase()` |
| **Precisión** | ~0.5° (suficiente para visual) |
| **Dependencias** | Ninguna extra |
| **Pros** | Simple, rápida, bien documentada |
| **Contras** | No da posición lunar detallada (solo fase) |

### 2. Skyfield (librería Python)

| Aspecto | Detalle |
|---------|---------|
| **Instalación** | `pip install skyfield` (~5MB + efemérides JPL DE421 ~18MB) |
| **Qué hace** | Astronomía de precisión: sol, luna, planetas, estrellas |
| **API** | `load()`, `Earth()`, `ephem.SSB`, `Elevation()` |
| **Precisión** | ~0.001° (nivel JPL) |
| **Dependencias** | numpy |
| **Pros** | Extremadamente precisa, datos JPL oficiales |
| **Contras** | Dependencia pesada (numpy + efemérides), más lenta |

### 3. PyEphem (librería Python)

| Aspecto | Detalle |
|---------|---------|
| **Instalación** | `pip install ephem` (~1MB) |
| **Qué hace** | Clásica de astronomía: sol, luna, planetas, fases |
| **API** | `Observer()`, `Sun()`, `Moon()`, `.alt`, `.az` |
| **Precisión** | ~0.01° |
| **Dependencias** | C extension (compilar) |
| **Pros** | Rápida, precisa, muy completa |
| **Contras** | Requiere compilación C en algunos sistemas |

### 4. NOAA Solar Calculator (Python puro)

| Aspecto | Detalle |
|---------|---------|
| **Instalación** | **Ninguna** — Python estándar |
| **Qué hace** | Posición del sol (elevación, azimut), sunrise/sunset |
| **Algoritmo** | NOAA Solar Calculator (2017) |
| **Precisión** | ~0.01° (suficiente para cualquier uso visual) |
| **Dependencias** | **Ninguna** — solo `math` |
| **Pros** | Cero dependencias, rápido, portátil, exacto |
| **Contras** | Solo sol (no luna), hay que implementar twilight |

### 5. Open-Meteo (API HTTP)

| Aspecto | Detalle |
|---------|---------|
| **Instalación** | Ninguna (API HTTP) |
| **Qué hace** | Sunrise/sunset, moonrise/moonset, moon_phase |
| **Endpoint** | `https://api.open-meteo.com/v1/forecast` |
| **Precisión** | ~1 minuto (evento), ~5% (fase lunar) |
| **Dependencias** | requests (ya instalado) |
| **Pros** | Gratis, sin API key, ya usado en el proyecto |
| **Contras** | Solo eventos (no posición), limitado a 16 días forecast, requiere HTTP |

---

## Decisión: NOAA puro + Open-Meteo para luna

| Componente | Fuente | Por qué |
|------------|--------|---------|
| **Posición del sol** | NOAA Solar Calculator | Python puro, cero deps, preciso |
| **Sunrise/sunset** | NOAA Solar Calculator | Ya calculado en el paso anterior |
| **Twilight periods** | NOAA Solar Calculator | Derivado de elevación del sol |
| **Fase lunar** | Open-Meteo (ya usado) | Gratis, sin key, ya integrado |
| **Moonrise/moonset** | Open-Meteo (ya usado) | Gratis, sin key, ya integrado |
| **Moon illumination** | Open-Meteo (ya usado) | Gratis, sin key, ya integrado |

**Razón**: NOAA puro = cero dependencias nuevas. Open-Meteo = ya está en el stack para clima.

---

## Algoritmo NOAA — Detalle técnico

Fuente: NOAA Solar Calculator (https://gml.noaa.gov/grad/solcalc/)

### Inputs
- `lat` (grados decimales, negativo = sur)
- `lon` (grados decimales, negativo = oeste)
- `dt_utc` (datetime aware en UTC)

### Paso 1: Día juliano
```
JD = 367*A - INT(7*(A+INT((M+9)/12))/4) + INT(275*M/9) + D + 1721013.5
```

### Paso 2: Medio siglo juliano
```
T = (JD - 2451545.0) / 36525.0
```

### Paso 3: Coordenadas eclípticas del sol
```
L0 = 280.46646 + T*(36000.76983 + 0.0003032*T)  [longitud eclíptica]
M  = 357.52911 + T*(35999.05029 - 0.0001537*T)  [anomalía media]
C  = (1.914602 - 0.004817*T) * sin(M)            [ecuación del centro]
   + (0.019993 - 0.000101*T) * sin(2M)
   + 0.000289 * sin(3M)
```

### Paso 4: Longitud eclíptica del sol
```
θ = L0 + C
```

### Paso 5: Oblicuidad de la eclíptica
```
ε = 23.439291 - 0.0130042*T
```

### Paso 6: Ascensión recta y declinación
```
α = atan2(cos(ε)*sin(θ), cos(θ))
δ = asin(sin(ε)*sin(θ))
```

### Paso 7: Ángulo horario local
```
GMST = (280.46061837 + 360.98564736629*(JD-2451545.0)) mod 360
H = (GMST + lon - α) mod 360
if H > 180: H -= 360
```

### Paso 8: Elevación y azimut
```
elev = asin(sin(lat)*sin(δ) + cos(lat)*cos(δ)*cos(H))
azim = atan2(-cos(δ)*sin(H), sin(δ)*cos(lat) - cos(δ)*sin(lat)*cos(H))
```

### Paso 9: Clasificación del momento
```
elev >= 12°  → "día"
elev 6°-12°  → "golden_hour"
elev 0°-6°   → "blue_hour"
elev -6°-0°  → "crepuculo_civil"
elev -12°-6° → "crepuculo_nautico"
elev -18°-12°→ "crepuculo_astronomico"
elev < -18°  → "noche"
```

---

## Columnas en la BD

### Tabla `media` (nuevas columnas)

```sql
-- Astronomía / posición del sol (calculado por scripts/astronomia.py)
sun_elevation       REAL,       -- altura del sol sobre horizonte (grados, -90 a +90)
sun_azimuth         REAL,       -- dirección del sol (grados, 0°=N, 90°=E)
sun_distance_au     REAL,       -- distancia al sol en UA (1.0 = promedio)
twilight_period     TEXT,       -- 'dia', 'golden_hour', 'blue_hour',
                                -- 'crepuculo_civil', 'crepuculo_nautico',
                                -- 'crepuculo_astronomico', 'noche'
sunrise_ts          TEXT,       -- hora UTC del amanecer (ISO 8601)
sunset_ts           TEXT,       -- hora UTC del atardecer (ISO 8601)
solar_noon_ts       TEXT,       -- hora UTC del cenit solar (ISO 8601)
secs_since_sunrise  REAL,       -- segundos desde el amanecer (+ si ya salio, - si aun no)
secs_to_sunset      REAL,       -- segundos hasta el atardecer (+ si aun no, - si ya paso)
secs_since_noon     REAL,       -- segundos desde el cenit (+ si es tarde, - si es maniana)
astronomy_source    TEXT,       -- 'noaa_calculator', 'open_meteo', 'manual'
```

### Tabla `media_metadata` (nuevas claves)

```sql
-- Datos de Open-Meteo (agregados en fetch_weather.py)
sunrise_time        TEXT,       -- hora de salida del sol (ISO 8601)
sunset_time         TEXT,       -- hora de puesta del sol (ISO 8601)
moonrise_time       TEXT,       -- hora de salida de la luna
moonset_time        TEXT,       -- hora de puesta de la luna
moon_phase          REAL,       -- fase lunar (0=new, 0.5=full)
moon_illumination   REAL,       -- iluminación lunar (0-100%)
```

---

## Uso en TouchDesigner

### Detección de momento del día
```python
# Desde TD, consultar DB
elev = query_result["sun_elevation"]
if elev >= 12:
    # Modo día: colores vivos, alto contraste
elif elev >= 6:
    # Golden hour: filtro cálido, saturación alta
elif elev >= 0:
    # Blue hour: filtro frío, tonos azules
else:
    # Noche: bajos brillos, ruido, sombras
```

### Dirección de la luz
```python
azim = query_result["sun_azimuth"]
# Si la cámara apunta hacia el sol: contraluz, flares
# Si la cámara apunta al sol: siluetas
```

### Luna como fuente de luz nocturna
```python
illum = query_result["moon_illumination"]
if illum > 50:
    # Luna llena: escena iluminada, sombras definidas
elif illum > 10:
    # Luna creciente: luz tenue
else:
    # Luna nueva: oscuridad total
```

---

## Scripts relacionados

| Script | Función |
|--------|---------|
| `scripts/astronomia.py` | Calcula posición del sol (NOAA) y clasifica twilight |
| `scripts/fetch_weather.py` | Agrega sunrise/sunset, moonrise/moonset, moon_phase de Open-Meteo |

---

## Referencias

- NOAA Solar Calculator: https://gml.noaa.gov/grad/solcalc/
- Astral (Python): https://astral.readthedocs.io/
- Skyfield: https://rhodesmill.org/skyfield/
- Open-Meteo API: https://open-meteo.com/
