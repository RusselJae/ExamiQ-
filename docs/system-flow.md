# ExamiQ System Flow

ExamiQ is a self-regulated mathematics exam review system for college students. It combines timed review sessions, confidence-based test flow, explanatory feedback, mistake tracking, and role-based analytics for Faculty and department leadership.

This document describes how users, modules, and data move through the system from setup to review to reporting.

---

## 1. System overview

### External actors

| Actor | Role in the system |
|-------|-------------------|
| **Student** | Completes timed review sessions, views feedback, tracks mistakes and progress |
| **Faculty** | Configures exams, manages the question bank, monitors course performance |
| **Chairperson** | Assigns teaching load, approves questions, monitors program-level trends |
| **Campus Administrator** | Approves accounts, manages academic calendar and program sections |

### Core modules

| Module | Purpose |
|--------|---------|
| **1.0 User Management** | Registration, authentication, profiles, account approval |
| **2.0 Academic Content Management** | Curriculum, subjects, question authoring, distribution |
| **3.0 Exam Module** | Exam setup, timed review, confidence capture, explanatory feedback, AI tutor, mistake logging |
| **4.0 Summary Module** | Dashboards, session history, performance analytics for students and faculty |
| **5.0 Reports Module** | Organized reports for faculty and chairperson based on exam results and learning progress |

DFD diagrams for these modules are in [`docs/dfd/`](dfd/README.md). Mermaid source code is in [`docs/dfd/dfd-mermaid.md`](dfd/dfd-mermaid.md).

---

## 2. High-level system flow

```mermaid
flowchart TB
    subgraph Setup["Phase 1 — Campus & Content Setup"]
        A1[Campus Admin creates calendar & sections]
        A2[Chairperson assigns Faculty to sections]
        A3[Faculty configures exam setup]
        A4[Faculty creates questions]
        A5[Chairperson approves questions]
        A1 --> A2 --> A3 --> A4 --> A5
    end

    subgraph Review["Phase 2 — Student Review Cycle"]
        B1[Student completes profile]
        B2[Student starts timed review]
        B3[System delivers questions adaptively]
        B4[Answers graded & confidence inferred]
        B5[Mistakes logged automatically]
        B6[Session summary & recommendations]
        B1 --> B2 --> B3 --> B4 --> B5 --> B6
    end

    subgraph Response["Phase 3 — Instructional & Institutional Response"]
        C1[Student views dashboard & weak areas]
        C2[Faculty reviews course analytics]
        C3[Chairperson monitors program trends]
        B6 --> C1
        B6 --> C2
        B6 --> C3
    end

    A5 --> B2
```

---

## 3. Module interaction flow

During an active review session, modules interact in this order:

```mermaid
flowchart LR
    UM[1.0 User Management]
    ACM[2.0 Academic Content Management]
    EM[3.0 Exam Module]
    SM[4.0 Summary Module]
    RM[5.0 Reports Module]

    ACM -->|questions| EM
    EM -->|exam results| SM
    SM -->|summary data| RM
    EM -->|explanations and mistakes| Student((Student))
    SM -->|dashboard| Student
    SM -->|student detail| Faculty((Faculty))
    RM -->|course and program reports| Faculty
    RM -->|program reports| Chairperson((Chairperson))

    UM & ACM & EM & SM & RM --> DB[(PostgreSQL db1 stores)]
```

---

## 4. End-to-end flows by phase

### Flow A — Account lifecycle

```mermaid
sequenceDiagram
    actor User
    participant Signup as /accounts/signup/
    participant Admin as Campus Admin
    participant Auth as User Management
    participant Dashboard as Role Dashboard

    User->>Signup: Register (Student / Faculty / Chairperson)
    alt Student
        Signup->>Auth: Create approved account
        Auth->>Dashboard: Redirect to /student/dashboard/
    else Faculty or Chairperson
        Signup->>Auth: Create pending account
        Admin->>Auth: Approve or reject at /campus/users/
        Auth->>Dashboard: Redirect on approval
    end
    User->>Auth: Maintain profile at /profile/
```

| Step | Action |
|------|--------|
| 1 | User visits the landing page and signs up at `/accounts/signup/` |
| 2 | Student accounts are activated immediately; Faculty and Chairperson accounts enter **pending** status |
| 3 | Campus Administrator reviews pending registrations at `/campus/users/` |
| 4 | Approved user logs in and is redirected to their role home page |
| 5 | All users maintain profile and notifications at `/profile/` |

**Post-login destinations**

| Role | Home URL |
|------|----------|
| Student | `/student/dashboard/` |
| Faculty | `/professor/courses/` |
| Chairperson | `/chairperson/dashboard/` |
| Campus Administrator | `/admin/` or `/campus/` |

---

### Flow B — Content and access pipeline

```mermaid
flowchart TD
    CA[Campus Admin<br/>calendar & sections] --> CP[Chairperson<br/>teaching assignments]
    CP --> CO[Course offering & exam setup created]
    CO --> FC[Faculty configures exam setup]
    FC --> QB[Faculty creates questions]
    QB --> PEND[PENDING status]
    PEND --> APR{Chairperson<br/>approves?}
    APR -->|Yes| ACTIVE[APPROVED — available in sessions]
    APR -->|No| REJ[REJECTED]
```

| Step | Actor | Action |
|------|-------|--------|
| 1 | Campus Administrator | Creates academic years, terms, and program sections; sets current term |
| 2 | Chairperson | Creates teaching assignments (Faculty + section + subject + term) |
| 3 | System | Creates course offering and exam setup for each assignment |
| 4 | Faculty | Enables exam setup — topics, difficulties, duration, per-question timer |
| 5 | Faculty | Creates questions manually or with AI assistance |
| 6 | System | All new questions enter **PENDING** status |
| 7 | Chairperson | Reviews and approves or rejects questions |
| 8 | System | Approved, active questions enter the student review pool |

**Question lifecycle**

```
Faculty creates question
        │
        ▼
     PENDING ──── Chairperson rejects ────► REJECTED
        │
        ▼
  Chairperson approves
        │
        ▼
     APPROVED (active in sessions)
```

If Faculty edits an approved question, it returns to **PENDING** and must be re-approved. Faculty can deactivate questions at any time to remove them from the active pool.

---

### Flow C — Student review cycle

```mermaid
flowchart TD
    P[Profile complete<br/>program, year level, section]
    E{Eligibility checks pass?}
    S[Start Review — select subject, topic, difficulty, duration]
    T[Timed session begins]
    Q[Adaptive question delivery]
    A[Student answers within time limit]
    G[Grade answer & infer confidence from response time]
    W{Wrong answer?}
    M[Log mistake]
    N{More questions<br/>or time left?}
    SUM[Session summary — calibration insights & recommendations]
    AN[Dashboard, history, mistakes, topic progress]

    P --> E
    E -->|No| BLOCK[Show eligibility message]
    E -->|Yes| S --> T --> Q --> A --> G --> W
    W -->|Yes| M --> N
    W -->|No| N
    N -->|Yes| Q
    N -->|No| SUM --> AN
```

**Eligibility requirements** (checked before a session can start):

- Student profile has section and year level set
- Year level matches assigned section
- A current academic term is active
- At least one teaching assignment exists for the student's section with exam setup enabled by Faculty

**During the exam**

- Countdown timer with per-question time limit
- Questions selected adaptively (prior mistakes, high-confidence wrong answers, unseen items)
- Explanations are **not** shown during the exam — they appear on the session summary afterward

**After the exam**

- Session summary at `/student/review/<id>/summary/`
- Accuracy, calibration insights (mastery, misconception, lucky guess, expected gap)
- Data feeds Dashboard, Session History, Mistakes, Weak Areas, and Topic Progress

---

### Flow D — Instructional response (Faculty)

```mermaid
flowchart LR
    S[Student session data] --> CA[Course analytics & roster]
    CA --> IL[Intervention list flagged]
    IL --> SD[Student detail drill-down]
    IL --> CSV[Intervention CSV export]
    CA --> FB[Edit feedback on high-mistake questions]
    CA --> AI[AI course summary optional]
```

| Step | Action |
|------|--------|
| 1 | Faculty opens course analytics or roster |
| 2 | System flags students on the intervention list (accuracy, calibration gaps, practice frequency) |
| 3 | Faculty drills into individual student performance |
| 4 | Faculty exports intervention CSV for follow-up |
| 5 | Faculty edits explanations on commonly missed questions |
| 6 | Faculty may generate an AI course summary for reporting |

---

### Flow E — Institutional oversight (Chairperson)

```mermaid
flowchart LR
    PD[Programs dashboard] --> CP[Cross-program analytics]
    PD --> QR[Question review queue]
    QR --> AP[Approve / reject / edit-then-approve]
    PD --> AUD[Course audit — active review participation]
```

| Step | Action |
|------|--------|
| 1 | Chairperson views Programs dashboard for department-wide performance |
| 2 | Chairperson monitors pending questions and approves or rejects submissions |
| 3 | Chairperson reviews cross-program analytics by home degree program |
| 4 | Chairperson audits which courses have active student review participation |

---

## 5. Role workflow summary

### Student

1. Set **home degree program**, year level, and section in Profile
2. **Start Review** — offerings filtered to the student's program and section
3. Select topic, difficulty, and duration
4. Complete timed session with confidence-inferred answers
5. Review session summary, mistakes, weak areas, and topic progress

### Faculty

| Action | URL |
|--------|-----|
| Overview | `/professor/overview/` |
| My Courses | `/professor/courses/` |
| Course analytics | `/professor/courses/<id>/` |
| Exam setup | `/professor/courses/<id>/exam-setup/` |
| Question bank | `/professor/courses/<id>/questions/` |
| Feedback editing | `/professor/courses/<id>/feedback/` |

### Chairperson

| Action | URL |
|--------|-----|
| Programs dashboard | `/chairperson/dashboard/` |
| Question review | Chairperson question review views |
| Cross-program analytics | Department-scoped program analytics |
| Teaching assignments | Create assignments linking Faculty, section, subject, term |

### Campus Administrator

| Action | URL |
|--------|-----|
| User approval | `/campus/users/` |
| Program sections | `/campus/sections/` |
| Academic calendar | `/campus/academic-calendar/` |
| Campus dashboard | `/campus/` |

---

## 6. Program scoping

Content is organized by **degree program**. Each of the eight programs owns its own math subjects, topics, and question bank.

| Slug | Program |
|------|---------|
| `cs` | Computer Science |
| `it` | Information Technology |
| `bsed_math` | BSEd Mathematics |
| `psychology` | Psychology |
| `marketing` | Marketing |
| `hr` | Human Resources |
| `hospitality` | Hospitality Management |
| `criminology` | Criminology |

```mermaid
flowchart LR
    Program[Program]
    Topic[Topics & questions]
    Course[Course offerings]
    Student[Student home_degree_program]
    Chair[Chairperson]

    Program --> Topic
    Program --> Course
    Student -->|matches slug| Program
    Chair -->|approves questions for| Program
```

---

## 7. Data persistence map

| Data | Primary module | Store |
|------|----------------|-------|
| User profiles & auth | 1.0 User Management | `examiq_db/Users` |
| Questions & curriculum | 2.0 Academic Content Management | `examiq_db/Questions` |
| Review sessions, feedback, mistakes | 3.0 Exam Module | `examiq_db/Sessions`, `Feedback`, `Mistakes` |
| Performance analytics | 4.0 Summary Module | `examiq_db/Analytics` |
| Formal reports | 5.0 Reports Module | `examiq_db/Analytics` (read) |

All modules read and write directly to the `db1` PostgreSQL data stores shown in the DFD set.

---

## 8. Related documentation

| Document | Description |
|----------|-------------|
| [`docs/functional-testing.md`](functional-testing.md) | Functional test cases and module checklist (Appendix A–C) |
| [`docs/functional-testing.pdf`](functional-testing.pdf) | PDF export of functional testing and test cases |
| [`docs/dfd/README.md`](dfd/README.md) | Data Flow Diagrams (Level 1 and Level 2.1–2.5) |
| [`docs/user-guide.txt`](user-guide.txt) | Full user guide with navigation and permissions |
| [`docs/user-roles-and-workflows.md`](user-roles-and-workflows.md) | Role permissions and domain model reference |
