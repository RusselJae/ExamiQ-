from django.urls import path

from apps.analytics import views_professor
from apps.questions import views_professor as question_views
from apps.reviews import views_professor as review_views
from apps.reviews import views_professor_feedback
from apps.users import views_professor as course_views

app_name = "analytics_professor"

urlpatterns = [
    path("overview/", views_professor.ProfessorOverviewView.as_view(), name="overview"),
    path("dashboard/", views_professor.ProfessorDashboardView.as_view(), name="dashboard"),
    path("courses/", course_views.ProfessorCourseListView.as_view(), name="course_list"),
    path("courses/create/", course_views.ProfessorCourseCreateView.as_view(), name="course_create"),
    path("courses/<int:pk>/clone/", course_views.ProfessorCourseCloneView.as_view(), name="course_clone"),
    path("courses/<int:pk>/archive/", course_views.ProfessorCourseArchiveView.as_view(), name="course_archive"),
    path("courses/<int:pk>/", views_professor.CourseDetailView.as_view(), name="course_detail"),
    path(
        "courses/<int:pk>/summary/generate/",
        views_professor.CourseSummaryGenerateView.as_view(),
        name="course_summary_generate",
    ),
    path(
        "courses/<int:pk>/interventions/export/",
        views_professor.CourseInterventionsExportView.as_view(),
        name="course_interventions_export",
    ),
    path("courses/<int:course_pk>/roster/", views_professor.CourseRosterView.as_view(), name="course_roster"),
    path(
        "courses/<int:course_pk>/roster/<int:student_pk>/",
        views_professor.StudentDetailView.as_view(),
        name="student_detail",
    ),
    path("courses/<int:pk>/insights/", views_professor.CourseInsightsRedirectView.as_view(), name="course_insights"),
    path("courses/<int:pk>/heatmap/", views_professor.CourseHeatmapView.as_view(), name="course_heatmap"),
    path("courses/<int:course_pk>/exam-setup/", review_views.ExamSetupUpdateView.as_view(), name="exam_setup"),
    path("courses/<int:course_pk>/windows/", review_views.ReviewWindowListView.as_view(), name="window_list"),
    path("courses/<int:course_pk>/windows/create/", review_views.ReviewWindowCreateView.as_view(), name="window_create"),
    path(
        "courses/<int:course_pk>/windows/<int:window_pk>/edit/",
        review_views.ReviewWindowUpdateView.as_view(),
        name="window_edit",
    ),
    path(
        "courses/<int:course_pk>/windows/<int:window_pk>/delete/",
        review_views.ReviewWindowDeleteView.as_view(),
        name="window_delete",
    ),
    path("courses/<int:course_pk>/topics/", question_views.TopicListView.as_view(), name="topic_list"),
    path(
        "courses/<int:course_pk>/topics/create/",
        question_views.TopicCreateView.as_view(),
        name="topic_create",
    ),
    path(
        "courses/<int:course_pk>/topics/<int:topic_pk>/edit/",
        question_views.TopicUpdateView.as_view(),
        name="topic_edit",
    ),
    path(
        "courses/<int:course_pk>/topics/<int:topic_pk>/delete/",
        question_views.TopicDeleteView.as_view(),
        name="topic_delete",
    ),
    path("courses/<int:course_pk>/questions/", question_views.QuestionListView.as_view(), name="question_list"),
    path(
        "courses/<int:course_pk>/questions/create/",
        question_views.QuestionBatchCreateView.as_view(),
        name="question_create",
    ),
    path(
        "courses/<int:course_pk>/questions/create/edit/<int:question_index>/",
        question_views.QuestionBatchEditView.as_view(),
        name="question_batch_edit",
    ),
    path(
        "courses/<int:course_pk>/questions/create/single/",
        question_views.QuestionCreateView.as_view(),
        name="question_create_single",
    ),
    path(
        "courses/<int:course_pk>/curriculum/subjects/",
        question_views.ProfessorCurriculumSubjectsView.as_view(),
        name="curriculum_subjects",
    ),
    path(
        "courses/<int:course_pk>/curriculum/topics/",
        question_views.ProfessorCurriculumTopicsView.as_view(),
        name="curriculum_topics",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-generate/",
        question_views.QuestionAIGenerateView.as_view(),
        name="question_ai_generate",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-validate/",
        question_views.QuestionAIValidateView.as_view(),
        name="question_ai_validate",
    ),
    path(
        "courses/<int:course_pk>/questions/<int:question_pk>/edit/",
        question_views.QuestionUpdateView.as_view(),
        name="question_edit",
    ),
    path(
        "courses/<int:course_pk>/questions/<int:question_pk>/delete/",
        question_views.QuestionDeleteView.as_view(),
        name="question_delete",
    ),
    path(
        "courses/<int:course_pk>/questions/suggest-difficulty/",
        question_views.QuestionSuggestDifficultyView.as_view(),
        name="question_suggest_difficulty",
    ),
    path(
        "courses/<int:course_pk>/questions/<int:question_pk>/generate-variations/",
        question_views.QuestionGenerateVariationsView.as_view(),
        name="question_generate_variations",
    ),
    path(
        "courses/<int:course_pk>/questions/<int:question_pk>/confirm-variations/",
        question_views.QuestionConfirmVariationsView.as_view(),
        name="question_confirm_variations",
    ),
    path(
        "courses/<int:course_pk>/feedback/",
        views_professor_feedback.FeedbackListView.as_view(),
        name="feedback_list",
    ),
    path(
        "courses/<int:course_pk>/feedback/<int:question_pk>/edit/",
        views_professor_feedback.FeedbackEditView.as_view(),
        name="feedback_edit",
    ),
]
