#!/usr/bin/env python3
"""Generate docs/thesis/user-flows-and-panel-questions.pdf."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from panel_qa_data import PANEL_QA  # noqa: E402

OUTPUT = ROOT / "docs" / "thesis" / "user-flows-and-panel-questions.pdf"

styles = getSampleStyleSheet()
TITLE = ParagraphStyle(
    "Title", parent=styles["Heading1"], fontSize=16, spaceAfter=6, alignment=TA_CENTER
)
SUBTITLE = ParagraphStyle(
    "Subtitle", parent=styles["Normal"], fontSize=10, spaceAfter=14, alignment=TA_CENTER
)
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13, spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=6)
H3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=10, spaceBefore=8, spaceAfter=4)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=13, alignment=TA_LEFT)
BULLET = ParagraphStyle(
    "Bullet", parent=styles["Normal"], fontSize=9, leading=13, leftIndent=14, bulletIndent=0
)
QA_Q = ParagraphStyle(
    "QAQ",
    parent=styles["Normal"],
    fontSize=9,
    leading=13,
    spaceBefore=8,
    leftIndent=0,
    fontName="Helvetica-Bold",
)
QA_A = ParagraphStyle(
    "QAA",
    parent=styles["Normal"],
    fontSize=9,
    leading=13,
    spaceAfter=4,
    leftIndent=12,
    textColor=colors.HexColor("#1a1a1a"),
)
CELL = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=11)
CELL_HDR = ParagraphStyle(
    "CellHdr", parent=styles["Normal"], fontSize=8, leading=11, textColor=colors.white
)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.grey)


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def para(text: str, style=BODY) -> Paragraph:
    return Paragraph(esc(text), style)


def bullet(text: str) -> Paragraph:
    return Paragraph(f"&bull; {esc(text)}", BULLET)


def make_table(headers, rows, col_widths=None):
    data = [[para(h, CELL_HDR) for h in headers]]
    for row in rows:
        data.append([para(str(c), CELL) for c in row])
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f5f7fa")],
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def section_heading(text: str):
    return [para(text, H1), Spacer(1, 4)]


def subsection_heading(text: str):
    return [para(text, H2), Spacer(1, 2)]


def body_paragraphs(*paragraphs: str):
    return [para(p) for p in paragraphs] + [Spacer(1, 6)]


def bullet_list(*items: str):
    return [bullet(item) for item in items] + [Spacer(1, 6)]


def qa_pair(question: str, answer: str) -> list:
    return [
        para(f"Q: {question}", QA_Q),
        para(f"A: {answer}", QA_A),
    ]


def flow_block(title: str, steps: list[str]):
    elements = [para(title, H3)]
    for i, step in enumerate(steps, 1):
        elements.append(para(f"{i}. {step}"))
    elements.append(Spacer(1, 8))
    return elements


def build_story():
    story = []

    # Title page
    story.append(Spacer(1, 3 * cm))
    story.append(para("ExamiQ+", TITLE))
    story.append(para("User Flows, System Locations, and Panel Q&A", SUBTITLE))
    story.append(para("Pure logic reference for thesis defense", SUBTITLE))
    story.append(Spacer(1, 1 * cm))
    story.append(
        para(
            "This document maps each user role to where they act in the system, "
            "the step-by-step logic for major functions, and panelist questions with suggested answers.",
            BODY,
        )
    )
    story.append(PageBreak())

    # Part 1: System overview
    story.extend(section_heading("Part 1 — System Overview"))
    story.extend(
        body_paragraphs(
            "ExamiQ+ is a self-regulated mathematics exam review platform for college students. "
            "It evaluates whether confidence-aware review improves calibration awareness and "
            "self-regulated learning (SRL). Content is math-only and scoped by degree program. "
            "Eight programs exist: Computer Science, Information Technology, BSEd Mathematics, "
            "Psychology, Marketing, Human Resources, Hospitality Management, and Criminology.",
            "The system operates in three phases: (1) campus and content setup, "
            "(2) student review cycle, and (3) instructional and institutional response. "
            "Each phase involves different roles at different locations in the application.",
        )
    )

    story.extend(subsection_heading("1.1 User Roles and Entry Points"))
    story.append(
        make_table(
            ["Role", "Registration", "Approval", "Post-Login Home"],
            [
                (
                    "Student",
                    "/accounts/signup/",
                    "Immediate (approved, active)",
                    "/student/dashboard/",
                ),
                (
                    "Faculty (Professor)",
                    "/accounts/signup/",
                    "Pending until campus admin approves",
                    "/professor/courses/",
                ),
                (
                    "Chairperson",
                    "/accounts/signup/ (department required)",
                    "Pending until campus admin approves",
                    "/chairperson/dashboard/",
                ),
                (
                    "Campus Administrator",
                    "Provisioned by admin (not public signup)",
                    "Active on creation",
                    "/campus/ or /admin/",
                ),
            ],
            col_widths=[3.2 * cm, 3.5 * cm, 5.3 * cm, 4.5 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("1.2 Role-Based Access Logic"))
    story.extend(
        bullet_list(
            "Students may only access /student/ routes and shared profile routes.",
            "Faculty may only access /professor/ routes for courses they own.",
            "Chairpersons see department-scoped data at /chairperson/ based on their department.",
            "Campus administrators manage users, sections, and calendar at /campus/.",
            "Cross-role URL access returns HTTP 403. Unauthenticated access redirects to login.",
        )
    )

    story.extend(subsection_heading("1.3 Core Modules"))
    story.append(
        make_table(
            ["Module", "Purpose", "Primary Actors"],
            [
                ("User Management", "Registration, login, profile, approval", "All roles"),
                (
                    "Academic Content",
                    "Sections, assignments, topics, question bank",
                    "Campus admin, chairperson, faculty",
                ),
                ("Exam Module", "Timed review, grading, confidence, feedback", "Student, faculty"),
                ("Summary Module", "Dashboards, session history, progress", "Student, faculty"),
                ("Reports Module", "Analytics, interventions, research export", "Faculty, chairperson"),
            ],
            col_widths=[3.5 * cm, 7.5 * cm, 5.5 * cm],
        )
    )
    story.append(PageBreak())

    # Part 2: Function-by-function user location
    story.extend(section_heading("Part 2 — Where Users Go for Each Function"))

    story.extend(subsection_heading("2.1 Authentication and Account Management"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "Register",
                    "Student, Faculty, Chairperson",
                    "/accounts/signup/",
                    "Role selected at signup. Student is active immediately. Faculty and chair enter pending status.",
                ),
                (
                    "Log in",
                    "All",
                    "/accounts/login/",
                    "On success, redirect to role dashboard. Pending/rejected faculty and chair are blocked.",
                ),
                (
                    "Log out",
                    "All",
                    "/accounts/logout/",
                    "Session ends; redirect to login.",
                ),
                (
                    "Edit profile",
                    "All",
                    "/profile/",
                    "Name, photo, email, password. Students also set home degree program, year level, section.",
                ),
                (
                    "View notifications",
                    "All",
                    "/profile/notifications/",
                    "System notifications for the authenticated user.",
                ),
                (
                    "Approve registration",
                    "Campus admin",
                    "/campus/users/ → /campus/users/<pk>/approve/",
                    "Activates pending faculty or chairperson accounts.",
                ),
                (
                    "Reject registration",
                    "Campus admin",
                    "/campus/users/",
                    "Sets rejected status; user cannot log in.",
                ),
                (
                    "Create faculty/chair account",
                    "Campus admin",
                    "/campus/users/create/professor/ or /create/chairperson/",
                    "Direct provisioning of approved active accounts.",
                ),
            ],
            col_widths=[2.8 * cm, 2.5 * cm, 4.5 * cm, 6.7 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("2.2 Campus and Academic Setup"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "Set current academic year/term",
                    "Campus admin",
                    "/campus/academic-calendar/",
                    "Required gate: students cannot start review without a current term.",
                ),
                (
                    "Create program sections",
                    "Campus admin",
                    "/campus/sections/",
                    "Defines cohorts with capacity for student signup and assignments.",
                ),
                (
                    "View campus dashboard",
                    "Campus admin",
                    "/campus/",
                    "Pending registrations and setup status overview.",
                ),
                (
                    "Create teaching assignment",
                    "Chairperson",
                    "/chairperson/assignments/create/",
                    "Links faculty + section + subject + term. Auto-creates course and exam setup.",
                ),
                (
                    "Manage teaching assignments",
                    "Chairperson",
                    "/chairperson/assignments/",
                    "Primary way students receive subjects for review.",
                ),
            ],
            col_widths=[2.8 * cm, 2.5 * cm, 4.5 * cm, 6.7 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("2.3 Faculty — Course and Content Management"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "View all courses",
                    "Faculty",
                    "/professor/courses/",
                    "Lists courses owned by the logged-in professor.",
                ),
                (
                    "Create course",
                    "Faculty",
                    "/professor/courses/create/",
                    "Self-create when no chair assignments exist.",
                ),
                (
                    "Configure exam setup",
                    "Faculty",
                    "/professor/courses/<pk>/exam-setup/",
                    "Enable review, set topics, difficulties, duration, per-question timer. Gates student eligibility.",
                ),
                (
                    "Manage topics",
                    "Faculty",
                    "/professor/courses/<pk>/topics/",
                    "Topic list for the course program.",
                ),
                (
                    "Create questions",
                    "Faculty",
                    "/professor/courses/<pk>/questions/create/",
                    "New questions enter PENDING status until chair approval.",
                ),
                (
                    "View question bank",
                    "Faculty",
                    "/professor/courses/<pk>/questions/",
                    "List, edit, deactivate questions. Edit of approved question returns to PENDING.",
                ),
                (
                    "AI-generate questions",
                    "Faculty",
                    "/professor/courses/<pk>/questions/ai-generate/",
                    "Draft questions via LLM; still requires approval.",
                ),
                (
                    "Edit feedback/explanations",
                    "Faculty",
                    "/professor/courses/<pk>/feedback/",
                    "Improve step-by-step explanations on high-mistake items.",
                ),
                (
                    "Manage review windows",
                    "Faculty",
                    "/professor/courses/<pk>/windows/",
                    "Optional scheduled review windows (timed or practice mode on model).",
                ),
            ],
            col_widths=[2.6 * cm, 2.0 * cm, 4.8 * cm, 7.1 * cm],
        )
    )
    story.append(PageBreak())

    story.extend(subsection_heading("2.4 Chairperson — Oversight and Approval"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "Programs dashboard",
                    "Chairperson",
                    "/chairperson/dashboard/",
                    "Department-scoped per-program performance metrics.",
                ),
                (
                    "Cross-program analytics",
                    "Chairperson",
                    "/chairperson/analytics/by-program/",
                    "Analytics grouped by student home degree program within department.",
                ),
                (
                    "Course audit",
                    "Chairperson",
                    "/chairperson/courses/",
                    "Courses with review participation from department students.",
                ),
                (
                    "Approve/reject questions",
                    "Chairperson",
                    "Intended: /chairperson/questions/review/",
                    "Service layer exists. Approval limited to programs managed by chair's department.",
                ),
                (
                    "Faculty audit logs",
                    "Chairperson",
                    "/chairperson/logs/faculty/",
                    "Activity logs for faculty in department scope.",
                ),
                (
                    "Student audit logs",
                    "Chairperson",
                    "/chairperson/logs/students/",
                    "Activity logs for students in department scope.",
                ),
                (
                    "Research data export",
                    "Chairperson",
                    "Intended: /chairperson/research/export/",
                    "Anonymized CSV with calibration and survey columns for thesis analysis.",
                ),
            ],
            col_widths=[2.6 * cm, 2.2 * cm, 4.6 * cm, 7.1 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("2.5 Student — Review and Learning"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "View performance dashboard",
                    "Student",
                    "/student/dashboard/",
                    "Accuracy, calibration summary, recommendations.",
                ),
                (
                    "Start review",
                    "Student",
                    "/student/review/setup/",
                    "Wizard: subject → topic → difficulty → duration. Filtered to home program.",
                ),
                (
                    "Take timed exam",
                    "Student",
                    "/student/review/<pk>/",
                    "Per-question countdown. Confidence inferred from response time.",
                ),
                (
                    "Submit answer",
                    "Student",
                    "/student/review/<pk>/answer/<question_id>/",
                    "Answer graded; wrong answers logged as mistakes.",
                ),
                (
                    "View session summary",
                    "Student",
                    "/student/review/<pk>/summary/",
                    "Calibration matrix, accuracy, recommendations. Explanations shown here, not during exam.",
                ),
                (
                    "View step feedback",
                    "Student",
                    "/student/review/<pk>/feedback/<answer_id>/",
                    "Step-by-step explanation after session.",
                ),
                (
                    "AI tutor",
                    "Student",
                    "/student/review/<pk>/tutor/chat/",
                    "Post-session AI assistance when provider configured.",
                ),
                (
                    "Session history",
                    "Student",
                    "/student/sessions/",
                    "Past review sessions.",
                ),
                (
                    "View mistakes",
                    "Student",
                    "/student/mistakes/",
                    "Auto-logged wrong answers.",
                ),
                (
                    "Weak areas",
                    "Student",
                    "/student/mistakes/patterns/",
                    "Mistake patterns by topic.",
                ),
                (
                    "Topic progress",
                    "Student",
                    "/student/topics/",
                    "Mastery progress per topic.",
                ),
            ],
            col_widths=[2.6 * cm, 2.0 * cm, 4.8 * cm, 7.1 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("2.6 Faculty — Analytics and Intervention"))
    story.append(
        make_table(
            ["Function", "Who", "System Location (URL)", "Logic"],
            [
                (
                    "Cross-course overview",
                    "Faculty",
                    "/professor/overview/",
                    "Summary across all owned courses.",
                ),
                (
                    "Course analytics",
                    "Faculty",
                    "/professor/courses/<pk>/",
                    "Calibration breakdown, intervention flags.",
                ),
                (
                    "Course roster",
                    "Faculty",
                    "/professor/courses/<pk>/roster/",
                    "Students who participated in review for this course.",
                ),
                (
                    "Student drill-down",
                    "Faculty",
                    "/professor/courses/<course_pk>/roster/<student_pk>/",
                    "Individual student performance in course context.",
                ),
                (
                    "Topic heatmap",
                    "Faculty",
                    "/professor/courses/<pk>/heatmap/",
                    "Visual topic-level performance.",
                ),
                (
                    "Export interventions CSV",
                    "Faculty",
                    "/professor/courses/<pk>/interventions/export/",
                    "Flagged students with accuracy and suggested actions.",
                ),
            ],
            col_widths=[2.6 * cm, 2.0 * cm, 4.8 * cm, 7.1 * cm],
        )
    )
    story.append(PageBreak())

    # Part 3: Step-by-step flows
    story.extend(section_heading("Part 3 — Step-by-Step User Flows (Pure Logic)"))

    story.extend(
        flow_block(
            "Flow A — Account Lifecycle",
            [
                "User visits landing page (/) or goes directly to /accounts/signup/.",
                "User selects role: Student, Faculty, or Chairperson and submits registration form.",
                "If Student: account is approved and active immediately; redirect to /student/dashboard/.",
                "If Faculty or Chairperson: account is pending and inactive; user sees pending message at login.",
                "Campus administrator opens /campus/users/, reviews pending accounts, approves or rejects.",
                "On approval: faculty redirect to /professor/courses/; chairperson to /chairperson/dashboard/.",
                "All users maintain profile at /profile/ throughout their use of the system.",
            ],
        )
    )

    story.extend(
        flow_block(
            "Flow B — Institutional Setup (Prerequisite Pipeline)",
            [
                "Campus admin sets current academic year and term at /campus/academic-calendar/.",
                "Campus admin creates program sections at /campus/sections/ with capacity limits.",
                "Chairperson creates teaching assignments at /chairperson/assignments/create/.",
                "System auto-creates Course offering and ExamSetup for each assignment.",
                "Faculty opens /professor/courses/<pk>/exam-setup/ and enables exam with topics, difficulties, timer.",
                "Faculty creates questions at /professor/courses/<pk>/questions/; each enters PENDING status.",
                "Chairperson approves questions (intended UI at question review; service layer enforces department scope).",
                "Approved and active questions enter the student review pool.",
            ],
        )
    )

    story.extend(
        flow_block(
            "Flow C — Student Review Session",
            [
                "Student sets home degree program, year level, and section in /profile/.",
                "System checks eligibility: profile complete, year matches section, current term active, enabled exam setup exists for section.",
                "If ineligible: block session; show eligibility message.",
                "Student opens /student/review/setup/ (sidebar: Start Review).",
                "Student selects subject, topic, difficulty, and duration via setup wizard.",
                "System creates ReviewSession in timed_exam mode; redirect to /student/review/<pk>/.",
                "Questions delivered adaptively (prior mistakes, high-confidence wrong answers, unseen items).",
                "Per-question timer runs; confidence inferred from response time vs. time limit.",
                "Student submits answers; system grades, logs mistakes on wrong answers.",
                "Explanations are withheld during exam; brief answer reveal only in timed mode.",
                "Session ends; redirect to /student/review/<pk>/summary/ with calibration insights.",
                "Student may follow up via Session History, Mistakes, Weak Areas, Topic Progress.",
            ],
        )
    )

    story.extend(
        flow_block(
            "Flow D — Faculty Instructional Response",
            [
                "Student session data aggregates into course analytics.",
                "Faculty opens /professor/courses/<pk>/ or roster view.",
                "System flags students on intervention list based on accuracy, calibration gaps, practice frequency.",
                "Faculty drills into individual student at roster student detail page.",
                "Faculty exports intervention CSV for follow-up at interventions export URL.",
                "Faculty edits explanations on high-mistake questions at feedback list.",
                "Optional: faculty generates AI course summary for reporting.",
            ],
        )
    )

    story.extend(
        flow_block(
            "Flow E — Chairperson Institutional Oversight",
            [
                "Chairperson views /chairperson/dashboard/ for department-wide program metrics.",
                "Chairperson manages teaching assignments to link faculty to sections and subjects.",
                "Chairperson reviews pending questions and approves or rejects (department-scoped programs only).",
                "Chairperson monitors cross-program analytics by student home degree program.",
                "Chairperson audits course participation at /chairperson/courses/.",
                "For thesis: chairperson exports anonymized research CSV with calibration and survey data.",
            ],
        )
    )

    story.extend(
        flow_block(
            "Flow F — Pilot Study Participant (Thesis)",
            [
                "Student logs in and sets home degree program in /profile/.",
                "Optional: submit pilot study consent (checkbox).",
                "Complete pre-survey (Likert 1–5) from profile before or during pilot.",
                "Student completes review sessions during pilot period (Flow C).",
                "Submit post-survey from profile after using the system (no session gate).",
                "Chairperson exports anonymized data: student hash, program, sessions, calibration counts, survey scores.",
            ],
        )
    )

    story.extend(subsection_heading("3.1 Question Lifecycle Logic"))
    story.extend(
        bullet_list(
            "Faculty creates or edits question → status PENDING.",
            "Chairperson approves → status APPROVED; question is active in sessions if is_active=True.",
            "Chairperson rejects → status REJECTED; not available in sessions.",
            "Faculty edits approved question → returns to PENDING; requires re-approval.",
            "Faculty deactivates question → removed from active pool regardless of status.",
        )
    )

    story.extend(subsection_heading("3.2 Calibration Classification Logic"))
    story.append(
        make_table(
            ["Classification", "Condition", "Instructional Meaning"],
            [
                ("Mastery", "High confidence + correct", "Student knows the material well."),
                ("Misconception", "High confidence + wrong", "Confident but incorrect; priority intervention target."),
                ("Lucky guess", "Low confidence + correct", "Correct by chance; knowledge may be fragile."),
                ("Expected gap", "Low confidence + wrong", "Student aware of knowledge gap."),
                ("Uncertain", "Medium confidence", "Ambiguous calibration signal."),
            ],
            col_widths=[3.0 * cm, 4.5 * cm, 8.0 * cm],
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        para(
            "In timed exam mode, confidence is inferred from answer time relative to the per-question "
            "time limit (default 30 seconds, configurable in exam setup). Manual confidence ratings "
            "apply in practice review mode but student setup currently defaults to timed exam.",
            BODY,
        )
    )
    story.append(PageBreak())

    # Part 4: Navigation map
    story.extend(section_heading("Part 4 — Sidebar Navigation by Role"))
    story.append(
        make_table(
            ["Role", "Primary Navigation Items"],
            [
                (
                    "Student",
                    "Dashboard | Start Review | Session History | Mistakes | Weak Areas | Topic Progress | Profile",
                ),
                (
                    "Faculty",
                    "Overview | My Courses (Analytics, Masterlist, Exam Setup, Heatmap, Topics, Question Bank, Feedback)",
                ),
                (
                    "Chairperson",
                    "Programs | Assignments | Faculty Logs | Student Logs | Cross-Program | Course Audit",
                ),
                (
                    "Campus Admin",
                    "Campus Dashboard | Users | Sections | Academic Calendar",
                ),
            ],
            col_widths=[3.0 * cm, 14.5 * cm],
        )
    )
    story.append(Spacer(1, 10))

    story.extend(subsection_heading("4.1 Eligibility Gate Logic (Student Review)"))
    story.extend(
        bullet_list(
            "Profile must have section and year level set.",
            "Year level must match assigned section.",
            "A current academic term must be active (campus admin responsibility).",
            "At least one teaching assignment for the student's section must have exam_setup.is_enabled=True.",
            "Approved, active questions must exist for selected topic and difficulty.",
        )
    )

    story.append(PageBreak())

    # Part 5: Panel Q&A
    story.extend(section_heading("Part 5 — Panelist Questions and Answers"))

    categories = PANEL_QA

    for title, pairs in categories:
        story.append(para(title, H2))
        for question, answer in pairs:
            story.extend(qa_pair(question, answer))
        story.append(Spacer(1, 6))

    story.append(PageBreak())

    # Appendix: Quick reference
    story.extend(section_heading("Appendix — Function-to-Location Quick Reference"))
    story.append(
        make_table(
            ["I want to…", "Go to…"],
            [
                ("Register", "/accounts/signup/"),
                ("Log in", "/accounts/login/"),
                ("Update my profile", "/profile/"),
                ("Approve a faculty account", "/campus/users/"),
                ("Set the current semester", "/campus/academic-calendar/"),
                ("Create student sections", "/campus/sections/"),
                ("Assign faculty to a class", "/chairperson/assignments/create/"),
                ("Enable exams for a course", "/professor/courses/<pk>/exam-setup/"),
                ("Add questions", "/professor/courses/<pk>/questions/"),
                ("Approve questions", "Chairperson question review (intended URL)"),
                ("Start a review session", "/student/review/setup/"),
                ("See my calibration results", "/student/review/<pk>/summary/"),
                ("See my mistakes", "/student/mistakes/"),
                ("See class performance", "/professor/courses/<pk>/"),
                ("Export intervention list", "/professor/courses/<pk>/interventions/export/"),
                ("See department analytics", "/chairperson/dashboard/"),
                ("Export thesis research data", "/chairperson/research/export/ (intended URL)"),
            ],
            col_widths=[6.5 * cm, 11.0 * cm],
        )
    )

    return story


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="ExamiQ+ User Flows and Panel Q&A",
        author="ExamiQ Thesis",
    )
    doc.build(build_story())
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()
