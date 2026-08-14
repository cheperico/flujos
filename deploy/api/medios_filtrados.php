<?php
/**
 * Devuelve hasta N medios aleatorios filtrados por municipio/color/provincia/tipo.
 * GET params:
 *   municipio (string, opcional)
 *   color     (string, opcional)
 *   provincia (string, opcional)
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
$tipoStr   = isset($_GET['tipo'])      ? trim($_GET['tipo'])      : '';
$limite    = isset($_GET['limite'])    ? max(1, min(20, (int)$_GET['limite'])) : 5;

// Construir WHERE dinámico
$condiciones = [];
$params = [];

if ($municipio !== '') {
    $condiciones[] = 'm.municipio = :municipio';
    $params[':municipio'] = $municipio;
}
if ($color !== '') {
    $condiciones[] = '(m.color_1 = :color OR m.color_2 = :color OR m.color_3 = :color)';
    $params[':color'] = $color;
}
if ($provincia !== '') {
    $condiciones[] = 'm.provincia = :provincia';
    $params[':provincia'] = $provincia;
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
                   m.descripcion, m.transcripcion
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
        'tipos'     => $tipos,
        'limite'    => $limite
    ],
    'resultados' => $resultados
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
