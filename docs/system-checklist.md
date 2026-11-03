# ExamiQ System Checklist

This checklist defines the behavioral expectations, error handling, and system responses for the Student, Faculty, Program Coordinator, and Administrator roles of the ExamiQ mathematics exam review platform. Each check maps a specific user action to its expected success metric and potential system failure. The matrix serves as a validation blueprint to ensure account security, reliable examination workflows, and robust error recovery across the application.

## Authentication (Student / Faculty / Coordinator / Admin)
✓ Enter email and password > Login successfully
✓ Enter invalid email/password > Display "Invalid Credentials"
✓ Login with unverified email > Display "Email not verified"
✓ Click Forgot Password > Send password reset link to email
✓ Successful login > Redirect to role dashboard
✓ Click Register > Create account with entered credentials

## User Management (Admin / Coordinator)
✓ Open users list > Load users with filters
✓ Approve pending faculty/coordinator > Activate account, send email
✓ Reject pending request > Deactivate account, send email
✓ Deactivate/activate approved account > Toggle access
✓ Archive/restore student > Hide from rosters / return to active
✓ Create faculty or coordinator directly > Active approved account

## Subject & Curriculum (Coordinator)
✓ Open subject catalog > Load subjects with edit/delete
✓ Add subject (program, code, title, year, semester) > Save with topic and course copy
✓ Edit subject details > Persist updates
✓ Delete subject > Remove subject, topics, questions, course copy
✓ Duplicate code in same program > Block with message

## Section & Teaching Assignments (Coordinator)
✓ Open sections list > Load sections with student counts
✓ Create section (program, year, label, year, capacity) > Save
✓ Bulk create sections > Save multiple numbered sections
✓ Edit section capacity > Persist update
✓ Create teaching assignment (faculty, sections, subject, term) > Provision course and exam setup
✓ Duplicate assignment > Skip with message
✓ Delete assignment > Remove and log

## Question Bank (Faculty)
✓ Open course > Load topics and questions
✓ Add topic to subject > Save topic
✓ Create draft MCQ question (stem, choices, correct, explanation) > Save draft
✓ Publish question with attestation > Activate for students
✓ Deactivate/activate question > Toggle in student pool
✓ Import CSV questions > Save valid, skip duplicates/errors
✓ AI generate questions (topic, difficulty, count) > Queue job, show results

## Examination (Faculty / Student)
✓ Faculty: Configure exam setup (timer, topics, difficulties) > Save, lock timer for students
✓ Faculty: Create review window (dates, topics, difficulties) > Save
✓ Student: Open exam setup > Select subjects, difficulty, timer > Start session
✓ Student: Answer question with confidence > Grade, store, next question
✓ Student: Session timeout > Record as unanswered, advance
✓ Student: Finish/expire > Show summary with score, weak topics, recommendations

## AI Review & Feedback (Student / Faculty)
✓ Student: Open explanation steps for answer > View steps, record view
✓ Student: Chat with AI tutor > Receive AI response in thread
✓ Student: Send message/photo to faculty > Deliver to conversation thread
✓ Faculty: Edit explanation steps > Save for student view
✓ Faculty: Reply in conversation thread > Deliver to student

## Mistake Tracking & Concept Review (Student)
✓ Open mistakes list > Filter by topic, confidence, date
✓ Open mistake detail > See question, both answers, explanation
✓ Generate AI feedback for mistake > Store and display
✓ Start concept review > Learn, try, practice until resolved
✓ Restart resolved concept > Reset progress

## Learning Analytics (Student / Faculty / Chairperson)
✓ Student: Dashboard > Accuracy donut, trend, recent sessions, weak topics
✓ Student: Session history > Paginated, filterable, finished only
✓ Student: Topic progress > Per-topic mastery
✓ Faculty: Course analytics > Accuracy, calibration, interventions, heatmap
✓ Faculty: Student detail > Sessions, answers, weak areas
✓ Faculty: Export interventions CSV > Scrambled IDs
✓ Chairperson: Programs dashboard > Cross-program analytics
✓ Chairperson: Course audit > Participation status
✓ Chairperson: Audit logs > Faculty and student activity

## Data Storage & Media
✓ Persistent storage for users, sessions, questions, feedback, mistakes, analytics > Migrations versioned
✓ Upload profile photo / learning material / mistake photo > Save and serve
✓ Download learning material > File response