<?php
/**
 * Devuelve mensajes de Telegram correspondientes a un municipio.
 * Estrategia: obtiene el rango de fechas de los medios en ese municipio
 * y busca mensajes de Telegram dentro de ese rango.
 * 
 * GET params:
 *   municipio (string, obligatorio)
 *   limite    (int, opcional, max mensajes a devolver, default 200)
 */
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$municipio = isset($_GET['municipio']) ? trim($_GET['municipio']) : '';
$limite    = isset($_GET['limite'])    ? max(1, min(500, (int)$_GET['limite'])) : 200;
$conFotos  = isset($_GET['fotos'])     ? filter_var($_GET['fotos'], FILTER_VALIDATE_BOOLEAN) : true;

if ($municipio === '') {
    echo json_encode(['error' => 'Falta parametro municipio'], JSON_UNESCAPED_UNICODE);
    exit;
}

// 1. Obtener rango de fechas del municipio
$stmt = $pdo->prepare("SELECT MIN(fecha) AS fecha_desde, MAX(fecha) AS fecha_hasta
                       FROM medios
                       WHERE municipio = ? AND fecha IS NOT NULL");
$stmt->execute([$municipio]);
$rango = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$rango || !$rango['fecha_desde']) {
    echo json_encode([
        'municipio' => $municipio,
        'total' => 0,
        'mensajes' => [],
        'rango' => null
    ], JSON_UNESCAPED_UNICODE);
    exit;
}

$desde = $rango['fecha_desde'] . 'T00:00:00Z';
$hasta = $rango['fecha_hasta'] . 'T23:59:59Z';

// 2. Buscar mensajes de Telegram en ese rango
$sql = "SELECT id, message_id, from_name, text, date_utc, message_type, has_media";
if ($conFotos) {
    $sql .= ", fotos";
}
$sql .= " FROM telegram_messages WHERE date_utc >= ? AND date_utc <= ? ORDER BY date_utc LIMIT ?";
$stmt = $pdo->prepare($sql);
$stmt->execute([$desde, $hasta, $limite]);
$mensajes = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Parsear JSON de fotos si existe
if ($conFotos) {
    foreach ($mensajes as &$m) {
        if (!empty($m['fotos'])) {
            $m['fotos'] = json_decode($m['fotos'], true);
            if (!is_array($m['fotos'])) {
                $m['fotos'] = [];
            }
        } else {
            $m['fotos'] = [];
        }
    }
    unset($m);
}

echo json_encode([
    'municipio' => $municipio,
    'total' => count($mensajes),
    'rango' => [
        'desde' => $rango['fecha_desde'],
        'hasta' => $rango['fecha_hasta']
    ],
    'mensajes' => $mensajes
], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
