from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.analytics.models import ErrorType, MistakeRecord
from apps.analytics.services import log_mistake
from apps.questions.models import ExplanationStep, Question, QuestionChoice, Subject, Topic, YearLevel
from apps.reviews.models import Answer, ReviewSession, ReviewWindow
from apps.reviews.services import complete_session, start_review_session
from apps.users.models import AcademicTerm, AcademicYear, Course, Department, Program, ProgramSection, User

# BSEd Mathematics curriculum: (year_order, semester 1/2/3, code, title)
# Semester 3 = Midyear. Empty year/term blocks are omitted.
BSED_MATH_CURRICULUM: list[tuple[int, int, str, str]] = [
    # 1st Semester
    (1, 1, "GNED 03", "Mathematics in the Modern World"),
    (2, 1, "BSEM 23", "Trigonometry"),
    (2, 1, "BSEM 24", "Plane and Solid Geometry"),
    (2, 1, "BSEM 25", "Logic and Set Theory"),
    (2, 1, "BSEM 26", "Elementary Statistics and Probability"),
    (3, 1, "BSEM 35", "Problem-Solving, Mathematical Investigation and Modelling"),
    (3, 1, "BSEM 27", "Calculus with Analytic Geometry"),
    (3, 1, "BSEM 38", "Research in Mathematics"),
    (3, 1, "BSEM 32", "Number Theory"),
    # 2nd Semester
    (2, 2, "BSEM 30", "Modern Geometry"),
    (2, 2, "BSEM 33", "Linear Algebra"),
    (2, 2, "BSEM 36", "Principles and Method of Teaching Mathematics"),
    (2, 2, "BSEM 34", "Advanced Statistics"),
    (3, 2, "BSEM 40", "Assessment and Evaluation in Mathematics"),
    (3, 2, "BSEM 31", "Mathematics of Investment"),
    (3, 2, "BSEM 37", "Abstract Algebra"),
    (3, 2, "BSEM 28", "Calculus 2"),
    # Midyear
    (1, 3, "BSEM 21", "History of Mathematics"),
    (1, 3, "BSEM 22", "College and Advanced Algebra"),
]

BSED_STUDENTS: list[tuple[str, str, str]] = [
    ("maria.santos.bsed01@gmail.com", "Maria", "Santos"),
    ("jose.reyes.bsed02@gmail.com", "Jose", "Reyes"),
    ("ana.cruz.bsed03@gmail.com", "Ana", "Cruz"),
    ("miguel.garcia.bsed04@gmail.com", "Miguel", "Garcia"),
    ("sofia.ramos.bsed05@gmail.com", "Sofia", "Ramos"),
    ("carlo.mendoza.bsed06@gmail.com", "Carlo", "Mendoza"),
    ("isabella.torres.bsed07@gmail.com", "Isabella", "Torres"),
    ("rafael.lopez.bsed08@gmail.com", "Rafael", "Lopez"),
    ("camille.villanueva.bsed09@gmail.com", "Camille", "Villanueva"),
    ("andre.fernandez.bsed10@gmail.com", "Andre", "Fernandez"),
]

FACULTY_EMAIL = "prof_educmath@examiq.edu"


class Command(BaseCommand):
    help = "Seed EXAMIQ with BSEd Mathematics demo data only."

    def handle(self, *args, **options):
        self.stdout.write("Seeding EXAMIQ (BSEd Math only)...")
        self._cleanup_non_bsed_demo_data()

        year_levels = {}
        for order, name in enumerate(["1st Year", "2nd Year", "3rd Year", "4th Year"], start=1):
            yl, _ = YearLevel.objects.get_or_create(order=order, defaults={"name": name})
            year_levels[order] = yl

        academic_year, _ = AcademicYear.objects.get_or_create(
            label="2025-2026",
            defaults={"is_current": True},
        )
        academic_year.is_current = True
        academic_year.save(update_fields=["is_current"])
        AcademicYear.objects.exclude(pk=academic_year.pk).update(is_current=False)

        for semester, name in (
            (AcademicTerm.Semester.FIRST, "1st Semester"),
            (AcademicTerm.Semester.SECOND, "2nd Semester"),
            (AcademicTerm.Semester.MIDYEAR, "Midyear"),
        ):
            term, _ = AcademicTerm.objects.get_or_create(
                academic_year=academic_year,
                name=name,
                defaults={
                    "semester": semester,
                    "is_current": semester == AcademicTerm.Semester.FIRST,
                },
            )
            if term.semester != semester:
                term.semester = semester
                term.save(update_fields=["semester"])
        AcademicTerm.objects.filter(academic_year=academic_year).update(is_current=False)
        AcademicTerm.objects.filter(
            academic_year=academic_year,
            name="1st Semester",
        ).update(is_current=True)

        edu, _ = Department.objects.get_or_create(name="College of Education")
        program, _ = Program.objects.get_or_create(
            slug=User.HomeDegreeProgram.BSED_MATH,
            defaults={
                "name": "BSEd Mathematics",
                "managing_department": edu,
            },
        )
        if program.managing_department_id != edu.pk:
            program.managing_department = edu
            program.save(update_fields=["managing_department"])

        for order, yl in year_levels.items():
            for label in ("1M", "2M"):
                ProgramSection.objects.get_or_create(
                    program=program,
                    year_level=yl,
                    label=label,
                    academic_year=academic_year,
                    defaults={"max_students": 40, "is_active": True},
                )
            # Retire legacy letter labels so UI shows BSE Y-#M only.
            ProgramSection.objects.filter(
                program=program,
                year_level=yl,
                academic_year=academic_year,
                label="A",
            ).update(is_active=False)

        professor, _ = User.objects.get_or_create(
            email=FACULTY_EMAIL,
            defaults={
                "first_name": "Educ",
                "last_name": "Math",
                "role": User.Role.PROFESSOR,
                "department": edu,
            },
        )
        professor.first_name = "Educ"
        professor.last_name = "Math"
        professor.role = User.Role.PROFESSOR
        professor.department = edu
        professor.set_password("demo1234")
        professor.save()

        primary_course = None
        for year_order, semester, code, title in BSED_MATH_CURRICULUM:
            term_label = {1: "1st Sem", 2: "2nd Sem", 3: "Midyear"}[semester]
            section_label = f"BSE {year_order}-1M"
            course = self._ensure_bsed_course(
                program=program,
                code=code,
                term=term_label,
                academic_year="2025-2026",
                section_label=section_label,
                name=title,
                professor=professor,
            )
            if code == "BSEM 22" and term_label == "Midyear":
                primary_course = course
            # Drop stale duplicates left from older section labels
            Course.objects.filter(
                code=code,
                program=program,
                term=term_label,
                academic_year="2025-2026",
            ).exclude(section=section_label).delete()
        if primary_course is None:
            primary_course = Course.objects.filter(
                program=program, code="BSEM 22", professor=professor
            ).first()

        students = []
        for index, (email, first_name, last_name) in enumerate(BSED_STUDENTS, start=1):
            year_level = year_levels.get(2 if index <= 5 else 1)
            section_label = "1M" if index % 2 else "2M"
            section = ProgramSection.objects.filter(
                program=program,
                year_level=year_level,
                label=section_label,
                academic_year=academic_year,
                is_active=True,
            ).first()
            student, _ = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": User.Role.STUDENT,
                    "home_degree_program": User.HomeDegreeProgram.BSED_MATH,
                    "department": edu,
                    "year_level": year_level,
                    "section": section,
                    "student_number": f"2025{index:05d}",
                },
            )
            student.first_name = first_name
            student.last_name = last_name
            student.role = User.Role.STUDENT
            student.home_degree_program = User.HomeDegreeProgram.BSED_MATH
            student.department = edu
            student.year_level = year_level
            student.section = section
            student.set_password("demo1234")
            student.save()
            students.append(student)

        topics = self._seed_curriculum(program, year_levels)
        self._seed_error_types()
        self._seed_questions(topics, professor)
        self._seed_review_window(primary_course, professor, topics)
        self._ensure_admin_user()
        self._seed_demo_sessions(primary_course, topics, students)

        self.stdout.write(self.style.SUCCESS("Seed complete!"))
        self._print_credentials(students)

    def _ensure_bsed_course(
        self,
        *,
        program,
        code,
        term,
        academic_year,
        section_label,
        name,
        professor,
    ):
        """Get/create a course with BSE section label; migrate legacy Sec A rows."""
        base = {
            "code": code,
            "program": program,
            "term": term,
            "academic_year": academic_year,
        }
        course = Course.objects.filter(**base, section=section_label).first()
        legacy = Course.objects.filter(**base, section="A").first()
        if course and legacy and legacy.pk != course.pk:
            legacy.delete()
        elif legacy and not course:
            legacy.section = section_label
            legacy.name = name
            legacy.professor = professor
            legacy.save(update_fields=["section", "name", "professor"])
            course = legacy
        elif not course:
            course = Course.objects.create(
                **base,
                section=section_label,
                name=name,
                professor=professor,
            )
        else:
            changed = []
            if course.professor_id != professor.pk:
                course.professor = professor
                changed.append("professor")
            if course.name != name:
                course.name = name
                changed.append("name")
            if changed:
                course.save(update_fields=changed)
        return course

    def _cleanup_non_bsed_demo_data(self):
        """Remove demo accounts/courses outside BSEd Math so seed stays focused."""
        keep_emails = {FACULTY_EMAIL, "admin@examiq.edu"} | {email for email, _, _ in BSED_STUDENTS}
        User.objects.filter(
            role__in=[
                User.Role.STUDENT,
                User.Role.PROFESSOR,
                User.Role.CHAIRPERSON,
            ]
        ).exclude(email__in=keep_emails).delete()

        bsed = Program.objects.filter(slug=User.HomeDegreeProgram.BSED_MATH).first()
        if bsed:
            Course.objects.exclude(program=bsed).delete()
            # Drop non-curriculum leftover offerings from older seeds
            curriculum_codes = {code for _, _, code, _ in BSED_MATH_CURRICULUM} | {"BSEM 22"}
            Course.objects.filter(program=bsed).exclude(code__in=curriculum_codes).delete()
            Program.objects.exclude(pk=bsed.pk).delete()
        Department.objects.exclude(name="College of Education").filter(
            managed_programs__isnull=True,
            users__isnull=True,
        ).delete()

    def _seed_curriculum(self, program, year_levels):
        topics = {}
        Subject.objects.filter(program=program, code="GEN-BSED_MATH").delete()
        for year_order, semester, code, title in BSED_MATH_CURRICULUM:
            subject, _ = Subject.objects.update_or_create(
                program=program,
                code=code,
                defaults={
                    "year_level": year_levels[year_order],
                    "semester": semester,
                    "name": title,
                },
            )
            topic, _ = Topic.objects.get_or_create(subject=subject, name=title)
            topics[f"bsed_math:{code}"] = topic
            topics[f"bsed_math:{title}"] = topic
        return topics

    def _seed_error_types(self):
        for slug, label, category in [
            ("sign_error", "Sign error", "procedural"),
            ("arithmetic", "Arithmetic error", "computational"),
            ("concept_gap", "Concept gap", "conceptual"),
        ]:
            ErrorType.objects.get_or_create(
                slug=slug,
                defaults={"label": label, "category": category},
            )

    def _seed_questions(self, topics, professor):
        # Remove legacy duplicated demo stems from earlier seeds
        Question.objects.filter(stem__istartswith="[Demo").delete()

        bank = [
            (
                "BSEM 22",
                Question.Difficulty.EASY,
                "Solve for x: 2x + 5 = 13",
                [
                    ("A", "x = 3", False),
                    ("B", "x = 4", True),
                    ("C", "x = 5", False),
                    ("D", "x = 6", False),
                ],
                "Linear equations",
                ["Subtract 5 from both sides.", "Divide both sides by 2."],
            ),
            (
                "BSEM 22",
                Question.Difficulty.EASY,
                "Simplify: (x^2)(x^3)",
                [
                    ("A", "x^5", True),
                    ("B", "x^6", False),
                    ("C", "x", False),
                    ("D", "2x^5", False),
                ],
                "Exponent rules",
                ["When multiplying same bases, add exponents: 2 + 3 = 5."],
            ),
            (
                "BSEM 22",
                Question.Difficulty.MEDIUM,
                "Factor: x^2 - 9",
                [
                    ("A", "(x - 3)(x + 3)", True),
                    ("B", "(x - 9)(x + 1)", False),
                    ("C", "(x - 3)^2", False),
                    ("D", "x(x - 9)", False),
                ],
                "Difference of squares",
                ["a^2 - b^2 = (a - b)(a + b) with a = x and b = 3."],
            ),
            (
                "BSEM 23",
                Question.Difficulty.EASY,
                "In a right triangle, sin θ equals opposite over:",
                [
                    ("A", "Adjacent", False),
                    ("B", "Hypotenuse", True),
                    ("C", "Opposite", False),
                    ("D", "Complement", False),
                ],
                "SOH-CAH-TOA",
                ["sin θ = opposite / hypotenuse."],
            ),
            (
                "BSEM 33",
                Question.Difficulty.MEDIUM,
                "The determinant of the 2x2 identity matrix is:",
                [
                    ("A", "0", False),
                    ("B", "1", True),
                    ("C", "2", False),
                    ("D", "-1", False),
                ],
                "Determinants",
                ["det(I) = 1 for any identity matrix."],
            ),
        ]
        for code, difficulty, stem, choices, concept_tag, steps in bank:
            topic = topics.get(f"bsed_math:{code}")
            if not topic or Question.objects.filter(stem=stem).exists():
                continue
            question = Question.objects.create(
                topic=topic,
                difficulty=difficulty,
                question_type=Question.QuestionType.MCQ,
                stem=stem,
                concept_tag=concept_tag,
                is_active=True,
                status=Question.Status.APPROVED,
                proposed_by=professor,
            )
            for label, text, is_correct in choices:
                QuestionChoice.objects.create(
                    question=question,
                    label=label,
                    text=text,
                    is_correct=is_correct,
                )
            for order, content in enumerate(steps, start=1):
                ExplanationStep.objects.create(
                    question=question,
                    order=order,
                    content=content,
                    professor_note="",
                )

    def _seed_review_window(self, course, professor, topics):
        topic = topics.get("bsed_math:BSEM 22")
        if not topic:
            return
        now = timezone.now()
        window, created = ReviewWindow.objects.get_or_create(
            course=course,
            title="Algebra Midyear Review",
            defaults={
                "created_by": professor,
                "exam_type": ReviewWindow.ExamType.MIDTERM,
                "opens_at": now - timedelta(days=1),
                "closes_at": now + timedelta(days=14),
                "duration_minutes": 30,
                "seconds_per_question": 30,
                "mode": ReviewWindow.Mode.TIMED_EXAM,
                "allowed_difficulties": ["easy", "medium", "hard"],
            },
        )
        if created:
            window.topics.set([topic])

    def _ensure_admin_user(self):
        admin_user, created = User.objects.get_or_create(
            email="admin@examiq.edu",
            defaults={
                "first_name": "Admin",
                "last_name": "User",
                "role": User.Role.CAMPUS_ADMIN,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin_user.role = User.Role.CAMPUS_ADMIN
        admin_user.is_staff = True
        admin_user.is_superuser = True
        if created or not admin_user.has_usable_password():
            admin_user.set_password("admin1234")
        admin_user.save()

    def _seed_demo_sessions(self, course, topics, students):
        topic = topics.get("bsed_math:BSEM 22")
        if not topic or len(students) < 3:
            return

        # Ana Cruz — mixed performance + student concerns for faculty Feedback demo
        ana = students[2]
        self._create_demo_session(
            ana,
            course,
            topic,
            Question.Difficulty.EASY,
            days_ago=3,
            answers_spec=[(4, True), (3, False), (4, False), (2, False)],
        )
        self._attach_student_concerns(ana, topic)

        # Maria Santos — stronger session
        self._create_demo_session(
            students[0],
            course,
            topic,
            Question.Difficulty.EASY,
            days_ago=5,
            answers_spec=[(5, True), (4, True), (3, False), (4, True)],
        )

        # Jose Reyes — weaker session
        self._create_demo_session(
            students[1],
            course,
            topic,
            Question.Difficulty.EASY,
            days_ago=7,
            answers_spec=[(2, False), (3, False), (2, False), (4, True)],
        )
        self._attach_student_concerns(students[1], topic)

    def _attach_student_concerns(self, student, topic):
        records = (
            MistakeRecord.objects.filter(student=student, topic=topic)
            .filter(Q(student_note="") | Q(student_note__isnull=True))
            .order_by("-occurred_at")[:2]
        )
        notes = [
            "I got stuck after isolating x. Can you check if my steps make sense?",
            "I confused the exponent rule with addition of exponents incorrectly.",
        ]
        for index, record in enumerate(records):
            record.student_note = notes[index % len(notes)]
            record.ai_feedback = (
                record.ai_feedback
                or "Review the related concept and rework the problem step by step."
            )
            record.save(update_fields=["student_note", "ai_feedback"])

    def _create_demo_session(self, student, course, topic, difficulty, days_ago, answers_spec):
        started = timezone.now() - timedelta(days=days_ago)
        if ReviewSession.objects.filter(
            student=student,
            topic=topic,
            difficulty=difficulty,
            status=ReviewSession.Status.COMPLETED,
            started_at__date=started.date(),
        ).exists():
            return

        questions = list(
            Question.objects.filter(
                topic=topic,
                difficulty=difficulty,
                status=Question.Status.APPROVED,
                is_active=True,
            )[: len(answers_spec)]
        )
        if not questions:
            return

        session = start_review_session(
            student=student,
            topic=topic,
            difficulty=difficulty,
            duration_minutes=15,
            course=course,
            mode=ReviewSession.Mode.TIMED_EXAM,
            seconds_per_question=30,
        )
        ReviewSession.objects.filter(pk=session.pk).update(started_at=started)
        session.refresh_from_db()

        for index, (confidence, is_correct) in enumerate(answers_spec[: len(questions)]):
            question = questions[index]
            choice = (
                question.choices.filter(is_correct=True).first()
                if is_correct
                else question.choices.filter(is_correct=False).first()
            )
            answer = Answer.objects.create(
                session=session,
                question=question,
                selected_choice=choice,
                confidence=confidence,
                is_correct=is_correct,
                time_spent_seconds=30,
            )
            if not is_correct:
                log_mistake(student=student, question=question, answer=answer)

        complete_session(session)
        ReviewSession.objects.filter(pk=session.pk).update(
            ended_at=started + timedelta(minutes=12)
        )

    def _print_credentials(self, students):
        self.stdout.write("\nDemo credentials (password: demo1234):")
        self.stdout.write(f"  Faculty:  {FACULTY_EMAIL}")
        self.stdout.write("  Students:")
        for student in students:
            self.stdout.write(f"    {student.email} ({student.get_full_name()})")
        self.stdout.write("\nAdmin: admin@examiq.edu / admin1234")
