<?php
/**
 * Devuelve tags para la nube de la visualización.
 * Fuente: keywords reales de la DB (columna `keywords`, de ia_keywords).
 * Filtra basura del modelo de visión y palabras muy cortas.
 *
 * GET params:
 *   limite (int, opcional, max tags, default 40)
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$limite = isset($_GET['limite']) ? max(10, min(100, (int)$_GET['limite'])) : 40;

// Normalizar palabra: minúsculas, quitar puntuación rara (conserva letras con tilde y guiones)
function limpiar_palabra($p) {
    $p = mb_strtolower(trim($p), 'UTF-8');
    $p = preg_replace('/[^a-záéíóúüñ\s-]/u', '', $p);
    return trim($p);
}

// Basura del modelo de visión (keywords que no significan nada o restos en inglés)
// Se normalizan igual que los keywords para que el match sea correcto.
$keywordsBasura = array_map('limpiar_palabra', [
    'otras','otros','macarona','objetivo','elante','aguaje','obtusco',
    'delicia','delicía','aguacate','esponja ribiosa','siguiente','igualmente',
    'pancho','género','ella','es ella','del tiempo','no incluía',
    'fiestas/concierto','gushing river','mountain top','green grass',
    'blue sky','yellow sun','general','etc','algo','cosas','miscelanea',
    'multa','otra','diversos','diversas','varias cosas','además','monta',
    'és ella','inlcuye','vista'
]);

$frecuencias = [];

// ── Fuente: keywords reales (columna keywords) ────────────
$stmt = $pdo->query("SELECT keywords FROM medios WHERE keywords IS NOT NULL AND keywords != ''");
$kwCount = 0;
while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
    foreach (explode(',', $row['keywords']) as $kw) {
        $kw = limpiar_palabra($kw);
        if (strlen($kw) < 3) continue;
        if (in_array($kw, $keywordsBasura, true)) continue;
        $frecuencias[$kw] = ($frecuencias[$kw] ?? 0) + 1;
        $kwCount++;
    }
}

// Ordenar por frecuencia descendente
arsort($frecuencias);

// Descartar fragmentos con frecuencia 1 que contengan espacios (basura tipo "no incluía")
foreach ($frecuencias as $palabra => $freq) {
    if ($freq === 1 && strpos($palabra, ' ') !== false) {
        unset($frecuencias[$palabra]);
    }
}

$top = array_slice($frecuencias, 0, $limite);
$maxF = $top ? max($top) : 1;

$resultado = [];
foreach ($top as $palabra => $frecuencia) {
    $resultado[] = [
        'tag' => $palabra,
        'frecuencia' => $frecuencia,
        'peso' => round($frecuencia / $maxF, 2)
    ];
}

echo json_encode([
    'total' => count($resultado),
    'keyword_count' => $kwCount,
    'tags' => $resultado
], JSON_UNESCAPED_UNICODE);
