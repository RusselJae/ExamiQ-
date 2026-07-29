"""Shared constants for home-degree-program → department mapping."""

from apps.users.models import User

# Maps each student home_degree_program value to the canonical department name
# used when seeding and resolving chairperson analytics scope.
HOME_PROGRAM_DEPARTMENT_NAMES: dict[str, str] = {
    User.HomeDegreeProgram.CS: "Department of Computer Studies",
    User.HomeDegreeProgram.IT: "Information Technology",
    User.HomeDegreeProgram.BSED_MATH: "College of Education",
    User.HomeDegreeProgram.PSYCHOLOGY: "Psychology",
    User.HomeDegreeProgram.MARKETING: "Business Administration",
    User.HomeDegreeProgram.HR: "Business Administration",
    User.HomeDegreeProgram.HOSPITALITY: "Hospitality Management",
    User.HomeDegreeProgram.CRIMINOLOGY: "Criminology",
}

# Canonical degree programs — slug, display name, managing department name.
PROGRAM_DEFINITIONS: list[tuple[str, str, str]] = [
    (User.HomeDegreeProgram.CS, "Computer Science", "Department of Computer Studies"),
    (User.HomeDegreeProgram.IT, "Information Technology", "Information Technology"),
    (User.HomeDegreeProgram.BSED_MATH, "BSEd Mathematics", "College of Education"),
    (User.HomeDegreeProgram.PSYCHOLOGY, "Psychology", "Psychology"),
    (User.HomeDegreeProgram.MARKETING, "Marketing", "Business Administration"),
    (User.HomeDegreeProgram.HR, "Human Resources", "Business Administration"),
    (User.HomeDegreeProgram.HOSPITALITY, "Hospitality Management", "Hospitality Management"),
    (User.HomeDegreeProgram.CRIMINOLOGY, "Criminology", "Criminology"),
]

# Short codes for section labels (e.g. "BSCS 1-2").
PROGRAM_ABBREVIATIONS: dict[str, str] = {
    User.HomeDegreeProgram.CS: "BSCS",
    User.HomeDegreeProgram.IT: "BSIT",
    User.HomeDegreeProgram.BSED_MATH: "BSE",
    User.HomeDegreeProgram.PSYCHOLOGY: "BSPSY",
    User.HomeDegreeProgram.MARKETING: "BSBA-MKT",
    User.HomeDegreeProgram.HR: "BSBA-HR",
    User.HomeDegreeProgram.HOSPITALITY: "BSHM",
    User.HomeDegreeProgram.CRIMINOLOGY: "BSCRIM",
}


def home_programs_for_department(department) -> list[str]:
    """Return home_degree_program values whose students belong to this department."""
    if department is None:
        return []
    return [
        program
        for program, dept_name in HOME_PROGRAM_DEPARTMENT_NAMES.items()
        if dept_name == department.name
    ]


def students_in_department(department):
    """Queryset filter helper: students whose home program maps to this department."""
    from apps.users.models import User

    programs = home_programs_for_department(department)
    return User.objects.filter(role=User.Role.STUDENT, home_degree_program__in=programs)
