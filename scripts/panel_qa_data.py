"""Panelist Q&A content for user-flows-and-panel-questions.pdf."""

PANEL_QA = [
    (
        "5.1 Problem Definition and Research Rationale",
        [
            (
                "What specific problem in self-regulated learning does ExamiQ+ address?",
                "ExamiQ+ addresses the gap between what students think they know and what they actually know — "
                "called poor calibration. Many students are overconfident on topics they get wrong (misconceptions) "
                "or underconfident on topics they get right (lucky guesses). The platform makes this visible through "
                "timed review sessions, confidence inference, and a calibration summary so students can monitor and "
                "adjust their study behavior — the core of self-regulated learning.",
            ),
            (
                "Why focus on calibration awareness rather than raw exam scores?",
                "Raw scores only show whether an answer was right or wrong. Calibration shows whether the student "
                "knew why they were right or wrong. A student with 70% accuracy but many misconceptions is in a "
                "different learning state than one with 70% and mostly expected gaps. Calibration awareness is the "
                "metacognitive skill that helps students decide what to review next, which is the thesis outcome "
                "measured by pre- and post-surveys.",
            ),
            (
                "How is your study different from existing LMS quiz modules or commercial review apps?",
                "Standard LMS quizzes report scores only. Commercial apps often give immediate explanations during "
                "practice, which reduces exam-like pressure. ExamiQ+ combines timed exam conditions (no inline "
                "explanations), inferred confidence from response time, a five-tier calibration matrix (mastery, "
                "misconception, lucky guess, expected gap, uncertain), role-based analytics for faculty intervention, "
                "and department-scoped content governance with chairperson question approval.",
            ),
            (
                "Why mathematics only, and why scoped by degree program instead of a shared question pool?",
                "Mathematics is a common required subject across all eight degree programs, making cross-program "
                "comparison possible within one campus. Each program has different math needs (e.g., discrete math "
                "for CS vs. business math for Marketing), so content is scoped by home degree program rather than "
                "a single shared pool. This ensures review questions match the student's actual curriculum.",
            ),
            (
                "What gap in the literature does your thesis fill?",
                "Existing SRL research often relies on self-reported confidence ratings, which interrupt exam flow "
                "and may be unreliable under time pressure. This study evaluates whether a web platform that infers "
                "confidence from response time, surfaces calibration gaps after timed sessions, and provides "
                "faculty intervention tools can improve students' calibration awareness as measured by validated "
                "survey items before and after use.",
            ),
            (
                "Who are your target participants and why are they appropriate for this study?",
                "College students enrolled in one of the eight supported degree programs who are actively taking "
                "math subjects during the pilot term. They are appropriate because they face real exam pressure, "
                "have program-specific math content available in the system, and can complete multiple review "
                "sessions within a single academic term to show measurable change in calibration awareness.",
            ),
        ],
    ),
    (
        "5.2 Theoretical Framework",
        [
            (
                "What theories of self-regulated learning underpin your design?",
                "The design draws on Zimmerman's cyclical model of SRL (forethought, performance, self-reflection) "
                "and Nelson and Narens' metacognitive monitoring framework. Students plan review (forethought via "
                "topic and difficulty selection), monitor performance under timed conditions, and reflect on "
                "calibration results on the session summary. Faculty analytics support the social/contextual "
                "dimension of SRL through instructional intervention.",
            ),
            (
                "How do you define calibration awareness in operational terms?",
                "Calibration awareness is the student's ability to recognize the relationship between their "
                "confidence and their actual performance. Operationally, it is measured by the pre- and post-survey "
                "Likert item: 'I am aware of how confidence affects learning' (pre) and 'EXAMIQ helped me understand "
                "my calibration gaps' (post). In the system, it is represented by the calibration matrix counts "
                "per session and aggregated on the student dashboard.",
            ),
            (
                "What is the relationship between confidence and metacognition in your model?",
                "Confidence is treated as a behavioral proxy for metacognitive judgment — the student's implicit "
                "estimate of knowing. Fast answers suggest high perceived certainty; slow answers suggest doubt. "
                "When this proxy is crossed with correctness, the system classifies the metacognitive state "
                "(well-calibrated mastery vs. miscalibrated misconception). The session summary makes this "
                "explicit so students can engage in metacognitive reflection.",
            ),
            (
                "Which SRL phases (planning, monitoring, control) does ExamiQ+ support?",
                "Planning: review setup wizard (subject, topic, difficulty, duration). Monitoring: per-question "
                "timer and real-time answer submission. Control: session summary recommendations, mistake list, "
                "weak-area patterns, and topic progress guide what to study next. Faculty intervention lists "
                "extend control to the instructional level.",
            ),
            (
                "How do your calibration tiers (mastery, misconception, lucky guess, expected gap) map to theory?",
                "These map to the confidence × accuracy matrix used in metacognitive research. Mastery = "
                "high confidence + correct (accurate monitoring). Misconception = high confidence + wrong "
                "(overconfidence). Lucky guess = low confidence + correct (underconfidence). Expected gap = "
                "low confidence + wrong (accurate awareness of not knowing). Uncertain = medium confidence, "
                "ambiguous signal requiring further practice.",
            ),
            (
                "What prior research supports inferring confidence from response time instead of self-report?",
                "Cognitive psychology literature links response latency to retrieval strength and judgment of "
                "learning. Fast correct answers typically indicate fluent recall; slow incorrect answers suggest "
                "struggle. ExamiQ+ applies fixed thresholds scaled to the per-question time limit: ≤33% of limit "
                "= high, ≤73% = medium, above = low. This avoids interrupting timed exams with extra rating steps "
                "while still producing a confidence signal for calibration analysis.",
            ),
        ],
    ),
    (
        "5.3 System Design and Architecture",
        [
            (
                "Why did you choose Django and this role-based architecture?",
                "Django provides built-in authentication, ORM, admin, and security features suitable for a "
                "multi-role academic system. The role-based architecture (student, professor, chairperson, "
                "campus admin) mirrors real institutional hierarchy. Each role has its own URL namespace "
                "(/student/, /professor/, /chairperson/, /campus/) enforced by mixins that return HTTP 403 "
                "on unauthorized access.",
            ),
            (
                "How do you enforce separation of duties between faculty, chairperson, and campus admin?",
                "Campus admin approves accounts and manages calendar/sections. Chairperson creates teaching "
                "assignments and approves questions for programs their department manages. Faculty configure "
                "exams and create questions but cannot approve their own submissions. Students can only review "
                "within their home program. Each boundary is enforced in view mixins (StudentRequiredMixin, "
                "ProfessorCourseMixin, ChairpersonProgramMixin, CampusAdminRequiredMixin).",
            ),
            (
                "Explain the data flow from question creation to student review to analytics.",
                "Faculty creates a question → status PENDING. Chairperson approves → APPROVED. Student starts "
                "review → system selects approved active questions adaptively. Each answer is graded, confidence "
                "inferred, and stored. Wrong answers create MistakeRecord entries. Session completion feeds "
                "student dashboard, faculty course analytics, chairperson program dashboard, and research export.",
            ),
            (
                "How does program scoping prevent students from accessing other departments' content?",
                "Each student has a home_degree_program field on their profile. Review setup filters subjects "
                "and topics to that program's curriculum. Course offerings, question banks, and analytics are "
                "linked to program slugs. Querysets in student views filter by the logged-in student's program; "
                "cross-program URLs are not exposed in the student interface.",
            ),
            (
                "What is the adaptive question selection algorithm and what pedagogical goal does it serve?",
                "Questions are weighted-randomly selected: +3 weight if the topic has prior mistakes, +2 if the "
                "specific question was previously answered wrong with high confidence, +1 if unseen. A 10% chance "
                "of pure random selection prevents predictability. The goal is spaced retrieval practice focused "
                "on weak areas and misconceptions rather than repeating already-mastered items.",
            ),
            (
                "Why are explanations shown only on the session summary and not during the timed exam?",
                "To simulate exam conditions where students cannot look up answers mid-test. This preserves the "
                "integrity of the timed confidence signal — immediate explanations would change both performance "
                "and response time. Post-session explanations on the summary support the reflection phase of SRL "
                "without contaminating the monitoring phase.",
            ),
            (
                "How does the system handle concurrent users during a pilot?",
                "Each review session is independent per student. Django serves stateless HTTP requests; session "
                "state is stored in PostgreSQL. Question delivery uses per-session exclude lists to avoid repeats. "
                "For pilot scale (dozens to low hundreds of students), standard single-server deployment with "
                "database connection pooling is sufficient. No shared in-memory state is required between users.",
            ),
        ],
    ),
    (
        "5.4 User Roles and Workflows",
        [
            (
                "Walk us through what a student does from registration to session summary.",
                "1) Register at /accounts/signup/ with program, year level, section. 2) Land on /student/dashboard/. "
                "3) Complete profile if needed. 4) Click Start Review → /student/review/setup/. 5) Select subject, "
                "topic, difficulty, duration. 6) Take timed exam at /student/review/<pk>/ answering each question "
                "within the countdown. 7) View session summary at /student/review/<pk>/summary/ showing accuracy, "
                "calibration matrix, and recommended topics. 8) Optionally review mistakes and topic progress.",
            ),
            (
                "What must happen institutionally before a student can start a review session?",
                "Campus admin must set the current academic term and create sections. Chairperson must create a "
                "teaching assignment linking faculty, section, subject, and term (auto-creates course and exam setup). "
                "Faculty must enable exam setup with topics and timer settings. Faculty must create questions; "
                "chairperson must approve them. Student profile must have matching program, year level, and section.",
            ),
            (
                "Why do faculty and chairperson accounts require campus approval but students do not?",
                "Faculty and chairperson accounts grant access to student data, content management, and institutional "
                "analytics. Requiring campus admin approval verifies employment and prevents unauthorized persons "
                "from accessing sensitive educational records. Student accounts only access their own data and "
                "publicly available review content within their program.",
            ),
            (
                "What is the chairperson's role in question quality control?",
                "Chairpersons review faculty-submitted questions and approve or reject them before they enter the "
                "student review pool. Approval is limited to programs managed by the chairperson's department. "
                "This ensures mathematical accuracy, appropriate difficulty, and alignment with program curriculum. "
                "The approval service layer exists in the codebase; the dedicated review UI is planned.",
            ),
            (
                "How does a professor identify and intervene with at-risk students?",
                "Faculty opens course analytics at /professor/courses/<pk>/ which shows an intervention list. "
                "Students are flagged based on low accuracy, high misconception count, low practice frequency "
                "(no sessions in 14 days), and calibration gaps. Faculty drills into individual students via the "
                "roster, then exports an intervention CSV with suggested actions for follow-up.",
            ),
            (
                "What can the campus administrator do that other roles cannot?",
                "Approve or reject faculty and chairperson registrations, directly provision staff accounts, "
                "manage program sections and capacity, set the current academic year and term, and access the "
                "campus dashboard. No other role can activate pending staff accounts or control the academic "
                "calendar that gates student review eligibility.",
            ),
        ],
    ),
    (
        "5.5 Confidence and Calibration Measurement",
        [
            (
                "How is confidence measured in timed exam mode?",
                "Confidence is not manually rated during the exam. The system records time spent per question "
                "and maps it to a confidence tier (1 = low, 3 = medium, 5 = high) using the confidence_from_time_spent "
                "function in apps/analytics/confidence.py. This value is stored on each Answer record alongside "
                "correctness for calibration classification.",
            ),
            (
                "What are the thresholds for high, medium, and low confidence from response time?",
                "Thresholds scale to the per-question time limit (default 30 seconds). At 30s limit: ≤10s = high "
                "confidence (5), ≤22s = medium (3), >22s = low (1). For other limits, thresholds scale "
                "proportionally (33% and 73% of the limit). These constants are HIGH_CONFIDENCE_MAX_SECONDS=10 "
                "and AVERAGE_CONFIDENCE_MAX_SECONDS=22 relative to CONFIDENCE_TIMER_CAP_SECONDS=30.",
            ),
            (
                "Why omit manual confidence ratings during the timed exam?",
                "Manual ratings after each question add cognitive load and break exam flow, potentially changing "
                "both response times and answer accuracy. Omitting them preserves a natural timed-exam experience "
                "while still producing a confidence proxy. The pilot protocol explicitly states confidence ratings "
                "are omitted in timed exam mode; explanations appear on the summary instead.",
            ),
            (
                "How do you validate that inferred confidence relates to actual student certainty?",
                "Validation is done through convergent evidence: (1) post-survey item on confidence rating usefulness, "
                "(2) correlation between response time distributions and self-reported calibration awareness change, "
                "(3) face validity — fast wrong answers (misconceptions) match the intuitive overconfidence pattern. "
                "Full psychometric validation of time-based inference is acknowledged as a limitation and future work.",
            ),
            (
                "What is a misconception in your system and why is it flagged for intervention?",
                "A misconception is a high-confidence wrong answer — the student answered quickly (suggesting "
                "certainty) but was incorrect. This is the most dangerous calibration state because the student "
                "believes they understand material they do not. The intervention list prioritizes students with "
                "high misconception counts, and the adaptive algorithm re-serves those questions with extra weight.",
            ),
            (
                "Can a student game the system by answering quickly or slowly to manipulate confidence?",
                "Partially. A student could deliberately slow down to lower confidence scores, but this also "
                "risks timer expiry and wrong answers. The timed constraint limits gaming — slowing down reduces "
                "time for thinking. Confidence is one input among many (accuracy, mistake patterns, session "
                "frequency) for analytics and research. Gaming would hurt their own performance metrics.",
            ),
        ],
    ),
    (
        "5.6 Pilot Study Methodology",
        [
            (
                "What is your research design: pre-experimental, quasi-experimental, or other?",
                "A one-group pre-test/post-test pre-experimental design. Each participant completes a pre-survey "
                "before using ExamiQ+ and a post-survey after the pilot period. Change in calibration awareness "
                "and related Likert items is measured within subjects. There is no control group in the initial "
                "campus pilot; this is appropriate for a system feasibility and preliminary effectiveness study.",
            ),
            (
                "How many participants do you need and how did you compute sample size?",
                "The pilot targets students across participating programs within one academic term. Sample size "
                "is determined by available enrolled students who consent to participate. For a paired pre-post "
                "Likert study, a minimum of 30 participants is commonly cited for central limit theorem applicability "
                "in thesis pilots. The department-scoped export allows aggregation across programs to reach this target.",
            ),
            (
                "What are your pre- and post-survey instruments and are they validated?",
                "Three Likert items (1–5) per survey: calibration awareness, confidence rating usefulness, and "
                "would recommend, plus optional open feedback. Pre-survey asks about general awareness; post-survey "
                "asks about ExamiQ-specific impact. Items are adapted from SRL and calibration literature. Formal "
                "validation with pilot reliability analysis (Cronbach's alpha) is planned as part of thesis analysis.",
            ),
            (
                "What are your dependent and independent variables?",
                "Dependent variables: post-survey scores (calibration awareness, confidence usefulness, recommendation), "
                "change scores (post minus pre), and behavioral metrics (misconception count, accuracy, sessions completed). "
                "Independent variable: exposure to ExamiQ+ (usage duration and number of review sessions). "
                "Covariates: home degree program, year level, baseline pre-survey scores.",
            ),
            (
                "How long is the pilot period and how many sessions must each student complete?",
                "The pilot runs for one academic term (duration set by campus admin via academic calendar). "
                "Students are encouraged to complete multiple review sessions but there is no hard session gate "
                "for the post-survey — it can be submitted anytime from Profile after using the system. "
                "More sessions produce richer calibration data for analysis.",
            ),
            (
                "How do you control for prior math ability or study habits?",
                "Pre-survey scores serve as a baseline for within-subject comparison. Program and year level "
                "are recorded as covariates in the research export. The system logs session frequency to distinguish "
                "active from inactive participants. Full control of prior ability would require a standardized "
                "math pre-test, which is noted as a limitation of the current design.",
            ),
            (
                "What ethical approvals and consent procedures are in place?",
                "Participants submit optional pilot consent via a checkbox (PilotConsent model). Pre- and post-surveys "
                "are voluntary. Research export uses SHA-256 hashed student IDs with no names or emails. "
                "Institutional ethics review board approval is obtained per university requirements before data "
                "collection begins.",
            ),
        ],
    ),
    (
        "5.7 Data Collection and Analysis",
        [
            (
                "What data does the system log for research purposes?",
                "Per student: sessions completed, total answers, accuracy percentage, average confidence, "
                "counts per calibration tier (mastery, misconception, lucky guess, expected gap, uncertain), "
                "mistake records, home program, and pre/post survey Likert scores. All exported via the "
                "chairperson research CSV endpoint.",
            ),
            (
                "How is student identity protected in the research export?",
                "The export uses student_hash — the first 16 characters of SHA-256 hash of the student ID — "
                "with no name, email, or student number. Data is department-scoped so only the chairperson "
                "of the managing department can export. Faculty intervention CSVs contain names but are "
                "separate from the anonymized research export.",
            ),
            (
                "What statistical tests will you use to compare pre- and post-survey scores?",
                "Paired t-test or Wilcoxon signed-rank test (if normality assumption fails) for each Likert item "
                "comparing pre vs. post scores. Effect size (Cohen's d) will be reported. Descriptive statistics "
                "(mean, SD, frequency) for calibration tier distributions. Correlation analysis between session "
                "count and calibration awareness change.",
            ),
            (
                "How will you analyze calibration tier distributions before and after intervention?",
                "Early-session calibration profiles (first N sessions) are compared to later-session profiles "
                "for the same student using misconception rate and mastery rate. A reduction in misconception "
                "proportion and increase in mastery proportion over time indicates improved calibration. "
                "Aggregated tier counts from the research export support group-level analysis.",
            ),
            (
                "What constitutes a meaningful improvement in calibration awareness?",
                "A statistically significant increase in the post-survey calibration awareness item (p < 0.05) "
                "with at least a medium effect size (Cohen's d ≥ 0.5). Practically, a mean increase of ≥ 0.5 "
                "points on the 5-point Likert scale is considered educationally meaningful for a short pilot.",
            ),
            (
                "How do you handle incomplete sessions or students who drop out of the pilot?",
                "Partial sessions are saved with their completed answers and appear in session history. "
                "Dropouts are included in analysis only if they completed the pre-survey (intent-to-treat) or "
                "excluded in a per-protocol sensitivity analysis. Session count and completion status are "
                "recorded in the export to filter active participants.",
            ),
        ],
    ),
    (
        "5.8 AI Features",
        [
            (
                "What AI features are integrated and what is their role in the study?",
                "AI question generation (faculty drafts questions from topic prompts), AI difficulty suggestion, "
                "adaptive step-by-step feedback generation, AI tutor chat post-session, and optional AI course "
                "summary for faculty. AI is a supporting tool, not the primary intervention. The core thesis "
                "intervention is the calibration-aware review workflow itself.",
            ),
            (
                "How does AI question generation maintain quality and alignment with learning objectives?",
                "AI-generated questions enter the same PENDING approval workflow as manual questions. Faculty "
                "review and edit drafts before submission. Chairperson must approve before questions reach students. "
                "This human-in-the-loop gate ensures curriculum alignment regardless of AI output quality.",
            ),
            (
                "Does the AI tutor influence SRL outcomes and how do you account for that in analysis?",
                "The AI tutor is optional and only available post-session. Usage is not required for the pilot. "
                "If tutor usage data is collected, it can be treated as a covariate. The primary SRL outcome "
                "is calibration awareness from surveys and behavioral calibration metrics, which are independent "
                "of tutor interaction.",
            ),
            (
                "What LLM provider do you use and how do you handle API failures or hallucinations?",
                "The system supports configurable LLM providers (e.g., Gemini when LLM_PROVIDER=gemini and API key "
                "is set). API failures return graceful error messages without blocking core review functionality. "
                "AI-generated content is always reviewed by faculty before student exposure. Hallucinated math "
                "content is caught by the approval workflow.",
            ),
            (
                "Are AI-generated explanations reviewed by faculty before students see them?",
                "Faculty can edit explanations at /professor/courses/<pk>/feedback/. AI-generated feedback is "
                "a draft that faculty can modify. Questions must be chairperson-approved before entering sessions. "
                "This two-layer review (faculty edit + chair approval) limits exposure to unreviewed AI content.",
            ),
        ],
    ),
    (
        "5.9 Limitations and Scope",
        [
            (
                "What are the limitations of a single-campus pilot?",
                "Results may not generalize to other institutions with different curricula, student populations, "
                "or technology access. Sample size is constrained to enrolled students in participating programs. "
                "No control group limits causal claims. External validity is addressed by documenting the "
                "implementation precisely so others can replicate.",
            ),
            (
                "Is the system generalizable beyond the eight degree programs?",
                "The architecture is program-agnostic — adding a program requires seeding subjects, topics, and "
                "a managing department. The eight current programs demonstrate the pattern. Generalization to "
                "non-math subjects would require new question types and grading logic but the role and analytics "
                "framework would remain the same.",
            ),
            (
                "What features are planned but not yet fully implemented?",
                "Chairperson question review UI (service exists, URL not wired), research export URL registration, "
                "pilot consent and survey forms on the Profile page (models exist), practice review mode in "
                "student setup (model supports it but setup defaults to timed_exam), and AI question variation "
                "confirm-save flow.",
            ),
            (
                "How does timed exam mode differ from practice review mode and which did you use in the pilot?",
                "Timed exam: per-question countdown, confidence inferred from time, no inline explanations. "
                "Practice review: supports manual confidence ratings and a more relaxed pace. The pilot uses "
                "timed exam mode exclusively, as stated in the pilot protocol, to simulate exam conditions.",
            ),
            (
                "What happens if no chairperson approves questions in time for the pilot?",
                "Questions remain in PENDING status and are excluded from the review pool. Mitigation: pre-seed "
                "approved questions before the pilot, use Django admin for bulk approval, or run the "
                "auto-approve migration in development. Faculty are notified that submissions require approval.",
            ),
            (
                "Can results be attributed to the platform versus normal classroom instruction?",
                "Not with certainty in a one-group design. Classroom instruction continues during the pilot. "
                "The pre-post survey isolates self-reported calibration awareness change attributable to platform "
                "use. Acknowledging this confound is part of the limitations section. A future RCT with a "
                "control group would strengthen causal claims.",
            ),
        ],
    ),
    (
        "5.10 Security, Privacy, and Ethics",
        [
            (
                "How is student data stored and who can access it?",
                "All data is stored in PostgreSQL. Students access only their own sessions, answers, and profile. "
                "Faculty access students enrolled in their courses via roster and analytics. Chairpersons access "
                "department-scoped aggregated data. Campus admins manage accounts. Django's ORM and view mixins "
                "enforce queryset filtering per role.",
            ),
            (
                "What personal identifiable information is excluded from research exports?",
                "The research CSV excludes name, email, student number, and phone. Only student_hash (SHA-256 "
                "truncated), program slug, and behavioral metrics are included. Survey scores are linked to "
                "the hash, not to identifiable fields.",
            ),
            (
                "How do you comply with data privacy regulations applicable to your institution?",
                "Consent is obtained before data collection. Data minimization is applied in research exports. "
                "Access is role-restricted. Passwords are hashed by Django's auth system. The platform follows "
                "the institution's data privacy policy and the Philippines Data Privacy Act requirements as "
                "applicable to educational records.",
            ),
            (
                "Can faculty see individual student calibration data and is that ethically appropriate?",
                "Yes — faculty see per-student accuracy, misconception counts, and calibration breakdowns for "
                "students in their courses. This is ethically appropriate because faculty already have a "
                "legitimate educational interest in student performance, the data supports instructional "
                "intervention (not punishment), and students are informed during pilot consent.",
            ),
            (
                "How are passwords and authentication handled?",
                "django-allauth with email-based login (USERNAME_FIELD = email). Passwords are hashed using "
                "Django's PBKDF2 hasher. CSRF protection on all forms. Session cookies for authentication. "
                "Pending/rejected accounts are blocked at the adapter level before login succeeds.",
            ),
        ],
    ),
    (
        "5.11 Testing and Validation",
        [
            (
                "How did you functionally test each role's workflows?",
                "Documented in docs/functional-testing.md with Satisfactory/Unsatisfactory checklist per role "
                "(Appendix B) and detailed test cases (Appendix A). Each major function — signup, review session, "
                "exam setup, question creation, analytics — was tested against expected system responses. "
                "Cross-role access was verified (Appendix C): students receive 403 on faculty URLs, etc.",
            ),
            (
                "What test cases cover eligibility gates and cross-role access control?",
                "Student review setup blocks when profile is incomplete, section is mismatched, or no current term "
                "exists. Cross-role tests verify 403 for students on /professor/, faculty on /student/dashboard/, "
                "chairperson on /campus/, and anonymous redirect to login. These are in Appendix A and C of "
                "the functional testing document.",
            ),
            (
                "Did you conduct usability testing with actual students?",
                "The pilot itself serves as the primary usability evaluation with real students. Pre-pilot, "
                "demo accounts (e.g., student3@examiq.edu with misconception profile) were used for walkthrough "
                "testing. Post-survey open feedback captures usability impressions. Formal think-aloud usability "
                "testing is recommended as future work.",
            ),
            (
                "How do you know the grading logic is correct for all question types?",
                "The grade_answer function in apps/questions/services.py handles multiple choice, true/false, "
                "numeric, and short-answer types with type-specific comparison logic. Unit tests in the questions "
                "and reviews apps verify grading outcomes. Faculty review of question correctness during the "
                "approval workflow provides an additional human validation layer.",
            ),
            (
                "What is your plan if the system fails during a live pilot session?",
                "Completed answers are saved per submission — a mid-session failure preserves partial progress. "
                "Students can start a new session. Faculty and campus admin monitor via Django admin. A backup "
                "database and documented restart procedure are maintained. Health check endpoint at /health/ "
                "supports uptime monitoring.",
            ),
        ],
    ),
    (
        "5.12 Demonstration and Practical Scenarios",
        [
            (
                "Can you demonstrate a student completing a review and show the calibration summary?",
                "Yes. Log in as student3@examiq.edu (demo1234). Go to Start Review, complete a session, then "
                "view /student/review/<pk>/summary/. The summary shows accuracy percentage, calibration matrix "
                "with mastery/misconception/lucky guess/expected gap counts, and a recommended topic for "
                "further study.",
            ),
            (
                "Show how a professor uses the intervention list to identify a misconception profile.",
                "Log in as prof.algebra@examiq.edu (demo1234). Open MATH101-CS course at /professor/courses/<pk>/. "
                "The intervention list flags student3 with high misconception count. Click into the student "
                "detail from the roster to see per-answer calibration breakdown. Export CSV for advising.",
            ),
            (
                "Show how a chairperson views department-wide program performance.",
                "Log in as chair.computersci@examiq.edu (demo1234). Open /chairperson/dashboard/ for per-program "
                "accuracy and session counts within the CS department scope. Cross-program view at "
                "/chairperson/analytics/by-program/ compares all programs managed by the department.",
            ),
            (
                "What does the research CSV export contain and how would you use it in analysis?",
                "Columns: student_hash, program, sessions_completed, total_answers, accuracy_pct, avg_confidence, "
                "five calibration tier counts, mistake_records, and pre/post survey Likert scores. Import into "
                "SPSS or Python pandas for paired t-tests on survey items, descriptive stats on calibration "
                "distributions, and correlation between usage intensity and awareness change.",
            ),
            (
                "What would you show if the panel asks about a student who is blocked from starting review?",
                "Navigate to /student/review/setup/ with an incomplete profile. The system displays the "
                "eligibility message listing missing requirements: no section, no current term, or no enabled "
                "exam setup. Demonstrate fixing each condition — set profile fields, campus admin sets term, "
                "faculty enables exam setup — and show the wizard proceeding.",
            ),
        ],
    ),
    (
        "5.13 Future Work and Sustainability",
        [
            (
                "What improvements would you make after the pilot?",
                "Wire the chairperson question review UI and research export URL, add pilot consent and survey "
                "forms to Profile, enable practice review mode as a student option, validate time-based confidence "
                "against self-report in a follow-up study, and add a control group for stronger causal evidence.",
            ),
            (
                "Can the platform scale to more programs or institutions?",
                "Yes. The program model is data-driven — new programs are added via fixtures or admin without "
                "code changes. Multi-tenancy (separate campuses) would require an institution field on core "
                "models. Current single-campus design scales to thousands of students on standard Django "
                "deployment with PostgreSQL.",
            ),
            (
                "Will the system remain deployed after the thesis defense?",
                "The platform is designed for continued institutional use beyond the thesis. Campus admin and "
                "chairperson workflows support ongoing term-over-term operation. Pilot data collection can be "
                "disabled while retaining review and analytics functionality for regular academic use.",
            ),
            (
                "How would you add support for non-math subjects?",
                "Add new subjects and topics under existing or new programs. Extend the grade_answer function "
                "for new question types (essay rubric, code evaluation). AI feedback prompts would need "
                "subject-specific templates. The role architecture, session flow, and analytics framework "
                "are subject-agnostic.",
            ),
            (
                "What metrics would you track for long-term institutional adoption?",
                "Active students per term, sessions per student per week, question bank growth rate, approval "
                "turnaround time, faculty intervention CSV downloads, misconception rate trends across terms, "
                "and student post-survey recommendation scores. Chairperson dashboard metrics provide "
                "institutional-level adoption visibility.",
            ),
        ],
    ),
]
