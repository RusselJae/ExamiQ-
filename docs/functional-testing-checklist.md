# ExamiQ Functional Testing Checklist

**Format:** Function | Satisfactory (S) / Unsatisfactory (U) | Note

---

## 1.0 User Management Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| Sign up with year level, section and email OTP | S | Creates approved but inactive account; code activates it |
| Sign in and reach personal dashboard | S | Redirects to dashboard with own data only |
| Update profile (name, section, password) | S | Validates section capacity and year-level match |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| Request faculty account with employee ID | S | Creates pending account awaiting coordinator approval |
| Sign in with emailed code after approval | S | Opens faculty overview with assigned courses |
| Update profile (name, photo, password) | S | Photo limited to 2 MB and JPEG/PNG/WebP |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| Request chairperson account with department | S | Creates pending account awaiting campus admin approval |
| Sign in with emailed code after approval | S | Opens chairperson dashboard |
| Update profile (name, photo, password) | S | Same rules as faculty |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| Sign in with admin credentials | S | Accesses campus console |
| Approve pending faculty registration | S | Sets account active and approved; sends email and notice |
| Create faculty or chairperson account directly | S | Creates active approved account without pending step |

---

## 2.0 Question Management Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| No direct access to question management | — | Student interacts only through examinations |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| Add topic to course subject | S | Topic saved under the course programme |
| Create draft MCQ question with choices and explanation steps | S | Saved as draft, not yet visible to students |
| Publish question after faculty attestation | S | Approves and activates question for student pool |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| Review pending questions from faculty | U | Service exists but review UI not wired to URLs/views |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| No direct access to question management | — | Managed by faculty and chairperson |

---

## 3.0 Examination Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| Set up timed exam (subjects, difficulty, timer) | S | Wizard validates eligibility and available questions |
| Answer questions with confidence rating | S | Grades answer, stores confidence and time, moves to next |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| Configure per-question timer, topics and difficulties | S | Students in assigned sections become eligible |
| Create review window with start/end dates | S | Window saved; students can start sessions within it |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| No direct access to examination setup | — | Managed by faculty |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| No direct access to examination setup | — | Prerequisite data only (calendar, sections) |

---

## 4.0 AI Review Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| View step-by-step explanation for an answer | S | Explanation shown; view recorded |
| Chat with AI tutor about a question | S | AI response returned in chat history |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| Edit explanation steps for a question | S | Steps saved for student view |
| Reply to student question in chat thread | S | Faculty note delivered to student thread |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| No direct access to AI review | — | Read-only through analytics |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| No direct access to AI review | — | Not in scope |

---

## 5.0 Learning Analytics Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| View personal mistake list with filters | S | Auto-logged wrong answers; confidence and topic shown |
| Open mistake detail with explanation | S | Question, both answers, and step-by-step shown |
| Generate AI feedback for a mistake | S | Generated feedback stored and displayed |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| View student mistakes for assigned sections | S | Course-scoped concern list with student notes |
| Post faculty reply to a mistake concern | S | Reply delivered to student conversation thread |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| View cross-program mistake patterns | S | Analytics available through chairperson dashboard |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| No direct access to learning analytics | — | Not in scope |

---

## 6.0 Progress Tracking Module

### Student

| Function | S/U | Note |
|----------|-----|------|
| View personal dashboard with accuracy and trends | S | Summary, donut chart, recent sessions, weak topics |
| Browse session history with filters | S | Completed/expired sessions paginated and searchable |
| View topic progress per subject | S | Per-topic mastery and accuracy displayed |

### Faculty

| Function | S/U | Note |
|----------|-----|------|
| View course analytics dashboard | S | Accuracy, calibration matrix, interventions, AI summary |
| Drill into individual student performance | S | Student detail with sessions, answers and weak areas |
| Export intervention list as CSV | S | Scrambled identifiers for safe sharing |
| View course heatmap | S | Topic mastery grid against students |

### Chairperson

| Function | S/U | Note |
|----------|-----|------|
| View department programs dashboard | S | Performance summary and cross-program analytics |
| View course audit list | S | Participation status across offerings |
| View audit logs (faculty / students) | S | Activity logs displayed |

### Campus Administrator

| Function | S/U | Note |
|----------|-----|------|
| View campus dashboard with counts and pending items | S | Student/faculty counts, pending registrations, section status |

---

## 7.0 Data Storage Module

| Function | S/U | Note |
|----------|-----|------|
| Persistent storage for users, sessions, questions, feedback, mistakes, analytics | S | All modules write to database; migrations versioned |
| Media files (photos, uploads) stored and served | S | Profile photos, learning materials, mistake photos |