<?php
/**
 * Devuelve transcripciones para el bloque "Textos".
 * Prioriza audios transcritos; opcionalmente excluye una lista de ids
 * (para no repetir los audios que ya están en el contenedor de sonidos).
 *
 * GET params:
 *   limite  (int, opcional, max textos, default 8)
 *   no      (string, opcional, IDs separados por coma a excluir)
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$limite = isset($_GET['limite']) ? max(1, min(20, (int)$_GET['limite'])) : 8;
$no = isset($_GET['no']) ? trim($_GET['no']) : '';
$excluir = [];
foreach (array_filter(explode(',', $no)) as $id) {
    $id = (int)$id;
    if ($id > 0) $excluir[] = $id;
}

// Preferir audios con transcripción; si no hay, cualquier tipo con transcripción.
$sql = "SELECT id, archivo, carpeta, subtipo, duracion_seg, descripcion, transcripcion
        FROM medios
        WHERE transcripcion IS NOT NULL AND transcripcion != ''";
$params = [];
if (count($excluir)) {
    $marcas = implode(',', array_fill(0, count($excluir), '?'));
    $sql .= " AND id NOT IN ($marcas)";
    $params = array_merge($params, $excluir);
}
$sql .= " ORDER BY (carpeta = 'telegram') ASC, RANDOM() LIMIT ?";
$params[] = $limite;

$stmt = $pdo->prepare($sql);
$stmt->execute($params);
$filas = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Compactar transcripciones (quitar saltos de línea, recortar)
foreach ($filas as &$f) {
    $t = $f['transcripcion'];
    $t = preg_replace('/\s+/u', ' ', $t);
    $f['transcripcion'] = trim($t);
}
unset($f);

echo json_encode([
    'total' => count($filas),
    'textos' => $filas
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);