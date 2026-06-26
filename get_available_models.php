<?php
// List available models from the Google Generative AI API
header('Content-Type: application/json');

require_once 'config/config.php';

if (empty($GEMINI_API_KEY)) {
    echo json_encode(['error' => 'API key not configured']);
    exit;
}

// Try to list models available in v1 API
$url = "https://generativelanguage.googleapis.com/v1/models?key=$GEMINI_API_KEY";

$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => $url,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 10,
    CURLOPT_CONNECTTIMEOUT => 5,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json']
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$error = curl_error($ch);
curl_close($ch);

if ($error) {
    echo json_encode([
        'error' => "cURL error: $error",
        'http_code' => $httpCode
    ]);
    exit;
}

$data = json_decode($response, true);

if ($httpCode !== 200) {
    echo json_encode([
        'error' => 'Failed to list models',
        'http_code' => $httpCode,
        'response' => $data
    ]);
    exit;
}

// Extract model names and their supported methods
$models = [];
if (isset($data['models']) && is_array($data['models'])) {
    foreach ($data['models'] as $model) {
        $name = $model['name'] ?? '';
        $displayName = $model['displayName'] ?? '';
        $supportedMethods = $model['supportedGenerationMethods'] ?? [];
        
        // Extract model ID from "models/gemini-pro" format
        $modelId = str_replace('models/', '', $name);
        
        $models[] = [
            'id' => $modelId,
            'name' => $name,
            'displayName' => $displayName,
            'supported_methods' => $supportedMethods,
            'supports_generateContent' => in_array('generateContent', $supportedMethods)
        ];
    }
}

echo json_encode([
    'success' => true,
    'available_models' => $models,
    'total_models' => count($models),
    'http_code' => $httpCode
], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
?>
