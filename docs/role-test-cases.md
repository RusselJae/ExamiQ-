# ExamiQ Role-Based Test Cases

**Student, Faculty and Program Coordinator — six main functionalities each**

This document defines the behavioral expectations, error handling, and system responses for the Student, Faculty, and Program Coordinator roles of the ExamiQ mathematics exam review platform. Each test case maps a specific user action to its expected success metric and potential system failure. The matrix serves as a validation blueprint to ensure account security, reliable examination workflows, and robust error recovery across the application.

---

## 1. How to read these test cases

| Column | Meaning |
|--------|---------|
| **Action** | The functionality being verified. |
| **Activities** | The steps the tester performs. |
| **System Response** | The behaviour the system must produce. |
| **Actual Errors** | The conditions that can interrupt the activity. |
| **Response** | The handling the system must apply. |

**Terms** — *Not allowed*: refused for the wrong role, or answered as not found
when the record is outside the user's area. *Draft*: saved but not yet offered to
students. *Approved*: live and visible. *Pending*: awaiting a decision. *Archived*:
kept for reference, hidden from daily lists, no longer able to sign in.

**Environment** — web application run locally; database rebuilt for every run;
emails captured so codes and notices can be read.

**Prepare before the run**

1. Campus administrator sets the current academic year and term.
2. Program coordinator adds the curriculum subjects.
3. Program coordinator creates the class sections.
4. Program coordinator assigns faculty to those sections.
5. Faculty writes and publishes questions for each course.
6. Faculty sets the time allowed per question.
7. Student completes the profile with programme, year level and section.

---

## 2. User: Student Side

| Action | Activities | System Response | Actual Errors | Response |
|--------|------------|-----------------|---------------|----------|
| **Create a student account** | Fill in the sign-up form, then enter the six-digit code from the email. | The account stays inactive until the code is confirmed. | Address or student number already used, section full or mismatched, code wrong or expired. | Each bad field is refused with its reason; a new code is offered when needed. |
| **Sign in to the student account** | Enter the email and password on the sign-in page. | The student lands on the personal dashboard with only their own data. | Wrong password, unconfirmed, deactivated or archived account, wrong role. | Bad details are refused on the form; closed accounts explain why. |
| **Set up and sit a practice exam** | Tick subjects, pick a difficulty and timer, answer each question with a confidence rating. | A session starts, answers are graded as submitted, and a summary ends it. | No subject ticked, timer out of range, no questions available, no confidence given. | The exam will not start or advance until the subject, timer and confidence are valid. |
| **Review mistakes and weak concepts** | Filter the mistakes list, open one record and follow the guided concept review. | The list and detail show the question, both answers and the explanation steps. | No mistakes yet, filter matches nothing, another student's record, empty message. | Empty states are explained, other records refused, and a bad photo rejected. |
| **Check personal performance** | Open the dashboard, switch the period, filter the session history and open topic progress. | The dashboard shows the summary and trend; the history lists finished sessions. | No finished sessions, filters match nothing, another student's data. | Zero-state figures are shown, filters are kept, and other students' data is refused. |
| **Ask faculty for help** | Send a question and a photo of the work in the conversation thread. | One thread links the student and their faculty member, who is notified. | Empty message, photo too large or the wrong type, another student's thread. | The message and photo are checked before sending; other threads are refused. |

---

## 3. User: Faculty Side

| Action | Activities | System Response | Actual Errors | Response |
|--------|------------|-----------------|---------------|----------|
| **Request a faculty account** | Fill in the sign-up form with the employee number and department, then confirm the code. | The request waits for approval; confirming the code only proves the address. | Employee number missing, address taken, password too weak. | Bad entries are refused and the account stays pending until a decision is made. |
| **Sign in to the faculty account** | Enter the email and password, then the emailed sign-in code. | The faculty overview opens, listing the courses handled and the work waiting. | Code wrong or expired, account pending or deactivated, wrong role. | The sign-in stays incomplete until the code works; blocked accounts explain why. |
| **Build the question bank** | Add topics to a subject, then write a question with choices and explanation steps. | Questions are saved as drafts, out of reach of students. | Duplicate topic, too few choices, no correct answer marked, another faculty member's course. | Each problem is named and the draft is kept; other courses are refused. |
| **Publish questions for students** | Filter the question list, tick the faculty attestation on a draft and publish it. | The question is approved, made active and added to the student pool. | Attestation not ticked, question deleted by a colleague, another faculty member's course. | Unattested questions stay drafts; other courses are refused. |
| **Configure the exam settings** | Set the timer, topics and difficulties on the exam setup, then save. | The settings are saved and the students become eligible to sit an exam. | Timer out of range, no difficulty ticked, another faculty member's course. | Invalid settings are refused with the rule named; other courses are refused. |
| **Review student performance** | Filter the roster, open a student or session, view the heatmap and export the intervention list. | The roster, student pages, heatmap and export all cover the faculty member's own students. | No sections assigned, student outside the scope, export with nobody flagged. | An empty roster explains itself, out-of-scope students are refused, and the export still returns headings. |

---

## 4. User: Program Coordinator Side

| Action | Activities | System Response | Actual Errors | Response |
|--------|------------|-----------------|---------------|----------|
| **Request a program coordinator account** | Register through the invitation link, then confirm the emailed code. | The request waits for approval; confirming the code only proves the address. | Link invalid or expired, department missing, address taken. | An invalid link opens nothing and bad entries are refused with their reason. |
| **Sign in to the program coordinator account** | Enter the email and password, then the emailed sign-in code. | The coordinator console opens with counts for the department's programmes and sections. | Code wrong, account pending, wrong role. | The sign-in stays incomplete until the code works; other roles are refused. |
| **Manage the subject catalog** | Add a subject, edit its details, then remove it from the catalogue. | Only the coordinator's own programmes are listed; adding creates the course copy. | Subject of another department, duplicate code, subject moved to another programme. | Out-of-scope subjects are refused, duplicate codes rejected, and a removal reports what was deleted. |
| **Manage the program sections** | Create one section, bulk-create several, then edit a capacity or repeat a section. | Sections of the managed programmes are listed with student counts and remaining places. | Section of another department, label not a number, capacity or count out of range, duplicate. | Only managed sections are shown; bad labels, capacities and duplicates are refused. |
| **Manage user accounts** | Filter the accounts, then approve, reject, deactivate, archive or restore one. | Only in-scope accounts are listed; each action changes the account and confirms. | Account not pending, pending account archived, own account managed, account of another department. | Invalid state changes are refused with a clear reason; out-of-scope accounts are not found. |
| **Assign teaching loads** | Choose a faculty member, sections, a subject and a term, then save. | A load is created per section and the course and exam setup are provisioned. | No section selected, subject of the wrong programme or year, same load twice, load of another department. | Mismatches are refused with the rule named; a repeated load is skipped, not duplicated. |

---

## 5. Summary checklist

### 5.1 Student

| Function | S/U | Note |
|----------|-----|------|
| Create Account | S | Sign up with year level and section, then confirm the code |
| Login Account | S | Taken straight to the personal dashboard |
| Sit a Practice Exam | S | Setup wizard, timed questions, confidence capture, summary |
| Review Mistakes | S | Wrong answers logged automatically, concept review available |
| Check Performance | S | Dashboard, session history and topic progress |
| Ask Faculty for Help | S | One thread per student, messages and photos supported |

### 5.2 Faculty

| Function | S/U | Note |
|----------|-----|------|
| Create Account | S | Request stays pending until it is approved |
| Login Account | S | Emailed sign-in code, then the faculty overview |
| Build the Question Bank | S | Topics and draft multiple-choice questions with explanation steps |
| Publish Questions | S | Faculty attestation is required before students see a question |
| Configure Exam Settings | S | Per-question timer, topics and difficulties; timer locks for students |
| Review Student Performance | S | Roster, student pages, heatmap and intervention export |

### 5.3 Program Coordinator

| Function | S/U | Note |
|----------|-----|------|
| Create Account | S | Invitation link only, request pending until approved |
| Login Account | S | Emailed sign-in code, then the coordinator console |
| Manage the Subject Catalog | S | Add, edit and remove subjects inside the department's programmes |
| Manage Program Sections | S | Single and bulk creation with capacity and label rules |
| Manage User Accounts | S | Approve, reject, deactivate, archive and restore inside the scope |
| Assign Teaching Loads | S | Links faculty member, sections, subject and term, with duplicate protection |

---

## 6. Issues noticed while preparing these test cases

| # | Area | What was noticed | Suggested handling |
|---|------|-------------------|-------------------|
| 1 | Subject catalogue | An invalid new subject fails the page instead of showing the reason. | Re-display the form with the specific reason. |
| 2 | Topic creation | A refused duplicate topic leaves the page unable to finish a later step. | Handle the refusal cleanly. |
| 3 | Question editor | The saved check still sends the old field names, so a complete question is refused. | Update the check to the current field names. |
| 4 | Faculty roster | Retired roster addresses are still advertised, sending staff to a page that no longer exists. | Remove the remaining references. |

---

## 7. Related documentation

- **Functional Testing** — the wider test list and checklist for the remaining roles.
- **System Flow** — how the data moves between the screens described above.
- **User Roles and Workflows** — what each role is responsible for.
