<?php
/**
 * api/loop.php — Sirve la spec del motor de loop (spec.json) al navegador.
 *
 * La spec la genera el motor Python:
 *   python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida web3/spec.json
 *
 * GET: /api/loop.php
 * Devuelve el contenido de web3/spec.json con Content-Type application/json.
 * Si no existe, HTTP 503 con mensaje.
 */
$spec_path = __DIR__ . '/../spec.json';

if (!file_exists($spec_path)) {
    http_response_code(503);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(['error' => 'spec.json no existe. Ejecutar el motor: python scripts/ai_media/loop_db.py --horas 7 16 13 18 --salida web3/spec.json'], JSON_UNESCAPED_UNICODE);
    exit;
}

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
readfile($spec_path);
