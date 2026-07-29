"""BSEd Mathematics research instruments for thesis fieldwork (survey + interview)."""

STUDENT_SURVEY_META = {
    "title": "BSEd Mathematics Student Survey",
    "subtitle": "ExamiQ+ Pilot Study — Pre- and Post-Study Instruments",
    "purpose": (
        "This survey supports the ExamiQ+ thesis pilot focused on BS Secondary Education "
        "Major in Mathematics students. It captures study habits, calibration and "
        "metacognition, BSEd-specific learning needs, and feedback for improving the "
        "platform beyond basic review. Administer the pre-survey before first use and "
        "the post-survey after 2–4 weeks of ExamiQ use."
    ),
    "likert_note": (
        "Unless marked otherwise, use a 1–5 Likert scale: "
        "1 = Strongly disagree, 2 = Disagree, 3 = Neutral, 4 = Agree, 5 = Strongly agree."
    ),
}

STUDENT_PRE_SECTIONS = [
    (
        "Section 1 — Profile and Context",
        [
            ("MC", "What year level are you in?", "1st year | 2nd year | 3rd year | 4th year"),
            (
                "MC",
                "Which math subjects are you currently enrolled in?",
                "Check all that apply (list subjects from current term).",
            ),
            (
                "MC",
                "How many hours per week do you spend reviewing math outside class?",
                "0–2 | 3–5 | 6–10 | More than 10",
            ),
            (
                "MC",
                "What do you primarily use to review math?",
                "YouTube / modules / classmates / Quizlet / LMS / tutoring / other",
            ),
        ],
    ),
    (
        "Section 2 — Problems Students Experience (Pre-Study)",
        [
            (
                "Likert",
                "I often feel confident about a math topic but still get it wrong on exams.",
                None,
            ),
            (
                "Likert",
                "I sometimes get answers right but do not fully understand why.",
                None,
            ),
            (
                "Likert",
                "I find it hard to decide which math topic to study first when preparing for exams.",
                None,
            ),
            (
                "Likert",
                "I struggle to explain math solutions step-by-step (not just getting the final answer).",
                None,
            ),
            (
                "Likert",
                "I feel unprepared for timed math exams even when I studied the material.",
                None,
            ),
            (
                "Likert",
                "I have difficulty connecting math concepts to how I would teach them in a classroom.",
                None,
            ),
            (
                "Likert",
                "When I review, I usually re-read notes or watch videos instead of practicing under exam conditions.",
                None,
            ),
            (
                "Likert",
                "I rarely know whether my mistakes come from careless errors, formula gaps, or conceptual misunderstanding.",
                None,
            ),
            (
                "Open",
                "Describe your biggest challenge when reviewing for math exams.",
                None,
            ),
            (
                "Open",
                "What usually happens when you think you understand a topic but fail the exam?",
                None,
            ),
        ],
    ),
    (
        "Section 3 — Calibration and Metacognition (Pre-Study)",
        [
            ("Likert", "I am aware of how confidence affects my learning.", "Core thesis item (pre)."),
            (
                "Likert",
                "Before answering, I can usually tell whether I truly know a solution or I am guessing.",
                None,
            ),
            (
                "Likert",
                "After a wrong answer, I can identify whether I was overconfident or simply did not know the material.",
                None,
            ),
            (
                "Likert",
                "Rating or reflecting on confidence after each answer helps me study better.",
                "Core thesis item (pre).",
            ),
            ("Likert", "I would recommend ExamiQ to classmates.", "Core thesis item (pre)."),
            ("Open", "Optional comments before using ExamiQ.", "Core thesis open feedback (pre)."),
        ],
    ),
]

STUDENT_POST_SECTIONS = [
    (
        "Section 3 — Calibration and Metacognition (Post-Study)",
        [
            (
                "Likert",
                "ExamiQ helped me understand my calibration gaps.",
                "Core thesis item (post).",
            ),
            (
                "Likert",
                "ExamiQ helped me see when I was overconfident on topics I got wrong.",
                None,
            ),
            (
                "Likert",
                "ExamiQ helped me see when I got answers right but was not sure why.",
                None,
            ),
            (
                "Likert",
                "ExamiQ helped me decide what to review next more than my usual study methods.",
                None,
            ),
            (
                "Likert",
                "ExamiQ's session summary (mastery, misconception, lucky guess, expected gap) made sense to me.",
                None,
            ),
            (
                "Likert",
                "Confidence ratings or confidence feedback improved my self-regulated learning.",
                "Core thesis item (post).",
            ),
        ],
    ),
    (
        "Section 4 — BSEd Mathematics-Specific (Post-Study)",
        [
            (
                "Likert",
                "Practicing math in exam-like timed conditions is important for my success as a future math teacher.",
                None,
            ),
            (
                "Likert",
                "Learning to identify common student misconceptions in math would help me in practicum or microteaching.",
                None,
            ),
            (
                "Likert",
                "I would find it useful if review feedback showed what type of error I made (conceptual, procedural, or careless).",
                None,
            ),
            (
                "Likert",
                "I want review questions aligned to topics I will teach (algebra, geometry, statistics), not only general math.",
                None,
            ),
            (
                "Likert",
                "I would use a tool more if it helped me prepare for licensure or board-style math exams, not only classroom quizzes.",
                None,
            ),
            (
                "Open",
                "As a future math teacher, what do you wish a review system helped you with that YouTube or modules do not?",
                None,
            ),
            (
                "Open",
                "Which ExamiQ feature was most useful (timed exam, session summary, mistake list, AI tutor, topic recommendations)? Why?",
                None,
            ),
        ],
    ),
    (
        "Section 5 — System Improvement and Edge (Post-Study)",
        [
            ("Likert", "I would recommend ExamiQ to other BSEd Math students.", "Core thesis item (post)."),
            (
                "Likert",
                "ExamiQ is more useful than our LMS quizzes because it shows learning gaps, not only scores.",
                None,
            ),
            (
                "Likert",
                "I would use ExamiQ more if my professor assigned review windows tied to our class schedule.",
                None,
            ),
            ("Likert", "I trust AI-generated explanations or tutor chat for math learning.", None),
            (
                "Rank",
                "Rank which new features would help you most:",
                (
                    "LET or board exam practice mode; error-type labels (misconception categories); "
                    "'explain like you are teaching' practice; peer review or study group mode; "
                    "printable weak-topic report for professor consultation; mobile-friendly offline review"
                ),
            ),
            (
                "Open",
                "What one feature would make ExamiQ indispensable for BSEd Math students?",
                None,
            ),
            (
                "Open",
                "What frustrated you or felt missing while using ExamiQ?",
                "Core thesis open feedback (post).",
            ),
        ],
    ),
]

STUDENT_EDGE_MAPPING = [
    (
        "I do not know what to review first",
        "Strengthen adaptive recommendations and weak-topic reports",
    ),
    (
        "I am confident but still wrong",
        "Highlight misconception tier in session summary and dashboard",
    ),
    (
        "Timed exams break me",
        "Position timed exam mode as core review, not optional practice",
    ),
    (
        "I need to teach, not only solve",
        "Add error-type taxonomy or 'explain the misconception' prompts",
    ),
    (
        "Professors notice problems too late",
        "Use faculty intervention export and chair course audit",
    ),
    (
        "Questions must match our curriculum",
        "Emphasize BSEd Math program scoping and chair approval workflow",
    ),
    (
        "LET prep matters",
        "Pilot board-exam review windows with department-approved items",
    ),
    (
        "We do not trust random AI content",
        "Stress human-in-the-loop: faculty create, chair approves",
    ),
]

CHAIR_INTERVIEW_META = {
    "title": "BSEd Mathematics Chairperson Interview Guide",
    "subtitle": "ExamiQ+ Pilot Study — Semi-Structured Department Interview",
    "purpose": (
        "This guide supports a 45–60 minute semi-structured interview with the Department "
        "Chairperson of the College of Education (or equivalent program lead for BSEd "
        "Mathematics). The goal is to understand institutional needs, curriculum alignment, "
        "faculty intervention gaps, and features that would give ExamiQ+ a defensible edge "
        "beyond student self-review."
    ),
    "format": (
        "Use open-ended questions with follow-up probes. Record with consent. Take notes on "
        "pain points, desired outcomes, governance concerns, and adoption barriers."
    ),
}

CHAIR_INTERVIEW_BLOCKS = [
    (
        "Block 1 — Department Context and Student Pain Points",
        [
            (
                "What are the top three challenges BSEd Math students face in mathematics courses?",
                "Probe: year level differences, major vs GE math, practicum readiness.",
            ),
            (
                "Where do students struggle most: content knowledge, problem-solving under time pressure, or explaining and teaching math?",
                "Probe: which courses show the pattern most clearly.",
            ),
            (
                "How do you currently measure whether a student is ready for exams — scores only, or something else?",
                "Probe: rubrics, consultations, formative assessments.",
            ),
            (
                "Do you see patterns of overconfidence (students think they know material but fail exams)?",
                "Probe: examples from recent terms.",
            ),
            (
                "How do students typically prepare for licensure exams or major assessments?",
                "Probe: formal review programs, self-study, commercial apps.",
            ),
        ],
    ),
    (
        "Block 2 — Current Practices and Gaps",
        [
            (
                "What tools do faculty and students use today for math review?",
                "Probe: LMS, printed drills, YouTube, commercial apps, tutoring.",
            ),
            (
                "What is missing in those tools from a department perspective?",
                "Probe: reporting, timing, misconception diagnosis, governance.",
            ),
            (
                "How do faculty currently identify students who need intervention before it is too late?",
                "Probe: triggers, timing in the term, follow-up actions.",
            ),
            (
                "How much time do faculty spend creating or reviewing practice questions versus teaching?",
                "Probe: workload pain points.",
            ),
            (
                "Is there a formal process for ensuring question quality and alignment with CHED or program outcomes?",
                "Probe: who approves content, how often it is updated.",
            ),
        ],
    ),
    (
        "Block 3 — ExamiQ Fit and Institutional Edge",
        [
            (
                "Would a system that flags misconceptions and calibration gaps (not only low scores) be useful for faculty intervention?",
                "Probe: preferred report format, ideal timing.",
            ),
            (
                "How valuable is timed exam simulation compared to untimed practice with immediate answers?",
                "Probe: fit for licensure prep vs classroom quizzes.",
            ),
            (
                "How important is chairperson approval of questions before students see them?",
                "Probe: quality control, liability, academic integrity.",
            ),
            (
                "Would department-level analytics by topic, section, and year level support program improvement or accreditation?",
                "Probe: which metrics matter most.",
            ),
            (
                "What data would you want in a research or intervention export?",
                "Probe: high misconceptions, low practice frequency, calibration gaps.",
            ),
        ],
    ),
    (
        "Block 4 — BSEd Mathematics Curriculum Alignment",
        [
            (
                "Which math topics should BSEd Math review prioritize?",
                "Probe: major courses, methods courses, GE math, statistics.",
            ),
            (
                "Should review content reflect K–12 math competencies students will eventually teach?",
                "Probe: DepEd alignment, practicum relevance.",
            ),
            (
                "Do you want questions written in a teaching-oriented style (for example, diagnosing a student's wrong solution)?",
                "Probe: pedagogical content knowledge vs pure computation.",
            ),
            (
                "How should the system support microteaching or practicum preparation?",
                "Probe: explanation practice, misconception spotting, lesson planning links.",
            ),
        ],
    ),
    (
        "Block 5 — Adoption, Governance, and Sustainability",
        [
            (
                "What would convince faculty to require or recommend ExamiQ instead of treating it as optional?",
                "Probe: assignments, review windows, chair endorsement.",
            ),
            (
                "What concerns do you have about AI-generated questions, feedback, or tutor chat?",
                "Probe: accuracy, bias, academic integrity, approval workflow.",
            ),
            (
                "What training or support would faculty need to use intervention dashboards and CSV exports?",
                "Probe: onboarding, documentation, demo sessions.",
            ),
            (
                "If ExamiQ succeeds, what outcome would you cite as proof?",
                "Probe: pass rates, LET performance, fewer remedial cases, teaching confidence.",
            ),
        ],
    ),
]

CHAIR_CLOSING_QUESTIONS = [
    (
        "If you could add one capability that no LMS or commercial review app offers for BSEd Math, what would it be?",
        "Probe for unique departmental needs.",
    ),
    (
        "What would make this thesis contribution meaningful to your department beyond being a student project?",
        "Probe for sustainability, policy, or institutional adoption.",
    ),
]

CHAIR_EDGE_MAPPING = [
    ("Misconception and calibration flags", "Faculty intervention list and chair program dashboard"),
    ("Curriculum-aligned content", "BSEd Math program scoping and chair question approval"),
    ("Exam readiness under time pressure", "Timed exam mode with post-session summary"),
    ("Department-wide visibility", "Cross-program analytics and course audit"),
    ("Evidence for program improvement", "Anonymized research CSV export"),
    ("Future-teacher preparation", "Teaching-oriented items and error-type feedback"),
]
