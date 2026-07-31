<?php
/**
 * Devuelve tags extraídos de las descripciones de medios.
 * Filtra stop words en español y palabras cortas.
 * GET params:
 *   limite (int, opcional, max tags, default 40)
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$limite = isset($_GET['limite']) ? max(10, min(100, (int)$_GET['limite'])) : 40;

// Stop words en español
$stopWords = [
    'de','la','que','el','en','y','a','los','del','se','las','por','un','para',
    'con','no','una','su','al','lo','como','más','pero','sus','le','ya','este',
    'entre','porque','todo','esta','sin','ella','ello','cada','muy','puede',
    'todos','cual','otro','esa','ese','ser','son','era','han','tiene','fue',
    'esa','eso','estar','está','están','estaba','estaban','tiene','tienen',
    'mucho','poco','misma','mismo','casi','solo','sino','aunque','tanto',
    'parte','lado','tipo','forma','medio','través','través','donde',
    'detrás','encima','debajo','cerca','lejos','dentro','fuera','durante',
    'sobre','tras','contra','hacia','para','ante','bajo','cabe','según',
    'además','también','así','bien','como','cuando','después','entonces',
    'mientras','nunca','siempre','tampoco','menos','demasiado','bastante',
    'varios','pocos','muchos','algunos','otros','unas','unas','unas',
    'vemos','puede','imagen','muestra','observa','encuentra','tiene',
    'parece','describe','escena','fondo','color','colores','vista',
    'varias','diferentes','alrededor','parte','partes','hacia','donde',
    'este','esta','estos','estas','ese','esa','esos','esas','aquel','aquella'
];

// Obtener todas las descripciones no vacías
$stmt = $pdo->query("SELECT descripcion FROM medios WHERE descripcion IS NOT NULL AND descripcion != ''");
$frecuencias = [];

while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
    $texto = $row['descripcion'];
    // Normalizar: minúsculas, sin puntuación
    $texto = mb_strtolower($texto, 'UTF-8');
    $texto = preg_replace('/[^a-záéíóúüñ\s]/u', ' ', $texto);
    $palabras = preg_split('/\s+/', $texto);
    
    foreach ($palabras as $p) {
        $p = trim($p);
        if (strlen($p) < 4) continue;               // muy cortas
        if (in_array($p, $stopWords)) continue;      // stop words
        $frecuencias[$p] = ($frecuencias[$p] ?? 0) + 1;
    }
}

// Ordenar por frecuencia descendente
arsort($frecuencias);

// Tomar top N
$top = array_slice($frecuencias, 0, $limite);

$resultado = [];
foreach ($top as $palabra => $frecuencia) {
    $resultado[] = [
        'tag' => $palabra,
        'frecuencia' => $frecuencia,
        'peso' => round($frecuencia / max($frecuencias), 2)
    ];
}

echo json_encode([
    'total' => count($resultado),
    'tags' => $resultado
], JSON_UNESCAPED_UNICODE);
