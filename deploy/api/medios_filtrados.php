<?php
/**
 * Devuelve hasta N medios aleatorios filtrados por municipio/color/provincia/tag/tipo.
 * GET params:
 *   municipio (string, opcional; acepta valores separados por coma)
 *   color     (string, opcional; acepta valores separados por coma)
 *   provincia (string, opcional; acepta valores separados por coma)
 *   tag       (string, opcional; acepta valores separados por coma)
 *   tipo      (string, opcional: image,video,audio,text — separado por coma;
 *              'text' devuelve los medios type='text' (textos del viaje))
 *   limite    (int, opcional, default 20)
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$municipio = isset($_GET['municipio']) ? trim($_GET['municipio']) : '';
$color     = isset($_GET['color'])     ? trim($_GET['color'])     : '';
$provincia = isset($_GET['provincia']) ? trim($_GET['provincia']) : '';
$tag       = isset($_GET['tag'])       ? trim($_GET['tag'])       : '';
$tipoStr   = isset($_GET['tipo'])      ? trim($_GET['tipo'])      : '';
$limite    = isset($_GET['limite'])    ? max(1, min(20, (int)$_GET['limite'])) : 5;

function valores_param($texto) {
    $valores = array_map('trim', explode(',', $texto));
    $valores = array_filter($valores, function($v) { return $v !== ''; });
    return array_values(array_unique($valores));
}

function minusculas_utf8_ligero($texto) {
    $texto = strtr($texto, [
        'Á' => 'á', 'É' => 'é', 'Í' => 'í', 'Ó' => 'ó', 'Ú' => 'ú',
        'Ü' => 'ü', 'Ñ' => 'ñ',
    ]);
    return strtolower($texto);
}

function agregar_in(&$condiciones, &$params, $columna, $prefijo, $valores) {
    if (!count($valores)) return;
    $marcas = [];
    foreach ($valores as $i => $valor) {
        $k = ':' . $prefijo . $i;
        $marcas[] = $k;
        $params[$k] = $valor;
    }
    $condiciones[] = $columna . ' IN (' . implode(',', $marcas) . ')';
}

// Construir WHERE dinámico
$condiciones = [];
$params = [];

$municipios = valores_param($municipio);
$colores = valores_param($color);
$provincias = valores_param($provincia);
$tags = valores_param($tag);

agregar_in($condiciones, $params, 'm.municipio', 'municipio', $municipios);
agregar_in($condiciones, $params, 'm.provincia', 'provincia', $provincias);

if (count($colores)) {
    $partesColor = [];
    foreach ($colores as $i => $valor) {
        $k = ':color' . $i;
        $partesColor[] = "(m.color_1 = $k OR m.color_2 = $k OR m.color_3 = $k)";
        $params[$k] = $valor;
    }
    $condiciones[] = '(' . implode(' OR ', $partesColor) . ')';
}

if (count($tags)) {
    $partesTag = [];
    foreach ($tags as $i => $valor) {
        $k = ':tag' . $i;
        $partesTag[] = "(',' || lower(replace(replace(m.keywords, ', ', ','), ' ,', ',')) || ',') LIKE $k";
        $params[$k] = '%,' . minusculas_utf8_ligero($valor) . ',%';
    }
    $condiciones[] = 'm.keywords IS NOT NULL AND (' . implode(' OR ', $partesTag) . ')';
}

$where = '';
if (count($condiciones)) {
    $where = 'WHERE ' . implode(' AND ', $condiciones);
}

// Tipos solicitados (incluye 'text' = medios tipo texto del viaje)
$tipos = ['image', 'video', 'audio', 'text'];
if ($tipoStr !== '') {
    $t = explode(',', $tipoStr);
    $t = array_map('trim', $t);
    $t = array_intersect($t, $tipos);
    if (count($t)) $tipos = array_values($t);
}

$resultados = [];

foreach ($tipos as $tipo) {
    // WHERE dinámico: si hay filtros previos, concatenar con AND
    $whereTipo = ($where ? ' AND' : ' WHERE') . ' m.tipo = :tipo';
    $sql = "SELECT m.id, m.archivo, m.tipo, m.subtipo, m.carpeta,
                   m.ruta_relativa, m.tamano_bytes, m.duracion_seg,
                   m.fecha, m.hora,
                   m.color_1, m.color_1_hex,
                   m.provincia, m.municipio, m.localidad,
                   m.titulo, m.descripcion, m.transcripcion
            FROM medios m
            $where$whereTipo
            ORDER BY RANDOM()
            LIMIT :limite";

    $stmt = $pdo->prepare($sql);
    foreach ($params as $k => $v) {
        $stmt->bindValue($k, $v);
    }
    $stmt->bindValue(':tipo', $tipo);
    $stmt->bindValue(':limite', $limite, PDO::PARAM_INT);
    $stmt->execute();
    $filas = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $resultados[$tipo] = $filas;
}

echo json_encode([
    'total_general' => array_sum(array_map('count', $resultados)),
    'filtros' => [
        'municipio' => $municipio,
        'color'     => $color,
        'provincia' => $provincia,
        'tag'       => $tag,
        'tipos'     => $tipos,
        'limite'    => $limite
    ],
    'resultados' => $resultados
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
