<?php
// Devuelve todos los puntos del embedding con datos para el canvas grande
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$sql = "SELECT id, archivo, carpeta, ruta_relativa,
               embedding_x, embedding_y, cluster,
               provincia, color_1, color_1_hex, descripcion
        FROM medios
        WHERE embedding_x IS NOT NULL AND embedding_y IS NOT NULL
        ORDER BY id";
$stmt = $pdo->query($sql);
$puntos = $stmt->fetchAll(PDO::FETCH_ASSOC);

echo json_encode([
    'total' => count($puntos),
    'puntos' => $puntos
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
