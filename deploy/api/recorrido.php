<?php
// Devuelve todos los puntos ordenados cronológicamente con colores dominantes
// para dibujar la línea "recorrido" en el canvas.
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$sql = "SELECT id, archivo, carpeta, tipo, ruta_relativa,
               fecha, hora,
               color_1, color_1_hex,
               color_2, color_2_hex,
               color_3, color_3_hex,
               provincia, municipio, descripcion
        FROM medios
        ORDER BY fecha, hora, id";

$stmt = $pdo->query($sql);
$puntos = $stmt->fetchAll(PDO::FETCH_ASSOC);

// También devolvemos la lista de colores disponibles y su hex representativo
// para armar los chips de selección
$sqlColores = "SELECT color_1 AS nombre, color_1_hex AS hex
               FROM medios WHERE color_1 IS NOT NULL
               UNION
               SELECT color_2, color_2_hex
               FROM medios WHERE color_2 IS NOT NULL
               UNION
               SELECT color_3, color_3_hex
               FROM medios WHERE color_3 IS NOT NULL";
$stmtColores = $pdo->query($sqlColores);
$filasColores = $stmtColores->fetchAll(PDO::FETCH_ASSOC);

// Agrupar hexes por nombre de color
$coloresAgrupados = [];
foreach ($filasColores as $f) {
    $nom = $f['nombre'];
    $hex = $f['hex'];
    if (!isset($coloresAgrupados[$nom])) {
        $coloresAgrupados[$nom] = ['nombre' => $nom, 'hexes' => []];
    }
    $coloresAgrupados[$nom]['hexes'][] = $hex;
}

// Para cada color, elegir el hex más frecuente como representativo
$coloresDisponibles = [];
foreach ($coloresAgrupados as $nom => $info) {
    $frecuencias = array_count_values($info['hexes']);
    arsort($frecuencias);
    $hexRep = array_key_first($frecuencias);
    $coloresDisponibles[] = [
        'nombre' => $nom,
        'hex'    => $hexRep,
        'total'  => count($info['hexes'])
    ];
}
// Ordenar por cantidad descendente
usort($coloresDisponibles, function($a, $b) {
    return $b['total'] - $a['total'];
});

echo json_encode([
    'total'    => count($puntos),
    'puntos'   => $puntos,
    'colores'  => $coloresDisponibles
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
