from decimal import Decimal

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.models import ErrorType
from apps.analytics.services import log_mistake
from apps.questions.models import ExplanationStep, Question, QuestionChoice, Subject, Topic, YearLevel
from apps.reviews.models import Answer, ReviewSession, ReviewWindow
from apps.reviews.services import complete_session, start_review_session, submit_answer
from apps.users.constants import HOME_PROGRAM_DEPARTMENT_NAMES, PROGRAM_DEFINITIONS
from apps.users.models import Course, Department, Program, User

# CS official math-related curriculum (year order, semester, code, name, topics).
CS_CURRICULUM: list[tuple[int, int, str, str, list[str]]] = [
    (1, 1, "COSC 50", "Discrete Structures I", ["Sets", "Logic", "Proof techniques"]),
    (1, 2, "GNED 03", "Mathematics in the Modern World", ["Patterns", "Finance math"]),
    (2, 1, "MATH 1", "Analytic Geometry", ["Lines", "Conics"]),
    (2, 1, "COSC 55", "Discrete Structures II", ["Graphs", "Counting"]),
    (2, 2, "MATH 2", "Calculus", ["Limits", "Derivatives", "Integrals"]),
    (3, 1, "MATH 3", "Linear Algebra", ["Matrices", "Vector spaces"]),
    (3, 2, "MATH 4", "Experimental Statistics", ["Descriptive stats", "Hypothesis testing"]),
    (3, 2, "COSC 90", "Design and Analysis of Algorithm", ["Big-O", "Sorting"]),
    (4, 1, "COSC 100", "Automata Theory", ["DFA", "NFA", "Regular languages"]),
    (4, 2, "COSC 110", "Numerical and Symbolic Computation", ["Numerical methods", "Symbolic math"]),
]

# Per-program math topics for non-CS programs (flat under placeholder subject).
PROGRAM_MATH_TOPICS: dict[str, list[str]] = {
    "it": ["Applied Mathematics", "Statistics for IT", "Binary Systems"],
    "bsed_math": ["Algebra for Teachers", "Geometry and Measurement", "Statistics in Education"],
    "psychology": ["Research Statistics", "Data Interpretation", "Probability in Psychology"],
    "marketing": ["Business Mathematics", "Percentages and Margins", "Financial Ratios"],
    "hr": ["Payroll Mathematics", "Labor Metrics", "Budget Calculations"],
    "hospitality": ["Cost and Profit Math", "Unit Conversions", "Revenue Management"],
    "criminology": ["Crime Statistics", "Data Analysis", "Probability in Forensics"],
}


class Command(BaseCommand):
    help = "Seed EXAMIQ with demo data for thesis presentation."

    def handle(self, *args, **options):
        self.stdout.write("Seeding EXAMIQ...")

        year_levels = {}
        for order, name in enumerate(["1st Year", "2nd Year", "3rd Year", "4th Year"], start=1):
            yl, _ = YearLevel.objects.get_or_create(order=order, defaults={"name": name})
            year_levels[order] = yl

        departments = {}
        for name in set(HOME_PROGRAM_DEPARTMENT_NAMES.values()):
            departments[name], _ = Department.objects.get_or_create(name=name)

        programs = {}
        for slug, name, dept_name in PROGRAM_DEFINITIONS:
            dept = departments[dept_name]
            prog, _ = Program.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "managing_department": dept},
            )
            programs[slug] = prog

        chairs = {}
        for dept_name, dept in departments.items():
            slug = dept_name.lower().replace(" ", "")[:12]
            chair, _ = User.objects.get_or_create(
                email=f"chair.{slug}@examiq.edu",
                defaults={
                    "first_name": "Chair",
                    "last_name": dept_name.split()[0],
                    "role": User.Role.CHAIRPERSON,
                    "department": dept,
                    "is_staff": True,
                },
            )
            chair.set_password("demo1234")
            chair.save()
            chairs[dept_name] = chair

        edu = departments["College of Education"]
        cs_dept = departments["Department of Computer Studies"]

        prof1, _ = User.objects.get_or_create(
            email="prof.calculus@examiq.edu",
            defaults={
                "first_name": "Juan",
                "last_name": "Reyes",
                "role": User.Role.PROFESSOR,
                "department": edu,
            },
        )
        prof1.set_password("demo1234")
        prof1.save()

        prof2, _ = User.objects.get_or_create(
            email="prof.algebra@examiq.edu",
            defaults={
                "first_name": "Ana",
                "last_name": "Cruz",
                "role": User.Role.PROFESSOR,
                "department": cs_dept,
            },
        )
        prof2.set_password("demo1234")
        prof2.save()

        course_specs = [
            ("MATH101-CS", "Mathematics for CS", "cs", prof2),
            ("MATH101-IT", "Mathematics for IT", "it", prof2),
            ("MATH101-BSED", "Teaching Mathematics", "bsed_math", prof1),
            ("MATH101-PSY", "Statistics for Psychology", "psychology", prof1),
            ("MATH101-MKT", "Business Math for Marketing", "marketing", prof1),
            ("MATH101-HR", "Quantitative HR Methods", "hr", prof1),
            ("MATH101-HM", "Hospitality Mathematics", "hospitality", prof1),
            ("MATH101-CRIM", "Quantitative Criminology", "criminology", prof1),
        ]
        courses = {}
        for code, name, prog_slug, professor in course_specs:
            course, _ = Course.objects.get_or_create(
                code=code,
                program=programs[prog_slug],
                term="1st Sem",
                academic_year="2026",
                section="A",
                defaults={"name": name, "professor": professor},
            )
            courses[prog_slug] = course

        home_programs = list(User.HomeDegreeProgram.choices)
        for i in range(1, 11):
            prog_value, _ = home_programs[(i - 1) % len(home_programs)]
            dept_name = HOME_PROGRAM_DEPARTMENT_NAMES.get(prog_value, "College of Education")
            year_level = year_levels.get(2) if prog_value == User.HomeDegreeProgram.CS else year_levels.get(1)
            student, _ = User.objects.get_or_create(
                email=f"student{i}@examiq.edu",
                defaults={
                    "first_name": "Student",
                    "last_name": f"{i:02d}",
                    "role": User.Role.STUDENT,
                    "home_degree_program": prog_value,
                    "department": departments.get(dept_name),
                    "year_level": year_level,
                },
            )
            student.set_password("demo1234")
            student.home_degree_program = prog_value
            student.year_level = year_level
            student.save()

        topics = self._seed_curriculum(programs, year_levels)
        self._retire_gen_placeholder_questions(programs.get("cs"))
        self._seed_questions(topics)
        self._seed_extras(courses.get("cs"), prof2, topics)
        self._seed_demo_narrative(courses, topics, programs)

        admin_user, created = User.objects.get_or_create(
            email="admin@examiq.edu",
            defaults={
                "first_name": "Admin",
                "last_name": "User",
                "role": User.Role.CHAIRPERSON,
                "department": edu,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created or not admin_user.has_usable_password():
            admin_user.set_password("admin1234")
            admin_user.save()

        self.stdout.write(self.style.SUCCESS("Seed complete!"))
        self._print_credentials(chairs)

    def _seed_curriculum(self, programs, year_levels):
        topics = {}

        cs_program = programs["cs"]
        for year_order, semester, code, name, topic_names in CS_CURRICULUM:
            subject, _ = Subject.objects.update_or_create(
                program=cs_program,
                code=code,
                defaults={
                    "year_level": year_levels[year_order],
                    "semester": semester,
                    "name": name,
                },
            )
            for topic_name in topic_names:
                topic, _ = Topic.objects.get_or_create(subject=subject, name=topic_name)
                topics[f"cs:{code}:{topic_name}"] = topic
                topics[f"cs:{topic_name}"] = topic

        for prog_slug, topic_names in PROGRAM_MATH_TOPICS.items():
            program = programs[prog_slug]
            subject, _ = Subject.objects.get_or_create(
                program=program,
                code=f"GEN-{prog_slug.upper()}",
                defaults={
                    "year_level": year_levels[1],
                    "semester": 1,
                    "name": f"General Mathematics ({program.name})",
                },
            )
            for topic_name in topic_names:
                topic, _ = Topic.objects.get_or_create(subject=subject, name=topic_name)
                topics[f"{prog_slug}:{topic_name}"] = topic

        return topics

    def _retire_gen_placeholder_questions(self, cs_program):
        """Deactivate legacy placeholder-subject questions for CS."""
        if not cs_program:
            return
        Question.objects.filter(
            topic__subject__program=cs_program,
            topic__subject__code__startswith="GEN-",
        ).update(is_active=False)

    def _create_mcq(self, topic, difficulty, stem, choices, concept_tag, steps):
        if Question.objects.filter(topic=topic, stem=stem).exists():
            return
        q = Question.objects.create(
            topic=topic,
            difficulty=difficulty,
            question_type=Question.QuestionType.MCQ,
            stem=stem,
            concept_tag=concept_tag,
            status=Question.Status.APPROVED,
        )
        for label, text, is_correct in choices:
            QuestionChoice.objects.create(
                question=q, label=label, text=text, is_correct=is_correct
            )
        for order, content in enumerate(steps, start=1):
            ExplanationStep.objects.create(question=q, order=order, content=content)

    def _seed_cs_catalog_questions(self, topics):
        """Seed approved MCQs on official CS catalog topics at all difficulty levels."""
        bank = [
            ("Sets", Question.Difficulty.EASY, "Which set is equal to $\\{1, 2, 3\\}$?",
             [("A", "$\\{3, 2, 1\\}$", True), ("B", "$\\{1, 2\\}$", False), ("C", "$\\{1, 2, 3, 4\\}$", False), ("D", "$\\emptyset$", False)],
             "Set equality", ["Order does not matter in sets."]),
            ("Sets", Question.Difficulty.EASY, "If $A = \\{1, 2\\}$ and $B = \\{2, 3\\}$, what is $A \\cup B$?",
             [("A", "$\\{1, 2, 3\\}$", True), ("B", "$\\{2\\}$", False), ("C", "$\\{1, 3\\}$", False), ("D", "$\\emptyset$", False)],
             "Set union", ["Union includes all elements from both sets."]),
            ("Sets", Question.Difficulty.MEDIUM, "How many subsets does $\\{a, b, c\\}$ have?",
             [("A", "8", True), ("B", "6", False), ("C", "3", False), ("D", "9", False)],
             "Subset counting", ["A set with $n$ elements has $2^n$ subsets."]),
            ("Sets", Question.Difficulty.MEDIUM, "If $|A| = 5$ and $|B| = 4$ and $A \\cap B = \\{x\\}$, what is $|A \\cup B|$?",
             [("A", "8", True), ("B", "9", False), ("C", "7", False), ("D", "10", False)],
             "Inclusion-exclusion", ["$|A \\cup B| = |A| + |B| - |A \\cap B|$."]),
            ("Sets", Question.Difficulty.HARD, "Which statement is true for all sets $A$?",
             [("A", "$A \\cup \\emptyset = A$", True), ("B", "$A \\cap \\emptyset = A$", False), ("C", "$A \\cup A = \\emptyset$", False), ("D", "$A \\subset \\emptyset$", False)],
             "Set identities", ["Union with the empty set leaves $A$ unchanged."]),
            ("Sets", Question.Difficulty.HARD, "If $U = \\{1,2,3,4,5\\}$ and $A = \\{2,4\\}$, what is $A^c$?",
             [("A", "$\\{1,3,5\\}$", True), ("B", "$\\{2,4\\}$", False), ("C", "$\\{1,2,3,4,5\\}$", False), ("D", "$\\emptyset$", False)],
             "Set complement", ["Complement contains elements of $U$ not in $A$."]),
            ("Logic", Question.Difficulty.EASY, "Which is a proposition?",
             [("A", "$2 + 2 = 4$", True), ("B", "Close the door.", False), ("C", "What time is it?", False), ("D", "Wow!", False)],
             "Propositions", ["A proposition has a definite truth value."]),
            ("Logic", Question.Difficulty.EASY, "What is the negation of \"It is raining\"?",
             [("A", "It is not raining", True), ("B", "It is sunny", False), ("C", "Maybe it is raining", False), ("D", "It is raining hard", False)],
             "Negation", ["Negation reverses truth value."]),
            ("Logic", Question.Difficulty.MEDIUM, "Which is logically equivalent to $p \\to q$?",
             [("A", "$\\neg p \\lor q$", True), ("B", "$p \\land q$", False), ("C", "$p \\lor q$", False), ("D", "$\\neg p \\land q$", False)],
             "Material implication", ["Implication equals disjunction with negated antecedent."]),
            ("Logic", Question.Difficulty.MEDIUM, "What is the truth value of $p \\to q$ when $p$ is false?",
             [("A", "True", True), ("B", "False", False), ("C", "Undefined", False), ("D", "Depends on $q$ only", False)],
             "Implication truth table", ["False antecedent makes implication vacuously true."]),
            ("Logic", Question.Difficulty.HARD, "Which is a tautology?",
             [("A", "$p \\lor \\neg p$", True), ("B", "$p \\land \\neg p$", False), ("C", "$p \\to p$", False), ("D", "$\\neg(p \\lor q)$", False)],
             "Tautologies", ["$p \\lor \\neg p$ is always true."],),
            ("Logic", Question.Difficulty.HARD, "Which is equivalent to $\\neg(p \\land q)$?",
             [("A", "$\\neg p \\lor \\neg q$", True), ("B", "$\\neg p \\land \\neg q$", False), ("C", "$p \\lor q$", False), ("D", "$\\neg p \\lor q$", False)],
             "De Morgan's laws", ["De Morgan: negation distributes over conjunction as disjunction."]),
            ("Derivatives", Question.Difficulty.EASY, "What is the derivative of $f(x) = 5x^3$?",
             [("A", "$15x^2$", True), ("B", "$5x^2$", False), ("C", "$15x^4$", False), ("D", "$3x^2$", False)],
             "Power rule", ["Apply $\\frac{d}{dx}(ax^n) = nax^{n-1}$."]),
            ("Derivatives", Question.Difficulty.EASY, "What is the derivative of $f(x) = 7$?",
             [("A", "$0$", True), ("B", "$7$", False), ("C", "$7x$", False), ("D", "$1$", False)],
             "Constant rule", ["Derivative of a constant is zero."]),
            ("Derivatives", Question.Difficulty.MEDIUM, "What is the derivative of $f(x) = x^2 \\sin x$?",
             [("A", "$2x\\sin x + x^2\\cos x$", True), ("B", "$2x\\cos x$", False), ("C", "$x^2\\cos x$", False), ("D", "$\\sin x + x\\cos x$", False)],
             "Product rule", ["$(uv)' = u'v + uv'$."]),
            ("Derivatives", Question.Difficulty.MEDIUM, "What is the derivative of $f(x) = \\frac{x}{x+1}$?",
             [("A", "$\\frac{1}{(x+1)^2}$", True), ("B", "$\\frac{x}{(x+1)^2}$", False), ("C", "$1$", False), ("D", "$\\frac{2x+1}{(x+1)^2}$", False)],
             "Quotient rule", ["Use quotient rule or simplify first."]),
            ("Derivatives", Question.Difficulty.HARD, "What is the derivative of $f(x) = e^{2x}$?",
             [("A", "$2e^{2x}$", True), ("B", "$e^{2x}$", False), ("C", "$2xe^{2x}$", False), ("D", "$e^x$", False)],
             "Chain rule", ["Chain rule on $e^{u}$ gives $u'e^u$."]),
            ("Derivatives", Question.Difficulty.HARD, "For $f(x) = \\ln x$, what is $f'(x)$?",
             [("A", "$\\frac{1}{x}$", True), ("B", "$x$", False), ("C", "$\\ln x$", False), ("D", "$e^x$", False)],
             "Logarithmic derivative", ["Standard derivative of natural log."]),
            ("Limits", Question.Difficulty.EASY, "What is $\\lim_{x \\to 2} (3x + 1)$?",
             [("A", "$7$", True), ("B", "$5$", False), ("C", "$6$", False), ("D", "$3$", False)],
             "Direct substitution", ["Substitute $x = 2$."]),
            ("Limits", Question.Difficulty.EASY, "What is $\\lim_{x \\to 0} \\frac{\\sin x}{x}$?",
             [("A", "$1$", True), ("B", "$0$", False), ("C", "$\\infty$", False), ("D", "undefined", False)],
             "Standard limit", ["Classic trigonometric limit equals 1."]),
            ("Limits", Question.Difficulty.MEDIUM, "What is $\\lim_{x \\to 1} \\frac{x^2 - 1}{x - 1}$?",
             [("A", "$2$", True), ("B", "$0$", False), ("C", "$1$", False), ("D", "undefined", False)],
             "Factoring limit", ["Factor numerator: $(x-1)(x+1)$."]),
            ("Limits", Question.Difficulty.MEDIUM, "If $\\lim_{x \\to a} f(x) = L$, what must be true for continuity at $a$?",
             [("A", "$f(a) = L$", True), ("B", "$f(a) = 0$", False), ("C", "$L = 0$", False), ("D", "$f$ is undefined at $a$", False)],
             "Continuity", ["Continuity requires the limit to equal the function value."]),
            ("Limits", Question.Difficulty.HARD, "What is $\\lim_{x \\to \\infty} \\frac{2x^2 + 1}{x^2 - 3}$?",
             [("A", "$2$", True), ("B", "$0$", False), ("C", "$\\infty$", False), ("D", "$1$", False)],
             "Limits at infinity", ["Compare leading terms; degrees match so ratio of coefficients."]),
            ("Limits", Question.Difficulty.HARD, "Which limit does **not** exist?",
             [("A", "$\\lim_{x \\to 0} \\frac{|x|}{x}$", True), ("B", "$\\lim_{x \\to 0} x^2$", False), ("C", "$\\lim_{x \\to 1} x$", False), ("D", "$\\lim_{x \\to 2} 5$", False)],
             "One-sided limits", ["Left and right limits disagree at 0."]),
            ("Graphs", Question.Difficulty.EASY, "In a graph, what does an edge represent?",
             [("A", "A connection between two vertices", True), ("B", "A vertex label", False), ("C", "A graph color", False), ("D", "A loop count", False)],
             "Graph basics", ["Edges join vertices."]),
            ("Graphs", Question.Difficulty.EASY, "How many edges does a tree with 5 vertices have?",
             [("A", "4", True), ("B", "5", False), ("C", "6", False), ("D", "10", False)],
             "Tree edges", ["A tree with $n$ vertices has $n-1$ edges."]),
            ("Graphs", Question.Difficulty.MEDIUM, "What is the degree of a vertex?",
             [("A", "Number of edges incident to it", True), ("B", "Number of vertices in the graph", False), ("C", "Length of longest path", False), ("D", "Number of components", False)],
             "Vertex degree", ["Degree counts incident edges."]),
            ("Graphs", Question.Difficulty.MEDIUM, "Which graph is bipartite?",
             [("A", "A graph with no odd cycles", True), ("B", "Any complete graph", False), ("C", "Any tree with 4 vertices only", False), ("D", "A graph with a triangle only", False)],
             "Bipartite graphs", ["No odd cycles is necessary and sufficient for bipartite graphs."]),
            ("Graphs", Question.Difficulty.HARD, "How many edges are in $K_4$?",
             [("A", "6", True), ("B", "4", False), ("C", "8", False), ("D", "12", False)],
             "Complete graphs", ["$K_n$ has $\\binom{n}{2}$ edges; $\\binom{4}{2} = 6$."]),
            ("Graphs", Question.Difficulty.HARD, "An Euler circuit exists in a connected graph when:",
             [("A", "Every vertex has even degree", True), ("B", "The graph is a tree", False), ("C", "Exactly two vertices have odd degree", False), ("D", "The graph is bipartite", False)],
             "Euler circuits", ["Euler circuit requires all degrees even."]),
        ]

        for topic_name, difficulty, stem, choices, concept_tag, steps in bank:
            topic = topics.get(f"cs:{topic_name}")
            if topic:
                self._create_mcq(topic, difficulty, stem, choices, concept_tag, steps)

    def _seed_questions(self, topics):
        self._seed_cs_catalog_questions(topics)

        bsed_algebra = topics.get("bsed_math:Algebra for Teachers")
        mkt_business = topics.get("marketing:Business Mathematics")

        questions_spec = []
        if bsed_algebra:
            questions_spec.append({
                "topic": bsed_algebra,
                "difficulty": Question.Difficulty.EASY,
                "type": Question.QuestionType.MCQ,
                "stem": "Solve for $x$: $2x + 5 = 13$",
                "concept_tag": "Linear equations",
                "choices": [("A", "$x = 3$", False), ("B", "$x = 4$", True), ("C", "$x = 5$", False), ("D", "$x = 6$", False)],
                "steps": ["Subtract 5 from both sides.", "Divide by 2."],
            })
        if mkt_business:
            questions_spec.append({
                "topic": mkt_business,
                "difficulty": Question.Difficulty.EASY,
                "type": Question.QuestionType.MCQ,
                "stem": "A product costs \\$80 and sells for \\$100. What is the markup percentage?",
                "concept_tag": "Markup percentage",
                "choices": [("A", "20%", False), ("B", "25%", True), ("C", "30%", False), ("D", "40%", False)],
                "steps": ["Markup = (100-80)/80 = 25%."],
            })

        for i in range(20):
            if not questions_spec:
                break
            base = questions_spec[i % len(questions_spec)]
            spec = dict(base)
            spec["stem"] = f"[Demo {i+1}] " + base["stem"]
            if Question.objects.filter(stem=spec["stem"]).exists():
                continue
            q = Question.objects.create(
                topic=spec["topic"],
                difficulty=spec["difficulty"],
                question_type=spec["type"],
                stem=spec["stem"],
                concept_tag=spec.get("concept_tag", ""),
                correct_answer=spec.get("answer"),
                tolerance=Decimal("0.01"),
                status=Question.Status.APPROVED,
            )
            if spec["type"] == Question.QuestionType.MCQ:
                for label, text, is_correct in spec["choices"]:
                    QuestionChoice.objects.create(
                        question=q, label=label, text=text, is_correct=is_correct
                    )
            for order, content in enumerate(spec["steps"], start=1):
                ExplanationStep.objects.create(question=q, order=order, content=content)

    def _seed_extras(self, course, professor, topics):
        if not course or not professor:
            return
        for slug, label, category in [
            ("sign_error", "Sign error", "procedural"),
            ("arithmetic", "Arithmetic error", "computational"),
        ]:
            ErrorType.objects.get_or_create(slug=slug, defaults={"label": label, "category": category})

        topic = topics.get("cs:Derivatives") or topics.get("cs:Sets")
        if not topic:
            return

        now = timezone.now()
        window, created = ReviewWindow.objects.get_or_create(
            course=course,
            title="Midterm 1 Review Weekend",
            defaults={
                "created_by": professor,
                "exam_type": ReviewWindow.ExamType.MIDTERM,
                "opens_at": now - timedelta(days=1),
                "closes_at": now + timedelta(days=7),
                "duration_minutes": 30,
                "seconds_per_question": 30,
                "mode": ReviewWindow.Mode.TIMED_EXAM,
                "allowed_difficulties": ["easy", "medium", "hard"],
            },
        )
        if created:
            cs_logic = topics.get("cs:Logic")
            window.topics.set([t for t in [topic, cs_logic] if t])

    def _seed_demo_narrative(self, courses, topics, programs):
        cs_course = courses.get("cs")
        psych_course = courses.get("psychology")
        cs_derivatives = topics.get("cs:Derivatives")
        psych_stats = topics.get("psychology:Research Statistics")

        student3 = User.objects.filter(email="student3@examiq.edu").first()
        student5 = User.objects.filter(email="student5@examiq.edu").first()
        student1 = User.objects.filter(email="student1@examiq.edu").first()

        if student3 and cs_course and cs_derivatives:
            student3.home_degree_program = User.HomeDegreeProgram.CS
            student3.save(update_fields=["home_degree_program"])
            self._create_demo_session(
                student3,
                cs_course,
                cs_derivatives,
                Question.Difficulty.EASY,
                days_ago=3,
                answers_spec=[(5, False), (5, False), (4, False), (3, True)],
            )

        if student5 and psych_course and psych_stats:
            student5.home_degree_program = User.HomeDegreeProgram.PSYCHOLOGY
            student5.save(update_fields=["home_degree_program"])
            self._create_demo_session(
                student5,
                psych_course,
                psych_stats,
                Question.Difficulty.EASY,
                days_ago=30,
                answers_spec=[(2, False), (2, False), (3, False), (1, True), (2, False)],
            )

        if student1 and cs_course and cs_derivatives:
            student1.home_degree_program = User.HomeDegreeProgram.CS
            student1.save(update_fields=["home_degree_program"])
            for days_ago in (14, 7, 2):
                self._create_demo_session(
                    student1,
                    cs_course,
                    cs_derivatives,
                    Question.Difficulty.EASY,
                    days_ago=days_ago,
                    answers_spec=[(4, True), (3, True), (4, False), (5, True)],
                )

        pending_specs = [
            ("cs:Logic", "Which statement is a tautology?", Question.Difficulty.MEDIUM),
            ("psychology:Data Interpretation", "What does a p-value below 0.05 indicate?", Question.Difficulty.EASY),
            ("marketing:Business Mathematics", "If revenue is $500 and cost is $400, what is profit margin?", Question.Difficulty.EASY),
        ]
        prof = User.objects.filter(email="prof.calculus@examiq.edu").first()
        for key, stem, difficulty in pending_specs:
            topic = topics.get(key)
            if not topic or Question.objects.filter(stem=stem).exists():
                continue
            Question.objects.create(
                topic=topic,
                difficulty=difficulty,
                question_type=Question.QuestionType.MCQ,
                stem=stem,
                status=Question.Status.PENDING,
                proposed_by=prof,
            )

    def _create_demo_session(self, student, course, topic, difficulty, days_ago, answers_spec):
        questions = list(
            Question.objects.filter(
                topic=topic,
                difficulty=difficulty,
                status=Question.Status.APPROVED,
                is_active=True,
            )[: max(len(answers_spec), 1)]
        )
        if not questions:
            return

        started = timezone.now() - timedelta(days=days_ago)
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

        for index, (confidence, is_correct) in enumerate(answers_spec):
            question = questions[index % len(questions)]
            if question.question_type == Question.QuestionType.MCQ:
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
            else:
                value = str(question.correct_answer) if is_correct else "0"
                answer = Answer.objects.create(
                    session=session,
                    question=question,
                    numeric_response=value,
                    confidence=confidence,
                    is_correct=is_correct,
                    time_spent_seconds=30,
                )
            if not is_correct:
                log_mistake(student=student, question=question, answer=answer)

        complete_session(session)
        ReviewSession.objects.filter(pk=session.pk).update(ended_at=started + timedelta(minutes=12))

    def _print_credentials(self, chairs):
        self.stdout.write("\nDemo credentials (password: demo1234):")
        self.stdout.write("  Chair (Education): chair.collegeofedu@examiq.edu")
        self.stdout.write("  Chair (CS):        chair.computersci@examiq.edu")
        self.stdout.write("  Professor:         prof.calculus@examiq.edu")
        self.stdout.write("  Professor:         prof.algebra@examiq.edu")
        self.stdout.write("  Student (CS demo): student3@examiq.edu - misconception pattern")
        self.stdout.write("  Student (Psych):   student5@examiq.edu - low practice / accuracy")
        self.stdout.write("  Student (trends):  student1@examiq.edu - multi-date sessions")
        self.stdout.write("  Students:          student1@examiq.edu ... student10@examiq.edu")
        self.stdout.write("\nAdmin: admin@examiq.edu / admin1234")
