<?php
/**
 * Sirve un archivo multimedia por ID.
 * GET: ?id=123
 */
require_once __DIR__ . '/../includes/db.php';
$pdo = db();

$id = isset($_GET['id']) ? (int)$_GET['id'] : 0;
if ($id <= 0) { http_response_code(400); echo "ID invalido"; exit; }

$stmt = $pdo->prepare("SELECT ruta_absoluta, tipo FROM medios WHERE id = ?");
$stmt->execute([$id]);
$row = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$row || !$row['ruta_absoluta']) {
    http_response_code(404);
    echo "Archivo no encontrado";
    exit;
}

$path = $row['ruta_absoluta'];
if (!file_exists($path)) {
    http_response_code(404);
    echo "Archivo no existe en disco";
    exit;
}

$ext = strtolower(pathinfo($path, PATHINFO_EXTENSION));

// Mapear extensiones a MIME
$mimes = [
    'jpg' => 'image/jpeg', 'jpeg' => 'image/jpeg',
    'png' => 'image/png', 'gif' => 'image/gif',
    'webp' => 'image/webp', 'bmp' => 'image/bmp',
    'mp3' => 'audio/mpeg', 'wav' => 'audio/wav',
    'ogg' => 'audio/ogg', 'm4a' => 'audio/mp4',
    'aac' => 'audio/aac', 'wma' => 'audio/x-ms-wma',
    'mp4' => 'video/mp4', 'mov' => 'video/quicktime',
    'avi' => 'video/x-msvideo', 'webm' => 'video/webm',
    'mkv' => 'video/x-matroska'
];

$mime = isset($mimes[$ext]) ? $mimes[$ext] : 'application/octet-stream';

// Si es thumb y es imagen, redimensionar a ~200px
// Requiere la extensión GD de PHP
$esThumb = isset($_GET['thumb']) && $row['tipo'] === 'image'
           && in_array($ext, ['jpg','jpeg','png','gif','webp'])
           && function_exists('imagecreatefromjpeg');

if ($esThumb) {
    $maxW = 200;
    $info = @getimagesize($path);
    if ($info) {
        list($w, $h) = $info;
        if ($w > $maxW) {
            $ratio = $maxW / $w;
            $nw = $maxW;
            $nh = round($h * $ratio);
            $src = null;
            switch ($info[2]) {
                case IMAGETYPE_JPEG: $src = @imagecreatefromjpeg($path); break;
                case IMAGETYPE_PNG:  $src = @imagecreatefrompng($path); break;
                case IMAGETYPE_GIF:  $src = @imagecreatefromgif($path); break;
                case IMAGETYPE_WEBP: $src = @imagecreatefromwebp($path); break;
            }
            if ($src) {
                $thumb = imagecreatetruecolor($nw, $nh);
                imagecopyresampled($thumb, $src, 0, 0, 0, 0, $nw, $nh, $w, $h);
                header('Content-Type: ' . $mime);
                switch ($info[2]) {
                    case IMAGETYPE_JPEG: imagejpeg($thumb, null, 70); break;
                    case IMAGETYPE_PNG:  imagepng($thumb, null, 6); break;
                    case IMAGETYPE_GIF:  imagegif($thumb); break;
                    case IMAGETYPE_WEBP: imagewebp($thumb, null, 70); break;
                }
                imagedestroy($thumb);
                imagedestroy($src);
                exit;
            }
        }
    }
    // Si no se pudo redimensionar, servir original pero con Content-Type
}

header('Content-Type: ' . $mime);
header('Content-Length: ' . filesize($path));
header('Cache-Control: public, max-age=86400');
readfile($path);
