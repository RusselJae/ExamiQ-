# ExamiQ Sequence Diagrams (Landscape)

Two landscape sequence diagrams: **two independent panels side-by-side** with a gap, colored headers, and role descriptions (no legend, no panel borders).

## Files

| File | Description |
|------|-------------|
| `sequence-diagram-admin-chairperson.png` | Campus Admin \| Chairperson (landscape) |
| `sequence-diagram-student-faculty.png` | Student \| Faculty (landscape) |
| `panels/campus-admin.mmd` | Campus Admin panel source |
| `panels/chairperson.mmd` | Chairperson panel source |
| `panels/student.mmd` | Student panel source |
| `panels/faculty.mmd` | Faculty panel source |
| `../../scripts/generate_sequence_diagrams.py` | Renders panels and composites landscape PNGs |

Regenerate:

```bash
python scripts/generate_sequence_diagrams.py
```

---

## Diagram 1 — Campus Admin | Chairperson

![Campus Admin and Chairperson](sequence-diagram-admin-chairperson.png)

### Panel 1 — Campus Admin (blue)

```mermaid
sequenceDiagram
    autonumber
    actor CA as Campus Admin
    participant Sys as ExamiQ+ System
    participant DB as Database

    CA->>Sys: Login Credentials
    activate Sys
    Sys->>DB: Validate Account
    activate DB
    DB-->>Sys: Account Verified
    deactivate DB
    Sys-->>CA: Access Granted
    deactivate Sys
    CA->>Sys: Display Dashboard

    Note over CA,Sys: Manage User Accounts
    CA->>Sys: Approve / Reject Staff
    activate Sys
    Sys->>DB: Update User Status
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>CA: Success Message
    deactivate Sys
    CA->>Sys: Display Updated Records

    Note over CA,Sys: Manage Program Sections
    CA->>Sys: Create / Update Sections
    activate Sys
    Sys->>DB: Save Section Data
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>CA: Success Message
    deactivate Sys
    CA->>Sys: Display Section List

    Note over CA,Sys: Academic Calendar
    CA->>Sys: Set Current Year & Term
    activate Sys
    Sys->>DB: Save Calendar Data
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>CA: Success Message
    deactivate Sys

    Note over CA,Sys: Logout
    CA->>Sys: Logout Request
    activate Sys
    Sys->>DB: End Session
    activate DB
    DB-->>Sys: Session Ended
    deactivate DB
    Sys-->>CA: Logout Successful
    deactivate Sys
```

### Panel 2 — Chairperson (green)

```mermaid
sequenceDiagram
    autonumber
    actor Chair as Chairperson
    participant Sys as ExamiQ+ System
    participant DB as Database

    Chair->>Sys: Login Credentials
    activate Sys
    Sys->>DB: Validate Account
    activate DB
    DB-->>Sys: Account Verified
    deactivate DB
    Sys-->>Chair: Access Granted
    deactivate Sys
    Chair->>Sys: Display Dashboard

    Note over Chair,Sys: Manage Teaching Assignments
    Chair->>Sys: Assign Faculty to Sections
    activate Sys
    Sys->>DB: Save Assignment Data
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>Chair: Success Message
    deactivate Sys
    Chair->>Sys: Display Assignment Records

    Note over Chair,Sys: View Program Analytics
    Chair->>Sys: Request Performance Data
    activate Sys
    Sys->>DB: Retrieve Analytics
    activate DB
    DB-->>Sys: Performance Data
    deactivate DB
    Sys-->>Chair: Display Reports
    deactivate Sys

    Note over Chair,Sys: Audit Logs & Course Audit
    Chair->>Sys: Request Audit Logs
    activate Sys
    Sys->>DB: Retrieve Log Data
    activate DB
    DB-->>Sys: Log Records
    deactivate DB
    Sys-->>Chair: Display Audit Reports
    deactivate Sys

    Note over Chair,Sys: Logout
    Chair->>Sys: Logout Request
    activate Sys
    Sys->>DB: End Session
    activate DB
    DB-->>Sys: Session Ended
    deactivate DB
    Sys-->>Chair: Logout Successful
    deactivate Sys
```

---

## Diagram 2 — Student | Faculty

![Student and Faculty](sequence-diagram-student-faculty.png)

### Panel 1 — Student (purple)

```mermaid
sequenceDiagram
    autonumber
    actor Stu as Student
    participant Sys as ExamiQ+ System
    participant DB as Database

    Stu->>Sys: Login Credentials
    activate Sys
    Sys->>DB: Validate Account
    activate DB
    DB-->>Sys: Account Verified
    deactivate DB
    Sys-->>Stu: Access Granted
    deactivate Sys
    Stu->>Sys: Display Dashboard

    Note over Stu,Sys: Start Review Session
    Stu->>Sys: Start Review Session
    activate Sys
    Sys->>DB: Retrieve Question Set
    activate DB
    DB-->>Sys: Question Data
    deactivate DB
    Sys-->>Stu: Display First Question
    deactivate Sys

    loop LOOP UNTIL EXAM COMPLETED
        Stu->>Sys: Submit Answer & Confidence
        activate Sys
        Sys->>DB: Save Answer Data
        activate DB
        DB-->>Sys: Confirmation
        deactivate DB
        Sys->>DB: Evaluate Answer
        activate DB
        DB-->>Sys: Result Data
        deactivate DB
        Sys-->>Stu: Real-Time Feedback
        Sys->>DB: Record Mistake & Analytics
        activate DB
        DB-->>Sys: Updated Records
        deactivate DB
        Sys->>DB: Get Next Adaptive Question
        activate DB
        DB-->>Sys: Next Question
        deactivate DB
        Sys-->>Stu: Display Next Question
        deactivate Sys
    end

    Note over Stu,Sys: Session Summary
    Stu->>Sys: Finish Session
    activate Sys
    Sys->>DB: Generate Summary
    activate DB
    DB-->>Sys: Performance Data
    deactivate DB
    Sys-->>Stu: Display Performance Report
    deactivate Sys

    Note over Stu,Sys: Logout
    Stu->>Sys: Logout Request
    activate Sys
    Sys->>DB: End Session
    activate DB
    DB-->>Sys: Session Ended
    deactivate DB
    Sys-->>Stu: Logout Successful
    deactivate Sys
```

### Panel 2 — Faculty (green)

```mermaid
sequenceDiagram
    autonumber
    actor Fac as Faculty
    participant Sys as ExamiQ+ System
    participant DB as Database

    Fac->>Sys: Login Credentials
    activate Sys
    Sys->>DB: Validate Account
    activate DB
    DB-->>Sys: Account Verified
    deactivate DB
    Sys-->>Fac: Access Granted
    deactivate Sys
    Fac->>Sys: Display Dashboard

    Note over Fac,Sys: Manage Exam Setup
    Fac->>Sys: Configure Exam Settings
    activate Sys
    Sys->>DB: Save Exam Setup
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>Fac: Success Message
    deactivate Sys

    Note over Fac,Sys: Manage Question Bank
    Fac->>Sys: Add / Edit Questions
    activate Sys
    Sys->>DB: Save Question Data
    activate DB
    DB-->>Sys: Confirmation
    deactivate DB
    Sys-->>Fac: Success Message
    deactivate Sys
    Fac->>Sys: Display Updated Records

    Note over Fac,Sys: View Performance Reports
    Fac->>Sys: Request Analytics
    activate Sys
    Sys->>DB: Retrieve Performance Data
    activate DB
    DB-->>Sys: Analytics Data
    deactivate DB
    Sys-->>Fac: Display Reports
    deactivate Sys

    Note over Fac,Sys: Logout
    Fac->>Sys: Logout Request
    activate Sys
    Sys->>DB: End Session
    activate DB
    DB-->>Sys: Session Ended
    deactivate DB
    Sys-->>Fac: Logout Successful
    deactivate Sys
```
