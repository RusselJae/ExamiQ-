#!/usr/bin/env python3
"""Generate docs/functional-testing.pdf from structured appendix content."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
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

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "functional-testing.pdf"

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, spaceAfter=12, alignment=TA_CENTER)
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=13, spaceBefore=14, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=6)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=12)
CELL = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7, leading=9)
CELL_HDR = ParagraphStyle("CellHdr", parent=styles["Normal"], fontSize=7, leading=9, textColor=colors.white)
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10)


def p(text, style=CELL):
    return Paragraph(text.replace("\n", "<br/>"), style)


def make_table(headers, rows, col_widths=None):
    data = [[p(h, CELL_HDR) for h in headers]]
    for row in rows:
        data.append([p(str(c), CELL) for c in row])
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def su_table(rows):
    return make_table(["Function", "S/U", "Note"], rows, col_widths=[5.5 * cm, 1.5 * cm, 10 * cm])


# --- Appendix B: max 5 functions per role ---
FUNCTIONAL_TESTING = {
    "B.1 Student": [
        ("Create Account", "S", "Working — sign up with program, year level, and section"),
        ("Login Account", "S", "Working — redirect to /student/dashboard/"),
        ("Start Review Session", "S", "Working — setup wizard, timed delivery, session summary"),
        ("View Mistakes", "S", "Working — auto-logged wrong answers; list and weak-area patterns"),
        ("View Dashboard", "S", "Working — performance summary, session history, topic progress"),
    ],
    "B.2 Faculty (Professor)": [
        ("Create Account", "S", "Working — creates pending account until campus approval"),
        ("Login Account", "S", "Working — redirect to /professor/courses/ after approval"),
        ("Create Question", "S", "Working — saves as pending; requires chair approval for live use"),
        ("Configure Exam Setup", "S", "Working — enables student review eligibility for section"),
        ("View Course Analytics", "S", "Working — roster, heatmap, and intervention data"),
    ],
    "B.3 Chairperson": [
        ("Create Account", "S", "Working — requires department; pending until campus approval"),
        ("Login Account", "S", "Working — redirect to /chairperson/dashboard/"),
        ("Create Teaching Assignment", "S", "Working — links faculty, section, subject, and term"),
        ("Approve Question", "U", "Service exists but review UI not wired to URLs/views"),
        ("View Programs Dashboard", "S", "Working — department program performance and cross-program analytics"),
    ],
    "B.4 Campus Administrator": [
        ("Login Account", "S", "Working — access to /campus/ or /admin/"),
        ("Approve / Reject Registration", "S", "Working — activate or reject pending faculty and chairperson accounts"),
        ("Create Faculty / Chair Account", "S", "Working — provision active approved accounts directly"),
        ("Manage Academic Calendar", "S", "Working — set current year and term for review eligibility"),
        ("Manage Program Sections", "S", "Working — create sections for student signup and assignments"),
    ],
}

# --- Appendix A: test cases ---
TEST_CASE_HEADERS = ["Action", "Activities", "System Response", "Actual Errors", "Response"]
TEST_CASE_COL_WIDTHS = [2.2 * cm, 4.5 * cm, 4.5 * cm, 3.5 * cm, 4.8 * cm]

STUDENT_CASES = [
    ("Sign In", "Enter email and password; click Sign In", "User authenticated; redirect to /student/dashboard/", "Invalid email or password", "Prompt to enter valid credentials"),
    ("Sign Up", "Enter name, email, student number, program, year level, section, phone, password", "Account created; redirect to student dashboard", "Email already registered", "Prompt for unique email"),
    ("Sign Up", "Enter weak password", "—", "Password too weak", "Prompt to use a strong password"),
    ("Sign Up", "Select full section", "—", "Section full", "Prompt: This section is full. Choose another section."),
    ("View Profile", "Update program, year level, or section at /profile/", "Profile saved", "Section mismatch", "Display validation error"),
    ("Log Out", "Click Sign Out", "Session ended; redirect to login", "No system errors", "No additional response"),
    ("Review Setup", "Select subject, topic, difficulty, duration at /student/review/setup/", "Wizard advances; preview shown", "Profile incomplete", "Display eligibility message; block session"),
    ("Start Review", "Confirm setup", "Timed session begins at /student/review/<pk>/", "No approved questions", "Display error or empty session message"),
    ("Submit Answer", "Answer within time limit", "Answer graded; confidence inferred; next question loaded", "Time expired", "Mark unanswered; advance per timer"),
    ("Session Summary", "Complete session; view summary", "Accuracy and calibration insights displayed", "No system errors", "Summary shown for partial sessions"),
    ("View Feedback", "Open feedback from session summary", "Step-by-step explanation displayed", "Feedback not generated", "Prompt to generate feedback"),
    ("View Mistakes", "Navigate to /student/mistakes/", "Mistake records listed", "No mistakes yet", "Show empty state"),
    ("View Dashboard", "Navigate to /student/dashboard/", "Performance summary displayed", "No session history", "Show zero-state metrics"),
]

FACULTY_CASES = [
    ("Sign Up", "Enter email, employee ID, phone, password; select Faculty", "Pending inactive account created", "Employee ID missing", "Prompt: Employee ID is required."),
    ("Sign In", "Enter credentials before approval", "—", "Account pending", "Redirect with pending banner"),
    ("Sign In", "Enter credentials after approval", "Redirect to /professor/courses/", "Invalid credentials", "Prompt valid credentials"),
    ("Log Out", "Click Sign Out", "Session ended", "No system errors", "No additional response"),
    ("Create Question", "Enter stem, choices, answer at questions/create/", "Question saved as pending", "Missing fields", "Prompt complete required fields"),
    ("Edit Question", "Edit approved question", "Updated; status returns to pending", "Not owned", "Return 404"),
    ("Exam Setup", "Enable setup, set topics, timer at exam-setup/", "Students become eligible", "Missing config", "Display validation errors"),
    ("Edit Feedback", "Edit explanation steps at feedback/", "Steps saved", "Question not in course", "Return 404"),
    ("Course Analytics", "Open /professor/courses/<pk>/", "Performance summary displayed", "Course not owned", "Return 404"),
    ("Roster", "Open roster; drill into student", "Student performance shown", "Student not in roster", "Return 404"),
]

CHAIRPERSON_CASES = [
    ("Sign Up", "Enter email, employee ID, department, password", "Pending account created", "Department missing", "Prompt: Department is required for chairpersons."),
    ("Sign In", "Enter credentials after approval", "Redirect to /chairperson/dashboard/", "Invalid credentials", "Prompt valid credentials"),
    ("Log Out", "Click Sign Out", "Session ended", "No system errors", "No additional response"),
    ("Review Questions", "Approve or reject pending question", "Status updated to approved/rejected", "Outside department", "Access denied or 404"),
    ("Review Questions", "Access review UI", "—", "UI not wired", "Known gap: use Django admin workaround"),
    ("Create Assignment", "Select faculty, section, subject, term", "Assignment and course created", "Missing fields", "Display validation error"),
    ("Programs Dashboard", "Open /chairperson/dashboard/", "Program performance displayed", "No data", "Show zero-state dashboard"),
    ("Cross-Program Analytics", "Open /chairperson/analytics/by-program/", "Analytics by degree program", "No student data", "Show empty analytics"),
    ("Course Audit", "Open /chairperson/courses/", "Course participation listed", "No courses", "Show empty list"),
]

CAMPUS_CASES = [
    ("Sign In", "Enter admin credentials", "Redirect to /campus/ or /admin/", "Invalid credentials", "Prompt valid credentials"),
    ("Approve Registration", "Approve pending user at /campus/users/", "User activated and approved", "Not pending", "Error: Only pending registrations can be approved."),
    ("Reject Registration", "Reject pending user", "User rejected and inactive", "Not pending", "Error on invalid state"),
    ("Create Professor", "Enter email, name, employee ID, password", "Active professor created", "Duplicate email", "Prompt unique email"),
    ("Toggle Active", "Toggle approved user active status", "is_active flipped", "Own account", "Error: cannot deactivate own account"),
    ("Academic Calendar", "Set current year and term", "Current term saved", "Invalid dates", "Display validation error"),
    ("Program Sections", "Create section with program and capacity", "Section available for signup", "Duplicate code", "Display validation error"),
    ("Log Out", "Click Sign Out", "Session ended", "No system errors", "No additional response"),
]

RBAC_MATRIX = [
    ("1", "Anonymous", "/student/dashboard/", "302 → login"),
    ("2", "Student", "/student/dashboard/", "200"),
    ("3", "Student", "/professor/courses/", "403"),
    ("4", "Faculty", "/professor/courses/", "200"),
    ("5", "Faculty", "/student/review/setup/", "403"),
    ("6", "Chairperson", "/chairperson/dashboard/", "200"),
    ("7", "Chairperson", "/campus/", "403"),
    ("8", "Campus Admin", "/campus/", "200"),
    ("9", "Campus Admin", "/student/dashboard/", "403"),
    ("10", "Pending Faculty", "/accounts/login/ (valid password)", "302 → ?registered=pending"),
]


def build_story():
    story = []

    story.append(Paragraph("EXAMIQ", TITLE))
    story.append(Paragraph("Functional Testing and Test Cases", TITLE))
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        Paragraph(
            "A Self-Regulated Mathematics Exam Review System for College Students "
            "with Dynamic Feedback, Mistake Tracking, and Confidence-Based Test Flow",
            SMALL,
        )
    )
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("1. Scope", H1))
    story.append(
        Paragraph(
            "This document defines functional test cases (Appendix A) and a functional testing "
            "checklist (Appendix B) for ExamiQ. Four user roles are covered: Student, Faculty, "
            "Chairperson, and Campus Administrator. Functional testing is limited to five primary "
            "functions per role. S = Satisfactory; U = Unsatisfactory.",
            BODY,
        )
    )
    story.append(Spacer(1, 0.3 * cm))
    story.append(
        make_table(
            ["Role", "Post-login home"],
            [
                ("Student", "/student/dashboard/"),
                ("Faculty", "/professor/courses/"),
                ("Chairperson", "/chairperson/dashboard/"),
                ("Campus Administrator", "/admin/ or /campus/"),
            ],
            col_widths=[5 * cm, 12 * cm],
        )
    )

    # Appendix B first (like thesis appendix order can vary; user asked for both)
    story.append(PageBreak())
    story.append(Paragraph("Appendix B — Functional Testing Checklist", H1))
    story.append(Paragraph("Function | Satisfactory (S) / Unsatisfactory (U) | Note", SMALL))
    story.append(Spacer(1, 0.2 * cm))

    for section, rows in FUNCTIONAL_TESTING.items():
        story.append(Paragraph(section, H2))
        story.append(su_table(rows))
        story.append(Spacer(1, 0.3 * cm))

    # Appendix A
    story.append(PageBreak())
    story.append(Paragraph("Appendix A — Test Cases", H1))
    story.append(Paragraph("Action | Activities | System Response | Actual Errors | Response", SMALL))
    story.append(Spacer(1, 0.2 * cm))

    for title, cases in [
        ("A.1 Student", STUDENT_CASES),
        ("A.2 Faculty (Professor)", FACULTY_CASES),
        ("A.3 Chairperson", CHAIRPERSON_CASES),
        ("A.4 Campus Administrator", CAMPUS_CASES),
    ]:
        story.append(Paragraph(title, H2))
        story.append(make_table(TEST_CASE_HEADERS, cases, TEST_CASE_COL_WIDTHS))
        story.append(Spacer(1, 0.3 * cm))
        story.append(PageBreak())

    # Appendix C
    story.append(Paragraph("Appendix C — Cross-Role Access Matrix", H1))
    story.append(
        make_table(
            ["#", "Actor", "URL / Resource", "Expected result"],
            RBAC_MATRIX,
            col_widths=[1 * cm, 3.5 * cm, 6 * cm, 6.5 * cm],
        )
    )
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph("Known Limitations", H2))
    story.append(
        Paragraph(
            "Chairperson Question Review UI is marked U — templates exist but views/URLs are not wired. "
            "Questions may remain pending unless approved via Django admin.",
            BODY,
        )
    )

    return story


def main():
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="ExamiQ Functional Testing",
        author="ExamiQ",
    )
    doc.build(build_story())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
