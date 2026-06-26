<?php
ob_clean();

ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);
error_reporting(E_ALL);

include '../config/db.php';
include "../config/config.php";

// Define supported Gemini models (in order of preference)
// These models are commonly available with Google Generative AI API
define('GEMINI_MODELS', [
    'gemini-pro',
    'gemini-1.5-pro',
    'gemini-1.5-flash',
]);

/**
 * Get list of available models from Gemini API
 * Caches result for 1 hour to avoid repeated API calls
 */
function get_available_gemini_models() {
    global $GEMINI_API_KEY;
    
    $cache_key = 'gemini_available_models_v1';
    $cache_file = sys_get_temp_dir() . '/examiq_' . md5('gemini_models_' . $GEMINI_API_KEY) . '.json';
    $cache_max_age = 3600; // 1 hour
    
    // Check cache
    if (file_exists($cache_file) && (time() - filemtime($cache_file) < $cache_max_age)) {
        $cached = json_decode(file_get_contents($cache_file), true);
        if (is_array($cached) && !empty($cached)) {
            error_log("Using cached available models: " . implode(', ', $cached));
            return $cached;
        }
    }
    
    // Query API to get available models
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
    curl_close($ch);
    
    $available = [];
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        if (isset($data['models']) && is_array($data['models'])) {
            foreach ($data['models'] as $model) {
                $name = str_replace('models/', '', $model['name'] ?? '');
                // Only include models that support generateContent
                if (isset($model['supportedGenerationMethods']) && 
                    in_array('generateContent', $model['supportedGenerationMethods'])) {
                    $available[] = $name;
                }
            }
            
            // Cache the result
            @file_put_contents($cache_file, json_encode($available));
            error_log("Discovered available Gemini models: " . implode(', ', $available));
            return $available;
        }
    }
    
    error_log("Failed to query available models (HTTP $httpCode)");
    return [];
}

// Set CORS headers properly for credential-based requests
$origin = $_SERVER['HTTP_ORIGIN'] ?? '';
$allowedOrigins = ['http://localhost', 'http://localhost:80', 'http://localhost:3000', 'http://127.0.0.1'];
if (in_array($origin, $allowedOrigins) || strpos($origin, 'localhost') !== false || strpos($origin, '127.0.0.1') !== false) {
    header('Access-Control-Allow-Origin: ' . $origin);
    header('Access-Control-Allow-Credentials: true');
} else {
    header('Access-Control-Allow-Origin: ' . $_SERVER['HTTP_ORIGIN'] ?? '*');
}
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

// Start PHP session so API can access session-based authentication
if (session_status() === PHP_SESSION_NONE) {
    // set a longer cookie lifetime (1 day) to help persist sessions across refresh
    // Using SameSite=None with Secure for proper cross-origin session handling
    $sameSite = 'Lax';
    if (isset($_SERVER['HTTPS']) || strpos($_SERVER['HTTP_ORIGIN'] ?? '', 'https') === 0) {
        $sameSite = 'None';
    }
    session_set_cookie_params([
        'lifetime' => 86400,
        'path' => '/',
        'domain' => '',
        'httponly' => true,
        'secure' => (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off'),
        'samesite' => $sameSite
    ]);
    session_start();
}

header('Content-Type: application/json');

date_default_timezone_set('Asia/Manila');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

$action = $_GET['action'] ?? $_POST['action'] ?? '';
$response = ['success' => false, 'message' => 'Invalid action'];

switch ($action) {
    case "get_topics":
        $response = getTopics($conn);
        break;
    case "get_questions":
        $response = getQuestions($conn);
        break;
    case "submit_exam":
        $response = submitExam($conn);
        break;
    case "get_analytics":
        $response = getAnalytics($conn);
        break;
    case "get_recommendations":
        $studentId = $_GET['student_id'] ?? 0;
        $response = recommendTopics($conn, $studentId);
        break;
    case "get_exam_history":
        getExamHistory($conn);
        break;
    case "get_student_details":
        getStudentDetails($conn);
        break;
    case "update_student_profile":
        updateStudentProfile($conn);
        break;
    case "update_student_course":
        updateStudentCourse($conn);
        break;
    case "update_student_number":
        updateStudentNumber($conn);
        break;
    case "get_dashboard_data":
        getDashboardData($conn);
        break;
    case "check_session":
        $response = checkSession();
        break;
    case "get_lesson":
        $topic = strtolower($_GET['topic'] ?? '');
        $response = getLessonContent($topic);
        break;
    case "ask_tutor":
        // Lightweight tutor QA endpoint (keeps behavior simple and focused)
        $payload = json_decode(file_get_contents('php://input'), true);
        $topic = strtolower($payload['topic'] ?? '');
        $question = strtolower($payload['message'] ?? $payload['question'] ?? '');
        $response = tutorQA($topic, $question);
        break;

    case "ai_chat":
        // Chat endpoint: accepts optional `history` (array of {role,text}), topic, and message
        $inputRaw = file_get_contents("php://input");
        $input = json_decode($inputRaw, true);

        // Debug logging removed in production - no-op here.

        $userMessage = $input["message"] ?? "";
        $topic = $input["topic"] ?? "general";
        $examContext = $input["exam_context"] ?? [];

        // If the frontend sent a `history` array include previous turns for context
        $historyText = "";
        if (isset($input['history']) && is_array($input['history'])) {
            foreach ($input['history'] as $turn) {
                $role = strtolower(trim($turn['role'] ?? 'user'));
                $text = trim((string)($turn['text'] ?? ''));
                if ($text === '') continue;
                if ($role === 'assistant' || $role === 'bot') {
                    $historyText .= "Assistant: " . $text . "\n";
                } else {
                    $historyText .= "User: " . $text . "\n";
                }
            }
        }

        $prompt = "You are ExamiQ+, a clear and friendly math tutor.\n\n";
        $prompt .= "Topic: " . ($topic ?: 'general') . "\n\n";
        
        // Include exam context if available
        if (!empty($examContext)) {
            $examInfo = "";
            if (!empty($examContext['exam_name'])) {
                $examInfo .= "The student recently took an exam: " . $examContext['exam_name'];
            }
            if (!empty($examContext['subject'])) {
                $examInfo .= " on the subject of " . $examContext['subject'];
            }
            if (!empty($examContext['topic'])) {
                $examInfo .= " covering the topic " . $examContext['topic'];
            }
            if ($examInfo) {
                $prompt .= "Context: " . $examInfo . "\n\n";
            }
        }
        
        if ($historyText !== "") {
            $prompt .= "Conversation so far:\n" . $historyText . "\n";
        }
        $prompt .= "User: " . $userMessage . "\n\n";
        $prompt .= "RULES:\n";
        $prompt .= "- Do NOT greet the user (no 'Hi', no 'Hello').\n";
        $prompt .= "- Do NOT introduce yourself.\n";
        $prompt .= "- Respond directly to the topic.\n";
        $prompt .= "- Keep explanations simple unless user asks for detailed steps.\n";
        $prompt .= "- If the message is vague, connect it to the topic or the exam they just took.\n";
        $prompt .= "- If it's about a calculation, show clean steps using plain text.\n";
        $prompt .= "- If it's conceptual, explain with 1 example.\n\n";
        $prompt .= "Now answer clearly and continue the conversation, using prior context where helpful.";

        // pass into chatGPT the correct format (include the raw history for auditing)
        $response = chatGPT([
            "message" => $prompt,
            "topic"   => $topic,
            "history" => $input['history'] ?? null
        ]);

        // Strip Markdown markers (bold/italic/code/fences/links) from AI reply for safety
        if (is_array($response) && isset($response['answer']) && is_string($response['answer'])) {
            $response['answer'] = stripMarkdown($response['answer']);
        }

        break;
    case "review_failed":
        $studentId = $_GET['student_id'];
        $response = getFailedConcepts($conn, $studentId);
        break;
    case "ai_feedback":
        $input = json_decode(file_get_contents("php://input"), true);
        $topic = $input['topic'] ?? 'general';
        $progressive = isset($input['progressive']) && $input['progressive'] ? true : false;
        // If progressive streaming requested, set NDJSON content-type
        if ($progressive) {
            header('Content-Type: application/x-ndjson');
            // Caller expects streamed chunk JSON lines; generate and echo progressively
            if (isset($input['submission']) && is_array($input['submission'])) {
                generateAIFeedbackPHP($topic, $input['submission'], null, null, null, $input['patterns'] ?? [], true);
            } else {
                generateAIFeedbackPHP($topic, $input['question'] ?? '', $input['userAnswer'] ?? '', $input['correctAnswer'] ?? '', $input['confidence'] ?? 'medium', $input['patterns'] ?? [], true);
            }
            // generateAIFeedbackPHP already echoed progressive output; exit to avoid extra JSON
            exit;
        }

        // Support batch submissions (array of answers) or single-question payloads (non-progressive)
        if (isset($input['submission']) && is_array($input['submission'])) {
            $response = generateAIFeedbackPHP($topic, $input['submission'], null, null, null, $input['patterns'] ?? [], false);
        } else {
            $response = generateAIFeedbackPHP($topic, $input['question'] ?? '', $input['userAnswer'] ?? '', $input['correctAnswer'] ?? '', $input['confidence'] ?? 'medium', $input['patterns'] ?? [], false);
        }
        break;
    case "tutor_intro":
        $input = json_decode(file_get_contents("php://input"), true);
        $topic = $input['topic'] ?? 'general';

        $prompt = "
        You are ExamiQ+, a concise and friendly math tutor.
        Provide a SHORT structured lesson intro for the topic: $topic.

        FORMAT STRICTLY LIKE THIS:
        Topic: <topic>

        Lesson:
        - 2 to 4 bullets of quick refresher concepts

        Example:
        A simple computation or example problem with solution.

        Keep everything SHORT and easy to read.
        No fancy symbols. Plain text only.
        ";

        echo json_encode(chatGPT(["message" => $prompt]));
        exit;
    case "start_exam":
        $response = startExam($conn);
        break;
    default:
        $response = ['success' => false, 'message' => 'Unknown or missing action.'];
}

echo json_encode($response, JSON_UNESCAPED_UNICODE);

// Function to get all available topics from the database
function getTopics($conn) {
    $sql = "SELECT DISTINCT topic FROM questions ORDER BY topic ASC";
    $result = $conn->query($sql);
    
    if (!$result) {
        return ['success' => false, 'message' => 'Failed to fetch topics'];
    }
    
    $topics = [];
    while ($row = $result->fetch_assoc()) {
        $topics[] = $row['topic'];
    }
    
    return ['success' => true, 'topics' => $topics];
}
if (json_last_error() !== JSON_ERROR_NONE) {
    error_log("JSON encoding error: " . json_last_error_msg());
}
exit;

function getQuestions($conn) {
    $topic = $_GET['topic'] ?? '';
    //added
    $map = [
        "Beginner" => "Beginner",
        "Intermediate" => "Intermediate",
        "Advanced" => "Advanced"
    ];
    $difficulty = $_GET['difficulty'] ?? '';
    $difficulty = $map[$difficulty] ?? $difficulty; //added
    if (empty($topic) || empty($difficulty)) return ['success' => false, 'message' => 'Missing topic or difficulty'];

    $sql = "SELECT question_id, question AS question_text, 
               option_a AS choice_a, 
               option_b AS choice_b, 
               option_c AS choice_c, 
               option_d AS choice_d, 
               correct_answer,
               concept_tag
        FROM questions 
        WHERE topic = ? AND difficulty = ? 
        ORDER BY RAND() LIMIT 10"; 

    $stmt = $conn->prepare($sql);
    if (!$stmt) {
        return ['success' => false, 'message' => 'SQL Prepare Failed: ' . $conn->error];
    }
    $stmt->bind_param("ss", $topic, $difficulty);
    
    if (!$stmt->execute()) {
        return ['success' => false, 'message' => 'SQL Execute Failed: ' . $stmt->error];
    }
    
    $result = $stmt->get_result();

    if (!$result) {
        return ['success' => false, 'message' => 'Failed to get result set'];
    }

    $questions = [];
    while ($row = $result->fetch_assoc()) {
        $row['concept_tag'] = $row['concept_tag'] ?? null;
        $raw = trim((string)($row['correct_answer'] ?? ''));
        $choices = [
            'A' => $row['choice_a'] ?? '',
            'B' => $row['choice_b'] ?? '',
            'C' => $row['choice_c'] ?? '',
            'D' => $row['choice_d'] ?? ''
        ];

        $correctLetter = null;
        $correctText = '';
        $numToLetter = ['1' => 'A', '2' => 'B', '3' => 'C', '4' => 'D'];

        if (preg_match('/^[ABCD]$/i', $raw)) {
            $correctLetter = strtoupper($raw);
            $correctText = $choices[$correctLetter] ?? '';
        } elseif (isset($numToLetter[$raw])) {
            $correctLetter = $numToLetter[$raw];
            $correctText = $choices[$correctLetter] ?? '';
        } else {
            $correctText = $raw;
            
            foreach ($choices as $letter => $txt) {
                if (strcasecmp(trim($txt), trim($raw)) === 0) {
                    $correctLetter = $letter;
                    break;
                }
            }
            // prefix match fallback (e.g. "72" ~ "72°")
            if (!$correctLetter && $raw !== '') {
                foreach ($choices as $letter => $txt) {
                    if ($txt !== null && stripos(preg_replace('/\s+/', '', $txt), preg_replace('/\s+/', '', $raw)) === 0) {
                        $correctLetter = $letter;
                        break;
                    }
                }
            }
        }

        $row['correct_letter'] = $correctLetter; // may be null
        $row['correct_text'] = $correctText;
        $questions[] = $row;
    }

    if (empty($questions)) {
        return ['success' => false, 'message' => "No questions found for topic='$topic' and difficulty='$difficulty'"];
    }

    return ['success' => true, 'questions' => $questions];
}


function submitExam($conn) {
    try {
        $raw = file_get_contents('php://input');
        $data = json_decode($raw, true);
        if(!$data){
            error_log("Raw input received: " . $raw);
            throw new Exception("Invalid JSON input");
        }

        $studentId = $data['student_id'] ?? 0;
        $examName = $data['exam_name'] ?? 'Math Review Exam';
        $topic = $data['topic'] ?? '';
        $difficulty = $data['difficulty'] ?? '';
        $course = $data['course'] ?? '';
        $subject = $data['subject'] ?? '';
        $submission = $data['submission'] ?? [];

        if (empty($studentId) || empty($submission)){
            throw new Exception("Missing student ID or submission");
        }

        $score = 0;
        $total = count($submission);
        $totalConfidence = 0;
        $highConfidenceWrong = 0;
        $lowConfidenceCorrect = 0;
        $gradedResults = [];
        
        $startTime = $data['start_time'] ?? date('Y-m-d H:i:s'); // fallback
        $endTime = $data['end_time'] ?? date('Y-m-d H:i:s'); // fallback
        $examDate = date('Y-m-d H:i:s'); // Add exam_date here

        $normText = function($s) {
            if ($s === null) return '';
            
            $t = mb_strtolower(trim($s));
            $t = preg_replace('/\s+/', ' ', $t);
            return $t;
        };

        $numToLetter = ['1'=>'A','2'=>'B','3'=>'C','4'=>'D'];
        for($i = 0; $i < $total; $i++){
            $item = $submission[$i];

            $userAnswer = trim(strtolower($item['userAnswer'] ?? $item['answer'] ?? ''));
            $correctAnswer = trim(strtolower($item['correctAnswer'] ?? $item['correct'] ?? ''));
            $confidenceStr = strtolower($item['confidence'] ?? 'medium');

            $confidenceStr = match ($confidenceStr) {
                '1', '2', 'low' => 'low',
                '3', 'medium' => 'medium',
                '4', '5', 'high' => 'high',
                default => 'medium'
            };

            $isCorrect = ($userAnswer === $correctAnswer);
            if($isCorrect){
                $score++;
                if ($confidenceStr <= 2) $lowConfidenceCorrect++;
            }else{
                if ($confidenceStr >= 4) $highConfidenceWrong++;
            }

            //moved here
            $confidenceValue = match ($confidenceStr) {
                'low' => 2,
                'medium' => 3,
                'high' => 5,
                default => 3
            };
            $totalConfidence += $confidenceValue; //from confidenceStr
            $gradedResults[] = [
                'questionId' => $item['questionId'] ?? 0,
                'userAnswer' => $userAnswer,
                'correctAnswer' => $correctAnswer,
                'isCorrect' => $isCorrect,
                'confidence' => $confidenceStr,
                'concept_tag' => $item['concept_tag'] ?? null, // NEW ADDED
                'exam_date' => $examDate // Add exam_date to each submission item
            ];
        }

        $percentage = round(($score / $total) * 100, 2);
        $avgConfidence = round($totalConfidence / $total, 2);
        $feedback = generateFeedback($percentage, $avgConfidence, $lowConfidenceCorrect, $highConfidenceWrong);
        $submissionJson = json_encode($gradedResults, JSON_UNESCAPED_UNICODE);

        $stmt = $conn->prepare("
            INSERT INTO exam_results 
                (student_id, start_time, end_time, score, total, percentage, exam_name, submission_details, exam_date, topic, subject)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ");

        if(!$stmt){
            throw new Exception("prepare failed: " . $conn->error);
        }

        // Bind parameters: 11 total (i=int, s=string, d=double)
        // Order: student_id(i), start_time(s), end_time(s), score(i), total(i), percentage(d), 
        //        exam_name(s), submission_details(s), exam_date(s), topic(s), subject(s)
        if(!$stmt->bind_param(
            "issiidsssss",
            $studentId,
            $startTime,
            $endTime,
            $score,
            $total,
            $percentage,
            $examName,
            $submissionJson,
            $examDate,
            $topic,
            $subject
        )) {
            throw new Exception("bind_param failed: " . $stmt->error);
        }

        if (!$stmt->execute()) {
            throw new Exception("Execute failed: " . $stmt->error);
        }
        $stmt->close();

        // Save individual mistakes to mistakes table
        $mistakesSaved = 0;
        foreach ($gradedResults as $result) {
            if (!$result['isCorrect']) {
                $mistakeStmt = $conn->prepare("
                    INSERT INTO mistakes 
                        (student_id, question_text, user_answer, correct_answer, confidence, topic, difficulty, subject, course, exam_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ");
                
                if ($mistakeStmt) {
                    // Find the original submission data for this question to get the question text
                    $questionText = '';
                    foreach ($submission as $subItem) {
                        if (($subItem['questionId'] ?? $subItem['question_id'] ?? 0) == $result['questionId']) {
                            $questionText = $subItem['question'] ?? $subItem['question_text'] ?? '';
                            break;
                        }
                    }
                    
                    $mistakeStmt->bind_param(
                        "isssssssss",
                        $studentId,
                        $questionText,
                        $result['userAnswer'],
                        $result['correctAnswer'],
                        $result['confidence'],
                        $topic,
                        $difficulty,
                        $subject,
                        $course,
                        $examDate
                    );
                    
                    if ($mistakeStmt->execute()) {
                        $mistakesSaved++;
                    }
                    $mistakeStmt->close();
                }
            }
        }

        return [
            'success' => true,
            'message' => "Exam graded and saved successfully. $mistakesSaved mistakes saved for review.",
            'result' => [
                'score' => $score,
                'total' => $total,
                'percentage' => $percentage,
                'feedback' => $feedback,
                'mistakes_saved' => $mistakesSaved
            ]
        ];
    } catch (Exception $e) {
        error_log("Submit Exam Error: " . $e->getMessage());
        return ['success' => false, 'message' => $e->getMessage()];
    }
}

function getAnalytics($conn) {
    $studentId = $_GET['student_id'] ?? 0;

    $sql = "SELECT exam_date, percentage, exam_name, submission_details 
            FROM exam_results WHERE student_id = ? 
            ORDER BY exam_date DESC";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $result = $stmt->get_result();

    $records = [];
    $confidenceData = [];
    while ($row = $result->fetch_assoc()) {
        $records[] = [
            'exam_name' => $row['exam_name'],
            'percentage' => $row['percentage'],
            'date' => date('M d', strtotime($row['exam_date']))
        ];

        //check if the submission row is empty, if not then proceed
        if(!empty($row['submission_details'])){
            $submission = json_decode($row['submission_details'], true); //decode the value of the submission details to an array
            if(json_last_error() === JSON_ERROR_NONE && is_array($submission)){ //check if the submission var. is an array, then proceed
                foreach($submission as $q){
                    //extract the confidence (e.g. high, low, medium) as a lowercase, if none then return empty string
                    $confidence = strtolower($q['confidence'] ?? ''); 
                    //check if the confidence values array e.g. high etc. matches the confidence var. 
                    if (in_array($confidence, ['high', 'medium', 'low'])) {
                        //then extract the confidence value and if the ans. is correct or not and put it in
                        //a temporary var. called confidence data
                        $confidenceData[] = [
                            'confidence' => $confidence,
                            'isCorrect' => $q['isCorrect'] ?? false
                        ];
                    }
                }
            }
        }
    }

    //confidence stats array is designed to count how many times that the student chose high, medium, low, all starts with 0
    //correct stats array is designed to count how many times a student was correct for each confidence level e.g. high etc.
    $confidenceStats = ['high' => 0, 'medium' => 0, 'low' => 0];
    $correctStats = ['high' => 0, 'medium' => 0, 'low' => 0];
    foreach($confidenceData as $data){ 
        $level = strtolower($data['confidence']); //takes the student's confidence lvl then converts to lowercase to match the scoreboards
        if(!isset($confidenceStats[$level])) continue; //checks if confidence lvl exists as a valid category in the scoreboard
        $confidenceStats[$level]++; //finds the correct spot on the confidence stats and increment it by 1 for that lvl
        if($data['isCorrect']) $correctStats[$level]++; //checks if the student's ans is correct for that question, if true then +1, otherwise does nothing
    }

    $confidencePerformance = [];
    foreach($confidenceStats as $level => $count){
        //check if the confidence level chosen at least once
        $accuracy = $count > 0 ? round(($correctStats[$level] / $count) * 100, 2) : 0;
        $confidencePerformance[$level] = $accuracy;
    }
    return [
        'success' => true,
        'records' => $records,
        'confidencePerformance' => $confidencePerformance
    ];
}

function generateFeedback($percent, $avgConfidence, $lowConfidenceCorrect, $highConfidenceWrong) {
    $feedback = [];

    if ($percent >= 90) $feedback[] = "Excellent work! You’ve mastered this topic.";
    elseif ($percent >= 75) $feedback[] = "Good job! You have a solid grasp of the material.";
    elseif ($percent >= 50) $feedback[] = "You’re on the right track. Review your weak spots for improvement.";
    else $feedback[] = "Keep practicing and reviewing your mistakes to strengthen understanding.";

    if ($avgConfidence < 3) $feedback[] = "You seemed uncertain overall — build more confidence in your knowledge.";
    elseif ($avgConfidence > 4) $feedback[] = "High confidence detected — but double-check reasoning to reduce careless errors.";

    if ($highConfidenceWrong > 0) $feedback[] = "You had {$highConfidenceWrong} confident mistakes — those need focused review.";
    if ($lowConfidenceCorrect > 0) $feedback[] = "You had {$lowConfidenceCorrect} correct guesses — trust your intuition more.";

    return implode(" ", $feedback);
}

function recommendTopics($conn, $studentId) {
    $sql = "SELECT exam_name, percentage, submission_details
            FROM exam_results 
            WHERE student_id = ? 
            ORDER BY exam_date DESC 
            LIMIT 5";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $result = $stmt->get_result();

    $topicStats = [];
    while ($row = $result->fetch_assoc()) {
        //$examTopic = strtolower(str_replace(" Exam", "", $row['exam_name']));
        //normalize topic title
        $examTopic = strtolower(trim(str_ireplace(['exam', 'test'], '', $row['exam_name'])));
        $percentage = (float)$row['percentage'];
        $submission = json_decode($row['submission_details'], true) ?? [];

        //check if topic is initialized
        if (!isset($topicStats[$examTopic])) {
            $topicStats[$examTopic] = [
                'attempts' => 0,
                'correct' => 0,
                'wrong' => 0,
                'lowConfidenceCorrect' => 0,
                'highConfidenceWrong' => 0,
                'avgScore' => 0
            ];
        }

        foreach($submission as $q){
            $isCorrect = strtolower(trim($q['userAnswer'] ?? '')) === strtolower(trim($q['correctAnswer'] ?? ''));
            $confidence = strtolower($q['confidence'] ?? 'medium');

            $topicStats[$examTopic]['attempts']++; //increment attempts of the topic stats count (high, medium, low) from the specific topic e.g. algebra
            if ($isCorrect) {
                $topicStats[$examTopic]['correct']++;
                if ($confidence === 'low') $topicStats[$examTopic]['lowConfidenceCorrect']++;
            } else {
                $topicStats[$examTopic]['wrong']++;
                if ($confidence === 'high') $topicStats[$examTopic]['highConfidenceWrong']++;
            }
        }

        // compute average after processing each exam
        $topicStats[$examTopic]['avgScore'] = ($topicStats[$examTopic]['correct'] / max(1, $topicStats[$examTopic]['attempts'])) * 100;
    }

    //uasort($topicStats, fn($a, $b) => $a['avgScore'] <=> $b['avgScore']);
    //show at least one topic recommendation if none found
    if (empty($recommendations) && !empty($topicStats)) {
        uasort($topicStats, fn($a, $b) => $a['avgScore'] <=> $b['avgScore']); // Find the weakest topic (lowest avg score)
        $weakestTopic = array_key_first($topicStats);

        $recommendations[] = [
            'topic' => ucfirst($weakestTopic),
            'reason' => "Continue reviewing this topic to strengthen your understanding.",
            'accuracy' => round($topicStats[$weakestTopic]['avgScore'], 2)
        ];
    }


    $recommendations = [];
    foreach ($topicStats as $topic => $stats) {
        if ($stats['avgScore'] < 90 || $stats['highConfidenceWrong'] > 0 || $stats['lowConfidenceCorrect'] > 0) {
            $recommendations[] = [
                'topic' => ucfirst($topic),
                'reason' => match (true) {
                    $stats['highConfidenceWrong'] > 0 => "You were confident but made mistakes — recheck reasoning.",
                    $stats['avgScore'] < 60 => "You struggled heavily with this topic.",
                    default => "Needs slight review for mastery."
                },
                'accuracy' => round($stats['avgScore'], 2)
            ];
        }
    }
    return [
        'success' => true,
        'recommendations' => $recommendations
    ];
}

function getProgressSummary($conn, $studentId) {
    $sql = "SELECT exam_name, AVG(percentage) as avg_score, COUNT(*) as exams_taken
            FROM exam_results WHERE student_id = ?
            GROUP BY exam_name";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $result = $stmt->get_result();

    $summary = [];
    $totalScore = 0;
    $totalExams = 0;
    while ($row = $result->fetch_assoc()) {
        $summary[] = $row;
        $totalScore += $row['avg_score'];
        $totalExams += $row['exams_taken'];
    }
    $overallAvg = $totalExams > 0 ? round($totalScore / count($summary), 2) : 0;

    return [
        'success' => true,
        'overall_avg' => $overallAvg,
        'total_exams' => $totalExams,
        'details' => $summary
    ];
}

function getExamHistory($conn) {
    $studentId = $_GET['student_id'] ?? 0;
    $sql = "SELECT exam_date, exam_name, score, total, percentage, topic, subject 
            FROM exam_results WHERE student_id = ? ORDER BY exam_date DESC";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $res = $stmt->get_result();

    $records = [];
    while ($row = $res->fetch_assoc()){
        $records[] = $row;
    }
    echo json_encode(['success' => true, 'records' => $records]);
    exit;
}

function getStudentDetails($conn) {
    $studentId = $_GET['student_id'] ?? 0;

    $sql = "SELECT s.name, s.email, s.course, s.student_number, s.year_level, s.avatar, s.date_created, c.course_id 
            FROM students s 
            LEFT JOIN courses c ON s.course = c.course_name 
            WHERE s.student_id = ?";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $result = $stmt->get_result();

    if ($result->num_rows > 0) {
        $student = $result->fetch_assoc();

        //optional computation for average percentage
        $avgSql = "SELECT ROUND(AVG(percentage), 2) AS avg_percentage FROM exam_results WHERE student_id = ?";
        $avgStmt = $conn->prepare($avgSql);
        $avgStmt->bind_param("i", $studentId);
        $avgStmt->execute();
        $avgRes = $avgStmt->get_result()->fetch_assoc();

        $student['avg_percentage'] = $avgRes['avg_percentage'] ?? 0;

        echo json_encode(['success' => true, 'data' => $student]);
        exit;
    } else {
        echo json_encode(['success' => false, 'message' => 'Student not found']);
    }
    $stmt->close();
}

function updateStudentProfile($conn) {
    $data = json_decode(file_get_contents('php://input'), true);
    
    $studentId = $data['student_id'] ?? 0;
    $name = trim($data['name'] ?? '');
    $phone = trim($data['phone'] ?? '');

    if (!$studentId || !$name) {
        echo json_encode(['success' => false, 'message' => 'Missing student_id or name']);
        exit;
    }

    $sql = "UPDATE students SET name = ?";
    $params = [$name];
    $types = "s";

    // Only update phone if provided
    if ($phone) {
        $sql .= ", phone = ?";
        $params[] = $phone;
        $types .= "s";
    }

    $sql .= " WHERE student_id = ?";
    $params[] = $studentId;
    $types .= "i";

    $stmt = $conn->prepare($sql);
    if (!$stmt) {
        echo json_encode(['success' => false, 'message' => 'Prepare failed: ' . $conn->error]);
        exit;
    }

    $stmt->bind_param($types, ...$params);
    
    if ($stmt->execute()) {
        echo json_encode(['success' => true, 'message' => 'Profile updated successfully']);
    } else {
        echo json_encode(['success' => false, 'message' => 'Update failed: ' . $stmt->error]);
    }
    $stmt->close();
}

function updateStudentCourse($conn) {
    $studentId = $_POST['student_id'] ?? 0;
    $newCourse = $_POST['new_course'] ?? '';

    if (!$studentId || !$newCourse) {
        echo json_encode(['success' => false, 'message' => 'Missing student_id or course']);
        exit;
    }

    $sql = "UPDATE students SET course = ? WHERE student_id = ?";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("si", $newCourse, $studentId);
    
    if ($stmt->execute()) {
        echo json_encode(['success' => true, 'message' => 'Course updated successfully']);
        exit;
    } else {
        echo json_encode(['success' => false, 'message' => 'Failed to update course']);
    }
    $stmt->close();
}

function updateStudentNumber($conn) {
    $data = json_decode(file_get_contents('php://input'), true);
    $studentId = $data['student_id'] ?? 0;
    $newStudentNumber = $data['new_student_number'] ?? '';

    if (!$studentId || !$newStudentNumber) {
        echo json_encode(['success' => false, 'message' => 'Missing student_id or student number']);
        exit;
    }

    $sql = "UPDATE students SET student_number = ? WHERE student_id = ?";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("is", $newStudentNumber, $studentId);
    
    if ($stmt->execute()) {
        echo json_encode(['success' => true, 'message' => 'Student number updated successfully']);
        exit;
    } else {
        echo json_encode(['success' => false, 'message' => 'Failed to update student number']);
    }
    $stmt->close();
}

function getDashboardData($conn){
    $studentId = $_GET['student_id'] ?? 0;
    // Debug: log incoming dashboard requests and session state
    try {
        $dbg = "[" . date('Y-m-d H:i:s') . "] getDashboardData called with student_id=" . var_export($studentId, true) . "\n";
        $dbg .= "\$_SESSION: " . print_r($_SESSION, true) . "\n";
        file_put_contents(__DIR__ . '/session_debug.txt', $dbg, FILE_APPEND);
    } catch (\Throwable $e) {}
    if(empty($studentId)){
        echo json_encode(['success' => false, 'message' => 'Missing student ID']);
        exit;
    }

    $sql = "SELECT name, email, course FROM students WHERE student_id=?";
    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $student = $stmt->get_result()->fetch_assoc();


    $avgSql = "SELECT ROUND(AVG(percentage), 2) AS average FROM exam_results WHERE student_id=?";
    $avgStmt = $conn->prepare($avgSql);
    $avgStmt->bind_param("i", $studentId);
    $avgStmt->execute();
    $avgRes = $avgStmt->get_result()->fetch_assoc();
    $average = $avgRes['average'] ?? 0;

    // Get total count of exams (not just recent 5)
    $countSql = "SELECT COUNT(*) AS total_count FROM exam_results WHERE student_id=?";
    $countStmt = $conn->prepare($countSql);
    $countStmt->bind_param("i", $studentId);
    $countStmt->execute();
    $countRes = $countStmt->get_result()->fetch_assoc();
    $totalExamCount = $countRes['total_count'] ?? 0;

    $examSql = "SELECT exam_name, percentage, exam_date, topic, subject FROM exam_results 
                WHERE student_id=? ORDER BY exam_date DESC LIMIT 5";
    $examStmt = $conn->prepare($examSql);
    $examStmt->bind_param("i", $studentId);
    $examStmt->execute();
    $examRes = $examStmt->get_result();

    $recentExams = [];
    while ($row = $examRes->fetch_assoc()) {
        $recentExams[] = $row;
    }

    echo json_encode([
        'success' => true,
        'data' => [
            'student' => $student,
            'average' => $average,
            'total_exams' => $totalExamCount,
            'recent_exams' => $recentExams
        ]
    ]);
    // Log successful dashboard response for debugging
    try {
        $dbg2 = "[" . date('Y-m-d H:i:s') . "] getDashboardData response for student_id=" . var_export($studentId, true) . " recent_count=" . count($recentExams) . "\n";
        file_put_contents(__DIR__ . '/session_debug.txt', $dbg2, FILE_APPEND);
    } catch (\Throwable $e) {}
    exit;
}

function getLessonContent($topic) {
    $lessons = [
        'calculus' => [
            'title' => 'Calculus — Core Concepts',
            'intro' => "Hey! I noticed you need help with Calculus. Don’t stress — let’s break down derivatives, limits, and basic problem-solving in simple steps.",
            'blocks' => [
                [
                    'title' => 'What is a Derivative?',
                    'content' => 'A derivative represents the rate of change of a function. Example: derivative of x² is 2x. Master power rule, product rule, and chain rule.'
                ],
                [
                    'title' => 'Limits Refresher',
                    'content' => 'Limits help us understand how a function behaves near a specific value. Example: lim x→2 (x²−4)/(x−2) simplifies by factoring.'
                ],
                [
                    'title' => 'Try This:',
                    'content' => 'Find d/dx of 3x³ − 5x. (Answer: 9x² − 5)'
                ]
            ],
            'closing' => "You got this! Want a mini quiz?"
        ],

        'algebra' => [
            'title' => 'Algebra — Key Lessons',
            'intro' => "Let’s polish your Algebra fundamentals! We’ll go through linear equations, factoring, and simplification.",
            'blocks' => [
                [
                    'title' => 'Solving Linear Equations',
                    'content' => 'Keep isolating x. Example: 2x + 6 = 16 → x = 5.'
                ],
                [
                    'title' => 'Factoring Quadratics',
                    'content' => 'x² + 7x + 12 = (x+3)(x+4). Recognize patterns!'
                ]
            ],
            'closing' => "Want to practice factoring or linear equations?"
        ],
    ];

    if (!isset($lessons[$topic])) {
        return [
            'success' => false,
            'message' => 'No lesson available for this topic yet.'
        ];
    }

    return [
        'success' => true,
        'topic' => $topic,
        'lesson' => $lessons[$topic]
    ];
}

function checkSession() {
    // Return authoritative session-based login info to the frontend
    if (session_status() === PHP_SESSION_NONE) session_start();
    if (isset($_SESSION['student_id'])) {
        return [
            'success' => true,
            'student_id' => $_SESSION['student_id'],
            'name' => $_SESSION['student_name'] ?? null,
            'email' => $_SESSION['student_email'] ?? null
        ];
    }
    return ['success' => false, 'message' => 'No active session'];
}

function tutorQA($topic, $question) {
    global $GEMINI_API_KEY;
    if (!$GEMINI_API_KEY) {
        return [
            "success" => false,
            "answer" => "AI service unavailable. Missing Gemini key."
        ];
    }

    //restrict non-related questions
    if (!empty($topic)) {
        $topicKeywords = [
            "algebra" => ["solve", "equation", "x", "variable", "polynomial", "factor"],
            "geometry" => [
                "triangle", "angle", "circle", "area",
                "perimeter", "shape", "sides", "radius", "diameter"
            ],
            "calculus" => ["derivative", "integral", "limit", "rate of change"],
            "logic" => ["statement", "truth table", "logic", "proposition", "if and only if"],
            "statistics" => ["mean", "median", "mode", "probability", "distribution"],
        ];

        $qLower = strtolower($question);
        $currentTopic = strtolower($topic);

        // Check if question contains keywords from OTHER topics
        foreach ($topicKeywords as $t => $keywords) {
            if ($t === $currentTopic) continue;
            foreach ($keywords as $word) {
                if(strpos($qLower, $word) !== false){
                    return [
                        "success" => true,
                        "answer" => "That question belongs to **" . ucfirst($t) . 
                        "**, but we’re currently studying **" . ucfirst($currentTopic) . 
                        "**.\n\nAsk something related to **" . ucfirst($currentTopic) . "** so I can help you better!"
                    ];
                }
            }
        }
    }

    $MODEL = "gemini-pro";
    $prompt = "
        You are ExamiQ+, a helpful and clear math tutor.
        Topic: $topic
        Student question: $question

        Provide a correct, step-by-step explanation.
        If the question is conceptual, give a simple explanation.
        If the question is a calculation, solve it clearly.
    ";

    $payload = [
        "contents" => [
            [
                "parts" => [
                    ["text" => $prompt]
                ]
            ]
        ]
    ];

    $url = "https://generativelanguage.googleapis.com/v1beta/models/$MODEL:generateContent?key=$GEMINI_API_KEY";

    $ret = call_gemini_api_with_fallback($url, $payload, $MODEL, 2);
    if (!$ret['success']) {
        error_log("Gemini tutorQA error: " . ($ret['error'] ?? json_encode($ret['decoded'] ?? $ret['raw'] ?? '')));
        return [
            "success" => false,
            "answer" => "AI service temporarily unavailable. Please try again later.",
            'raw' => $ret['raw'] ?? null,
            'error' => $ret['error'] ?? null
        ];
    }

    $decoded = $ret['decoded'];
    $answer = $decoded['candidates'][0]['content']['parts'][0]['text'] ?? ($ret['raw'] ?? "I'm not sure, but try rephrasing your question.");

    return [
        "success" => true,
        "answer" => $answer,
        'raw' => $ret['raw'] ?? null
    ];
}


function getFailedConcepts($conn, $studentId) {
    $sql = "SELECT submission_details FROM exam_results 
            WHERE student_id = ? 
            ORDER BY exam_date DESC 
            LIMIT 5";

    $stmt = $conn->prepare($sql);
    $stmt->bind_param("i", $studentId);
    $stmt->execute();
    $result = $stmt->get_result();

    $failed = [];
    while($row = $result->fetch_assoc()){
        $submission = json_decode($row['submission_details'], true);
        foreach ($submission as $q) {
            if (!$q['isCorrect'] && !empty($q['concept_tag']) && $q['concept_tag'] !== "null") {
                $failed[] = $q['concept_tag'];
            }
        }
    }
    $failed = array_unique($failed);
    $failed = array_values($failed);
    return [
        'success' => true,
        'failed_concepts' => $failed
    ];
}

/**
 * Try API call with fallback models and API versions if the primary model fails
 * Returns array: ['success'=>bool, 'decoded'=>array|null, 'raw'=>string|null, 'error'=>string|null, 'model_used'=>string]
 */
function call_gemini_api_with_fallback($baseUrl, $payload, $primaryModel, $maxRetries = 2) {
    global $GEMINI_API_KEY;
    
    // First, try to get list of actually available models from the API
    $available = get_available_gemini_models();
    
    // If we got available models, use only those
    if (!empty($available)) {
        $modelsToTry = [];
        // Put primary model first if it's in the available list
        if (in_array($primaryModel, $available)) {
            $modelsToTry[] = $primaryModel;
        }
        // Add remaining available models
        foreach ($available as $model) {
            if (!in_array($model, $modelsToTry)) {
                $modelsToTry[] = $model;
            }
        }
        error_log("Using discovered models: " . implode(', ', $modelsToTry));
    } else {
        // Fallback to configured models if discovery failed
        error_log("Model discovery failed, using configured models");
        $modelsToTry = [$primaryModel];
        foreach (GEMINI_MODELS as $model) {
            if ($model !== $primaryModel) {
                $modelsToTry[] = $model;
            }
        }
    }
    
    // Also try API versions
    $apiVersions = ['v1beta', 'v1'];
    
    $lastError = null;
    foreach ($apiVersions as $apiVersion) {
        foreach ($modelsToTry as $model) {
            error_log("call_gemini_api: Trying model: $model with API version: $apiVersion");
            
            // Rebuild URL with current API version and model
            $url = preg_replace(
                '/\/v1(beta)?\//i',
                "/$apiVersion/",
                preg_replace(
                    '/\/models\/[^\/]+:/i',
                    "/models/$model:",
                    $baseUrl
                )
            );
            
            $result = call_gemini_api($url, $payload, 1); // Try 1 retry per model before switching
            
            if ($result['success']) {
                error_log("call_gemini_api: Success with model: $model on $apiVersion");
                $result['model_used'] = $model;
                $result['api_version'] = $apiVersion;
                return $result;
            }
            
            $lastError = $result['error'] ?? 'Unknown error';
            error_log("call_gemini_api: Model $model ($apiVersion) failed: $lastError");
        }
    }
    
    error_log("call_gemini_api: All models and API versions failed");
    return ['success' => false, 'error' => $lastError, 'model_used' => null, 'http_code' => 0];
}

/**
 * Helper to call Gemini API with simple retry/backoff and uniform return shape.
 * Returns array: ['success'=>bool, 'decoded'=>array|null, 'raw'=>string|null, 'error'=>string|null]
 */
function call_gemini_api($url, $payload, $maxRetries = 2) {
    $attempt = 0;
    $lastRaw = null;
    $lastErr = null;
    while ($attempt <= $maxRetries) {
        $attempt++;
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => [ "Content-Type: application/json" ],
            CURLOPT_POSTFIELDS => json_encode($payload),
            CURLOPT_TIMEOUT => 60,
            CURLOPT_CONNECTTIMEOUT => 10,
            CURLOPT_HEADER => true, // capture headers so we can honor Retry-After
        ]);

        $result = curl_exec($ch);
        $curlErr = curl_errno($ch) ? curl_error($ch) : null;
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $responseHeaders = substr($result, 0, $headerSize);
        $body = substr($result, $headerSize);
        curl_close($ch);

        $lastRaw = $body;
        if ($curlErr) {
            $lastErr = "cURL error: " . $curlErr;
            error_log("call_gemini_api attempt $attempt cURL error: " . $curlErr);
        } else {
            $decoded = json_decode($body, true);
            // If API returns an error field (e.g., quota or overloaded), treat as failure
            if (is_array($decoded) && isset($decoded['error'])) {
                $errcode = $decoded['error']['code'] ?? $httpCode;
                $errmsg = $decoded['error']['message'] ?? json_encode($decoded['error']);
                $lastErr = "API error: " . $errmsg;
                error_log("call_gemini_api attempt $attempt API error (HTTP $httpCode): " . $errmsg);
                // Treat as retriable for server-side errors
                if ($errcode == 503 || ($httpCode >= 500 && $httpCode < 600) || $httpCode == 429) {
                    // honor Retry-After header if present
                    $retryAfter = null;
                    if (preg_match('/Retry-After:\s*(\d+)/i', $responseHeaders, $m)) {
                        $retryAfter = (int)$m[1];
                    } elseif (preg_match('/Retry-After:\s*(.+)/i', $responseHeaders, $m2)) {
                        $date = trim($m2[1]);
                        $ts = strtotime($date);
                        if ($ts !== false) $retryAfter = max(0, $ts - time());
                    }
                    if ($retryAfter !== null && $retryAfter > 0) {
                        // sleep respecting Retry-After
                        sleep(min($retryAfter, 30));
                        continue;
                    }
                    // exponential backoff with jitter
                    $base = min(pow(2, $attempt - 1), 16);
                    $jitter = rand(100, 1000) / 1000; // 0.1-1.0s
                    usleep(($base + $jitter) * 1000000);
                    continue;
                }
                return ['success' => false, 'decoded' => $decoded, 'raw' => $body, 'error' => $lastErr, 'http_code' => $httpCode];
            }

            // If HTTP 429 or 5xx, retry with backoff
            if ($httpCode == 429 || ($httpCode >= 500 && $httpCode < 600)) {
                // parse Retry-After
                $retryAfter = null;
                if (preg_match('/Retry-After:\s*(\d+)/i', $responseHeaders, $m)) {
                    $retryAfter = (int)$m[1];
                } elseif (preg_match('/Retry-After:\s*(.+)/i', $responseHeaders, $m2)) {
                    $date = trim($m2[1]);
                    $ts = strtotime($date);
                    if ($ts !== false) $retryAfter = max(0, $ts - time());
                }
                if ($retryAfter !== null && $retryAfter > 0) {
                    sleep(min($retryAfter, 30));
                    continue;
                }
                $base = min(pow(2, $attempt - 1), 16);
                $jitter = rand(100, 1000) / 1000;
                usleep(($base + $jitter) * 1000000);
                continue;
            }

            // Success
            return ['success' => true, 'decoded' => $decoded, 'raw' => $body, 'error' => null, 'http_code' => $httpCode];
        }

        // If we reached here, there was a curlErr and we'll retry if attempts remain
        if ($attempt <= $maxRetries) {
            sleep(min(2 * $attempt, 8));
            continue;
        }
    }

    return ['success' => false, 'decoded' => null, 'raw' => $lastRaw, 'error' => $lastErr, 'http_code' => $httpCode ?? 0];
}

/**
 * Remove common Markdown markers while keeping the inner text.
 * This is conservative: it preserves the content but strips **bold**, *italic*, `code`, ```fences```, links, headings, etc.
 * IMPORTANT: Preserves mathematical notation with subscripts/superscripts (underscores and carets in math context)
 */
function stripMarkdown($s) {
    if (!is_string($s) || $s === '') return $s;

    // Remove fenced code blocks but keep inner content
    $s = preg_replace('/```\s*(.*?)\s*```/s', '$1', $s);
    // Remove inline code backticks
    $s = preg_replace('/`([^`]*)`/', '$1', $s);
    // Remove bold/italic markers (**, __, *, _) but preserve mathematical notation
    // Only remove ** for bold
    $s = preg_replace('/\*\*(.*?)\*\*/s', '$1', $s);
    // Only remove __ (double underscore) for italic, not single _ (used in math)
    $s = preg_replace('/__(.*?)__/s', '$1', $s);
    // Remove * for italic (not part of math)
    $s = preg_replace('/\*(.*?)\*/s', '$1', $s);
    // DO NOT remove single underscores - they're used for mathematical subscripts (x_2, etc)
    // $s = preg_replace('/_(.*?)_/s', '$1', $s);  // REMOVED - breaks math notation
    // Remove strike-through
    $s = preg_replace('/~~(.*?)~~/s', '$1', $s);
    // Convert markdown links [text](url) -> text
    $s = preg_replace('/\[([^\]]+)\]\([^\)]+\)/', '$1', $s);
    // Remove leading heading markers
    $s = preg_replace('/^#{1,6}\s*/m', '', $s);
    // Trim whitespace
    return trim($s);
}

function chatGPT($input) {
    global $GEMINI_API_KEY;

    $MODEL = "gemini-pro";
    if (!$GEMINI_API_KEY) {
        return ["success" => false, "message" => "Missing Gemini API key."];
    }

    $isAdaptive = isset($input['question']) &&
                  isset($input['userAnswer']) &&
                  isset($input['correctAnswer']);

    if($isAdaptive){
        $prompt = buildAdaptivePrompt(
            $input['topic'] ?? '',  
            $input['question'],
            $input['userAnswer'],
            $input['correctAnswer'],
            $input['confidence'] ?? 'medium',
            $input['patterns'] ?? []
        );
    }else{
        $userMessage = $input['message'] ?? "hello";

        $prompt = "
            You are ExamiQ+, a friendly and clear math tutor. Your primary goal is to simplify math concepts and show clear, step-by-step solutions.

            ### RULES FOR MATH NOTATION
            - Do NOT use LaTeX, $ symbols, or complex math notation.
            - Use plain text formulas only. Example: area = length x width
            - For multiplication, use 'x' or 'times'. For division, use '/' or 'divided by'.
            - For exponents (like squared or cubed), use the caret symbol followed by the power. Example: m^2, ft^3, 2^4
            - If the student seems confused, rewrite formulas in simple English.

            ### RULES FOR TEXT CLARITY (Markdown)
            - Use **bolding** for final answers, key terms, and formula names.
            - Use *italic* text to emphasize important warnings or concepts.
            - Use numbered lists or bullet points to show steps clearly.

            ### RESPONSE STYLE
            - **Keep it Simple:** Keep explanations simple unless the user asks for detailed steps.
            - **Adaptive Difficulty:** If a problem requires more than three main steps, break the explanation into smaller, numbered chunks and check for understanding before proceeding.
            - **If Calculation is Requested:** Show clean, clear, step-by-step work using Markdown lists.
            - **If Concept is Requested:** Give a short definition + one simple example.
            - **Always Friendly:** Maintain a friendly, supportive, and easy-to-understand tone.
            - **Handling Confusion:** If the user states they are confused, provide an analogy or rephrase the explanation in simpler terms immediately.

            ### INITIAL ACTION
            - **Start Strong:** If this is the very first interaction, begin the response by enthusiastically greeting the student and asking, 'What math problem or concept can I help you tackle today?'

            User says: $userMessage

            Now respond clearly, strictly following all the rules above.
            ";
    }

    // Gemini API call using centralized helper with retries
    $payload = [
        "contents" => [
            [
                "parts" => [
                    ["text" => $prompt]
                ]
            ]
        ]
    ];

    $url = "https://generativelanguage.googleapis.com/v1beta/models/$MODEL:generateContent?key=$GEMINI_API_KEY";
    $ret = call_gemini_api_with_fallback($url, $payload, $MODEL, 2);
    if (!$ret['success']) {
        error_log("Gemini chatGPT error: " . ($ret['error'] ?? json_encode($ret['decoded'] ?? $ret['raw'] ?? '')));
        return ["success" => false, "message" => "AI service temporarily unavailable. Please try again later.", 'raw' => $ret['raw'] ?? null, 'error' => $ret['error'] ?? null];
    }

    $data = $ret['decoded'];
    $answer = $data['candidates'][0]['content']['parts'][0]['text'] ?? ($ret['raw'] ?? "No response from AI.");

    return [
        "success" => true,
        "answer" => $answer,
        "raw" => $ret['raw'] ?? null
    ];
}


function generateAIFeedbackPHP($topic, $questionOrSubmission, $userAnswer = null, $correctAnswer = null, $confidence = 'medium', $patterns = [], $progressive = false) {
    global $GEMINI_API_KEY;
    $MODEL = "gemini-pro";

    // Normalize patterns text
    $patternText = empty($patterns) ? "No recurring mistakes yet." : "Detected recurring mistakes:\n- " . implode("\n- ", $patterns);

    // If caller passed a submission array, build a batch prompt
    $isBatch = is_array($questionOrSubmission);

    if ($isBatch) {
        global $conn;
        $submission = $questionOrSubmission;

        // If the submission is large, chunk it into smaller batches to avoid model token limits and timeouts
        $CHUNK_SIZE = 6; // safe default; tune upward if your questions are very short
        $allItems = [];
        $allOverall = [];

        $chunks = array_chunk($submission, $CHUNK_SIZE);
        $totalChunks = count($chunks);
        foreach ($chunks as $chunkIndex => $chunk) {
            // Build itemsText for this chunk
            $itemsText = "";
            $count = 0;
            foreach ($chunk as $it) {
                $isCorrect = isset($it['isCorrect']) ? $it['isCorrect'] : false;
                if ($isCorrect) continue; // only request recommendations for incorrect answers
                $count++;
                $q = $it['question'] ?? ($it['questionText'] ?? "(no question text)");
                $ua = $it['userAnswer'] ?? $it['user_answer'] ?? "";
                $ca = $it['correctAnswer'] ?? $it['correct_answer'] ?? $it['correct'] ?? "";
                $tag = $it['concept_tag'] ?? ($it['conceptTag'] ?? null);

                $uaText = '';
                $caText = '';
                $qid = $it['questionId'] ?? $it['question_id'] ?? null;
                if ($qid && is_numeric($qid)) {
                    $qstmt = $conn->prepare("SELECT option_a, option_b, option_c, option_d FROM questions WHERE question_id = ? LIMIT 1");
                    if ($qstmt) {
                        $qstmt->bind_param('i', $qid);
                        if ($qstmt->execute()) {
                            $qres = $qstmt->get_result();
                            if ($rowQ = $qres->fetch_assoc()) {
                                $choicesMap = [
                                    'A' => $rowQ['option_a'] ?? '',
                                    'B' => $rowQ['option_b'] ?? '',
                                    'C' => $rowQ['option_c'] ?? '',
                                    'D' => $rowQ['option_d'] ?? ''
                                ];
                                $uaLetter = strtoupper(trim((string)$ua));
                                $caLetter = strtoupper(trim((string)$ca));
                                $uaText = $choicesMap[$uaLetter] ?? '';
                                $caText = $choicesMap[$caLetter] ?? '';
                            }
                        }
                        $qstmt->close();
                    }
                }

                $displayUA = $ua;
                if (!empty($uaText)) $displayUA = trim($ua . ' (' . $uaText . ')');
                $displayCA = $ca;
                if (!empty($caText)) $displayCA = trim($ca . ' (' . $caText . ')');

                $itemsText .= "Item $count:\nQuestion: $q\nUser Answer: $displayUA\nCorrect Answer: $displayCA\nConcept Tag: " . ($tag ?? "(none)") . "\n\n";
            }

            if ($itemsText === "") {
                // nothing to analyze in this chunk
                continue;
            }

            // Build prompt for this chunk (strict JSON requested)
            $prompt = "You are ExamiQ+, an adaptive mathematics tutor focused on the topic: $topic.\n\n" .
                "Below are the incorrect answers the student made (only incorrect items). For each item:\n" .
                "1. Explain clearly WHY the answer is wrong\n" .
                "2. Provide the CORRECT ANSWER\n" .
                "3. Show detailed step-by-step corrections (use actual line breaks, not \\\\n)\n" .
                "4. Recommend 1-3 specific concepts to review and an ideal difficulty level\n\n" .
                "CRITICAL JSON FORMATTING RULES:\n" .
                "- Use proper JSON string escaping. LaTeX expressions MUST be properly escaped for JSON.\n" .
                "- For 'correction_steps': use ACTUAL newlines in the JSON string (not literal \\\\n)\n" .
                "- Preserve all mathematical notation and LaTeX carefully\n" .
                "- Do NOT add extra backslashes\n\n" .
                "Return ONLY a single JSON object with this structure:\n" .
                "{\n" .
                "  \"success\": true,\n" .
                "  \"topic\": \"<topic_name>\",\n" .
                "  \"items\": [\n" .
                "    {\n" .
                "      \"question\": \"<the_question_text>\",\n" .
                "      \"user_answer\": \"<what_student_answered>\",\n" .
                "      \"correct_answer\": \"<the_correct_answer>\",\n" .
                "      \"why_wrong\": \"<explanation_of_error>\",\n" .
                "      \"correction_steps\": \"Step 1: ...\\nStep 2: ...\\nStep 3: ...\",\n" .
                "      \"recommended_concepts\": [\"concept1\", \"concept2\"],\n" .
                "      \"recommended_difficulty\": \"easy|medium|hard\"\n" .
                "    }\n" .
                "  ],\n" .
                "  \"overall_recommendations\": [\"...\", \"...\"]\n" .
                "}\n\n" .
                "Here are the items to analyze (do not invent additional items):\n\n" . $itemsText . "\nPatterns:\n$patternText\n\nFollow the JSON schema exactly. Return ONLY the JSON object.\n";

            $payload = [
                "contents" => [
                    [
                        "parts" => [
                            ["text" => $prompt]
                        ]
                    ]
                ]
            ];

            $url = "https://generativelanguage.googleapis.com/v1beta/models/$MODEL:generateContent?key=$GEMINI_API_KEY";
            $ret = call_gemini_api_with_fallback($url, $payload, $MODEL, 2);
            if (!$ret['success']) {
                error_log("Gemini ai_feedback chunk $chunkIndex error: " . ($ret['error'] ?? json_encode($ret['decoded'] ?? $ret['raw'] ?? '')));
                // continue to next chunk; don't fail the whole request immediately
                // If progressive mode, emit an error chunk so frontend can show progress
                if ($progressive) {
                    $out = ['chunk_index' => $chunkIndex + 1, 'total_chunks' => $totalChunks, 'error' => $ret['error'] ?? 'API error', 'items' => []];
                    echo json_encode($out) . "\n";
                    @ob_flush(); @flush();
                }
                continue;
            }

            $decoded = $ret['decoded'];
            $raw = $decoded['candidates'][0]['content']['parts'][0]['text'] ?? $ret['raw'] ?? '';

            // Extract first JSON object from output
            if (preg_match('/\{(?:[^{}]|(?R))*\}/x', $raw, $match)) {
                $jsonText = $match[0];
            } else {
                // couldn't parse this chunk; include raw as a fallback item
                $chunkItems = [[
                    'question' => 'AI chunk parsing error',
                    'user_answer' => '',
                    'correct_answer' => '',
                    'why_wrong' => is_string($raw) ? trim($raw) : '',
                    'correction_steps' => '',
                    'recommended_concepts' => [],
                    'recommended_difficulty' => ''
                ]];
                if ($progressive) {
                    $out = ['chunk_index' => $chunkIndex + 1, 'total_chunks' => $totalChunks, 'items' => $chunkItems, 'overall' => []];
                    echo json_encode($out) . "\n";
                    @ob_flush(); @flush();
                } else {
                    $allItems = array_merge($allItems, $chunkItems);
                }
                continue;
            }

            $json = json_decode($jsonText, true);
            if (json_last_error() !== JSON_ERROR_NONE || !is_array($json)) {
                // salvage common alternate shapes
                $chunkItems = [];
                if (isset($json['results']) && is_array($json['results'])) {
                    foreach ($json['results'] as $r) {
                        $chunkItems[] = [
                            'question' => $r['question'] ?? ($r['prompt'] ?? ''),
                            'user_answer' => $r['user_answer'] ?? ($r['userAnswer'] ?? ''),
                            'correct_answer' => $r['correct_answer'] ?? ($r['correctAnswer'] ?? ''),
                            'why_wrong' => $r['why_wrong'] ?? ($r['explanation'] ?? ''),
                            'correction_steps' => $r['correction_steps'] ?? ($r['steps'] ?? ''),
                            'recommended_concepts' => $r['recommended_concepts'] ?? [],
                            'recommended_difficulty' => $r['recommended_difficulty'] ?? ''
                        ];
                    }
                } else {
                    // fallback: add raw
                    $chunkItems[] = [
                        'question' => 'Detailed AI feedback',
                        'user_answer' => '',
                        'correct_answer' => '',
                        'why_wrong' => is_string($raw) ? trim($raw) : '',
                        'correction_steps' => '',
                        'recommended_concepts' => [],
                        'recommended_difficulty' => ''
                    ];
                }
                if ($progressive) {
                    $out = ['chunk_index' => $chunkIndex + 1, 'total_chunks' => $totalChunks, 'items' => $chunkItems, 'overall' => $json['overall_recommendations'] ?? ($json['recommendations'] ?? [])];
                    echo json_encode($out) . "\n";
                    @ob_flush(); @flush();
                } else {
                    $allItems = array_merge($allItems, $chunkItems);
                }
            } else {
                // extract items
                $chunkItems = [];
                if (isset($json['items']) && is_array($json['items'])) {
                    foreach ($json['items'] as $it) {
                        $chunkItems[] = $it;
                    }
                }
                // Normalize items before streaming
                $chunkItems = normalizeAIFeedbackItems($chunkItems);
                
                if ($progressive) {
                    $out = ['chunk_index' => $chunkIndex + 1, 'total_chunks' => $totalChunks, 'items' => $chunkItems, 'overall' => $json['overall_recommendations'] ?? ($json['recommendations'] ?? [])];
                    echo json_encode($out) . "\n";
                    @ob_flush(); @flush();
                } else {
                    foreach ($chunkItems as $it) $allItems[] = $it;
                }
                if (isset($json['overall_recommendations']) && is_array($json['overall_recommendations'])) {
                    $allOverall = array_merge($allOverall, $json['overall_recommendations']);
                } elseif (isset($json['recommendations']) && is_array($json['recommendations'])) {
                    $allOverall = array_merge($allOverall, $json['recommendations']);
                }
            }
        }

        if (empty($allItems)) {
            return ["success" => false, "message" => "AI failed to generate detailed feedback for the submission. Try again later."];
        }

        // dedupe overall recommendations
        $allOverall = array_values(array_unique($allOverall));
        return normalizeAIFeedbackResponse(["success" => true, 'items' => $allItems, 'overall_recommendations' => $allOverall, 'raw_chunks' => null]);

    } else {
        // Single question flow (backwards compatible) — build single-item prompt
        $q = $questionOrSubmission ?? '(no question text)';
        $ua = $userAnswer ?? '';
        $ca = $correctAnswer ?? '';

        $prompt = "You are ExamiQ+, an adaptive mathematics tutor for topic: $topic.\n\n" .
            "Analyze the single student response below:\n" .
            "- Explain clearly WHY the answer is wrong (if it is wrong)\n" .
            "- Provide the CORRECT ANSWER\n" .
            "- Show detailed step-by-step corrections (use actual line breaks in JSON, not literal \\\\n)\n" .
            "- Recommend 1-3 specific concepts to review and an ideal difficulty (easy|medium|hard)\n\n" .
            "CRITICAL JSON FORMATTING RULES:\n" .
            "- Use proper JSON string escaping. LaTeX expressions MUST be properly escaped for JSON.\n" .
            "- For 'correction_steps': use ACTUAL newlines in the JSON string (not literal \\\\n)\n" .
            "- Preserve all mathematical notation and LaTeX carefully\n" .
            "- Do NOT add extra backslashes\n\n" .
            "Return ONLY a JSON object (no extra text) with this structure:\n" .
            "{\n" .
            "  \"success\": true,\n" .
            "  \"topic\": \"<topic_name>\",\n" .
            "  \"items\": [\n" .
            "    {\n" .
            "      \"question\": \"<the_question_text>\",\n" .
            "      \"user_answer\": \"<what_student_answered>\",\n" .
            "      \"correct_answer\": \"<the_correct_answer>\",\n" .
            "      \"why_wrong\": \"<explanation_of_error>\",\n" .
            "      \"correction_steps\": \"Step 1: ...\\nStep 2: ...\\nStep 3: ...\",\n" .
            "      \"recommended_concepts\": [\"concept1\"],\n" .
            "      \"recommended_difficulty\": \"easy|medium|hard\"\n" .
            "    }\n" .
            "  ],\n" .
            "  \"overall_recommendations\": [\"...\"]\n" .
            "}\n\n" .
            "Student data:\n" .
            "Question: $q\n" .
            "Student Answer: $ua\n" .
            "Correct Answer: $ca\n" .
            "Confidence: $confidence\n" .
            "Patterns:\n$patternText\n\n" .
            "Follow the JSON schema exactly. Return ONLY the JSON object.\n";
    }

    // Call Gemini
    $payload = [
        "contents" => [
            [
                "parts" => [
                    ["text" => $prompt]
                ]
            ]
        ]
    ];

    $url = "https://generativelanguage.googleapis.com/v1beta/models/$MODEL:generateContent?key=$GEMINI_API_KEY";
    $ret = call_gemini_api_with_fallback($url, $payload, $MODEL, 2);
    if (!$ret['success']) {
        error_log("Gemini ai_feedback error: " . ($ret['error'] ?? json_encode($ret['decoded'] ?? $ret['raw'] ?? '')));
        return ["success" => false, "message" => "AI service temporarily unavailable. Please try again later.", 'raw' => $ret['raw'] ?? null, 'error' => $ret['error'] ?? null];
    }

    // Extract Gemini text output
    $decoded = $ret['decoded'];
    $raw = $decoded['candidates'][0]['content']['parts'][0]['text'] ?? $ret['raw'] ?? '';

    // Extract first JSON object from output (robust)
    if (preg_match('/\{(?:[^{}]|(?R))*\}/x', $raw, $match)) {
        $jsonText = $match[0];
    } else {
        return ["success" => false, "message" => "AI did not return parsable JSON.", "raw" => $raw];
    }

    $json = json_decode($jsonText, true);
    if (json_last_error() !== JSON_ERROR_NONE || !is_array($json)) {
        return ["success" => false, "message" => "Failed to decode AI JSON output.", "raw" => $jsonText];
    }

    // Ensure basic shape — attempt to salvage if 'items' missing
    if (!isset($json['items']) || !is_array($json['items'])) {
        error_log("AI JSON missing 'items'; attempting to salvage response.");

        $items = [];

        // Common alternative keys the model might return
        if (isset($json['results']) && is_array($json['results'])) {
            foreach ($json['results'] as $r) {
                $items[] = [
                    'question' => $r['question'] ?? ($r['prompt'] ?? ''),
                    'user_answer' => $r['user_answer'] ?? ($r['userAnswer'] ?? ''),
                    'correct_answer' => $r['correct_answer'] ?? ($r['correctAnswer'] ?? ''),
                    'why_wrong' => $r['why_wrong'] ?? ($r['explanation'] ?? ''),
                    'correction_steps' => $r['correction_steps'] ?? ($r['steps'] ?? ''),
                    'recommended_concepts' => $r['recommended_concepts'] ?? [],
                    'recommended_difficulty' => $r['recommended_difficulty'] ?? ''
                ];
            }
        } elseif (isset($json['questions']) && is_array($json['questions'])) {
            foreach ($json['questions'] as $r) {
                $items[] = [
                    'question' => $r['text'] ?? ($r['question'] ?? ''),
                    'user_answer' => $r['user_answer'] ?? '',
                    'correct_answer' => $r['correct_answer'] ?? '',
                    'why_wrong' => $r['why'] ?? ($r['explanation'] ?? ''),
                    'correction_steps' => $r['correction_steps'] ?? '',
                    'recommended_concepts' => $r['recommended_concepts'] ?? [],
                    'recommended_difficulty' => $r['recommended_difficulty'] ?? ''
                ];
            }
        } else {
            // Fallback: package the raw AI text into a single item so frontend can show something useful
            $items[] = [
                'question' => 'Detailed AI feedback',
                'user_answer' => '',
                'correct_answer' => '',
                'why_wrong' => is_string($raw) ? trim($raw) : (is_array($json) ? json_encode($json) : ''),
                'correction_steps' => '',
                'recommended_concepts' => [],
                'recommended_difficulty' => ''
            ];
        }

        // Attach any overall recommendations if present
        $overall = $json['overall_recommendations'] ?? ($json['recommendations'] ?? []);

        return normalizeAIFeedbackResponse(array_merge(['success' => true, 'raw' => $raw], ['items' => $items, 'overall_recommendations' => $overall]));
    }

    // Return parsed structured response
    return normalizeAIFeedbackResponse(array_merge(['success' => true, 'raw' => $raw], $json));
}

function buildAdaptivePrompt($topic, $question, $userAnswer, $correctAnswer, $confidence, $patterns) {

    $patternText = empty($patterns)
        ? "No major recurring mistakes detected yet."
        : "Here are recurring mistake patterns: \n- " . implode("\n- ", $patterns);

    return "
You are ExamiQ+, an adaptive, friendly, and highly flexible math tutor.
Your job is to help students learn clearly, accurately, and at the level they ask for.

### CORE BEHAVIOR (GLOBAL RULES)
- Match the student's requested style.
- If the student wants something 'brief', respond in 1–3 sentences.
- If correction is needed, explain gently and clearly.
- If teaching a process, provide step-by-step reasoning.
- Keep explanations simple and friendly unless advanced detail is requested.
- Never overwhelm the student unless they explicitly ask for deep explanation.
- Avoid LaTeX, special math symbols, or overly formal notation unless the student specifically asks for it.
- ALWAYS USE PROPER MATHEMATICAL SYMBOLS in all explanations (do NOT use plain-text notation):
  For square root use √ NOT sqrt. For exponents use ² ³ NOT caret. For multiply use × NOT asterisk.
  For divide use ÷ NOT slash. Use ± ≈ ≤ ≥ for operators, π for pi, α β γ δ for Greek letters.
  Use x₁ x₂ for subscripts NOT x1, x2. Use x² y³ NOT x^2, y^3.
  Use ∑ for summation, ∫ for integration, ½ ¾ ⅓ for fractions.
  Example: √((x₂ - x₁)² + (y₂ - y₁)²) NOT sqrt((x2 - x1)^2 + (y2 - y1)^2)
- Use proper mathematical symbols instead of plain text.
- If the student seems confused, still use proper symbols but explain what they mean. (e.g., “the square root symbol √ means we need to find what”).

---

### TOPIC RESTRICTION (IMPORTANT)
You must ONLY answer questions related to this topic: **$topic**.

If the student asks something outside this topic:
- Do NOT answer the unrelated question.
- Redirect them politely.
- Keep them focused on the current lesson.

Example:
\"That question is outside the topic we’re reviewing. Right now we are learning **$topic**. 
Please ask something related so I can help you better.\"

---

### DYNAMIC FEEDBACK RULES  
When the student is incorrect:
- Give step-by-step solutions.
- Explain their mistake clearly.
- If confidence is LOW → simpler explanations.
- If confidence is HIGH → deeper reasoning.
- Tailor tone to confidence.

---

### SKILL & PRACTICE RECOMMENDATION RULES
Always include:
- What topics the student should practice next
- Ideal difficulty level
- Concepts needing immediate attention
- Recommended number of practice questions

---

### PERFORMANCE PATTERNS
You analyze ongoing mistakes:
$patternText

Provide insights such as:
- What steps they consistently get wrong
- What concepts they confuse
- What topics they are strong/weak in

---

### CONFIDENCE-ADAPTIVE BEHAVIOR
- Low confidence → slow, simple, supportive.
- Medium confidence → balanced explanation.
- High confidence → deeper, more advanced reasoning.
- Fast answering → remind them to check work.
- Hesitation → offer confidence-building tips.

---

### STUDENT DATA
Topic: $topic
Question: $question
Student Answer: $userAnswer
Correct Answer: $correctAnswer
Confidence Level: $confidence

---

Now generate adaptive, personalized feedback based on all rules above.
";
}

function startExam($conn) {
    try {
        $data = json_decode(file_get_contents('php://input'), true);
        
        $studentId = $data['student_id'] ?? 0;
        $topic = $data['topic'] ?? '';
        $difficulty = $data['difficulty'] ?? '';
        
        if (empty($studentId)) {
            return ['success' => false, 'message' => 'Student ID is required'];
        }
        if (empty($topic)) {
            return ['success' => false, 'message' => 'Topic is required'];
        }
        if (empty($difficulty)) {
            return ['success' => false, 'message' => 'Difficulty is required'];
        }
        
        $startTime = date('Y-m-d H:i:s');
        $duration = 900; // 15 minutes in seconds
        
        return [
            'success' => true,
            'message' => 'Exam started successfully',
            'start_time' => $startTime,
            'duration' => $duration
        ];
        
    } catch (Exception $e) {
        return ['success' => false, 'message' => 'Error starting exam: ' . $e->getMessage()];
    }
}

/**
 * Normalize AI-generated feedback items
 * Fixes formatting issues like:
 * - Literal \n characters that should be actual newlines
 * - Extra escaping in LaTeX expressions
 * - Malformed JSON strings
 */
function normalizeAIFeedbackItems($items) {
    if (!is_array($items)) return $items;
    
    $normalized = [];
    foreach ($items as $item) {
        if (!is_array($item)) {
            $normalized[] = $item;
            continue;
        }
        
        $normalizedItem = [];
        foreach ($item as $key => $value) {
            if (!is_string($value)) {
                $normalizedItem[$key] = $value;
                continue;
            }
            
            // For correction_steps and why_wrong: convert literal \n to actual newlines
            if ($key === 'correction_steps' || $key === 'why_wrong') {
                // Replace literal \n (backslash followed by n) with actual newline
                $value = str_replace('\n', "\n", $value);
                
                // Normalize multiple consecutive newlines (keep max 2)
                $value = preg_replace('/\n{3,}/', "\n\n", $value);
            }
            
            $normalizedItem[$key] = $value;
        }
        
        $normalized[] = $normalizedItem;
    }
    
    return $normalized;
}

/**
 * Normalize entire AI feedback response before returning to client
 * Applies formatting fixes to all items
 */
function normalizeAIFeedbackResponse($response) {
    if (!is_array($response) || !isset($response['items'])) {
        return $response;
    }
    
    $response['items'] = normalizeAIFeedbackItems($response['items']);
    return $response;
}

?>

