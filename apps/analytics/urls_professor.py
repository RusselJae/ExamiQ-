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
    path("students/", views_professor.ProfessorStudentsView.as_view(), name="students"),
    path(
        "students/<int:student_pk>/",
        views_professor.ProfessorStudentDetailView.as_view(),
        name="professor_student_detail",
    ),
    path(
        "students/<int:student_pk>/sessions/<int:session_pk>/review/",
        views_professor.ProfessorSessionReviewView.as_view(),
        name="session_review",
    ),
    path("chat/", views_professor_feedback.GlobalChatInboxView.as_view(), name="chat_inbox"),
    path(
        "chat/conversations/",
        views_professor_feedback.GlobalChatConversationsApiView.as_view(),
        name="chat_conversations_api",
    ),
    path(
        "chat/concerns/",
        views_professor_feedback.GlobalChatConversationsApiView.as_view(),
        name="chat_concerns_api",
    ),
    path(
        "chat/<int:conversation_pk>/message/",
        views_professor_feedback.GlobalChatFacultyMessageView.as_view(),
        name="chat_faculty_message",
    ),
    path(
        "chat/<int:conversation_pk>/note/",
        views_professor_feedback.GlobalChatFacultyMessageView.as_view(),
        name="chat_faculty_note",
    ),
    path(
        "exam-setup/",
        views_professor.ExamSetupHubView.as_view(),
        name="exam_setup_hub",
    ),
    path("courses/", course_views.ProfessorCourseListView.as_view(), name="course_list"),
    path("courses/create/", course_views.ProfessorCourseCreateView.as_view(), name="course_create"),
    path("courses/<int:pk>/clone/", course_views.ProfessorCourseCloneView.as_view(), name="course_clone"),
    path("courses/<int:pk>/archive/", course_views.ProfessorCourseArchiveView.as_view(), name="course_archive"),
    path(
        "courses/subjects/<int:subject_pk>/remove/",
        course_views.ProfessorCourseRemoveView.as_view(),
        name="course_subject_remove",
    ),
    path(
        "questions/add/",
        question_views.QuestionAddHubView.as_view(),
        name="question_add",
    ),
    path(
        "sections/<int:pk>/",
        views_professor.SectionDetailView.as_view(),
        name="section_detail",
    ),
    path(
        "sections/<int:section_pk>/roster/",
        views_professor.SectionRosterView.as_view(),
        name="section_roster",
    ),
    path(
        "sections/<int:section_pk>/roster/<int:student_pk>/",
        views_professor.SectionStudentDetailView.as_view(),
        name="section_student_detail",
    ),
    path(
        "sections/<int:section_pk>/roster/<int:student_pk>/archive/",
        views_professor.SectionStudentArchiveView.as_view(),
        name="section_student_archive",
    ),
    path(
        "sections/<int:section_pk>/roster/<int:student_pk>/restore/",
        views_professor.SectionStudentRestoreView.as_view(),
        name="section_student_restore",
    ),
    path(
        "sections/<int:section_pk>/exam-setup/",
        views_professor.SectionExamSetupRedirectView.as_view(),
        name="section_exam_setup",
    ),
    path(
        "sections/<int:section_pk>/heatmap/",
        views_professor.SectionHeatmapView.as_view(),
        name="section_heatmap",
    ),
    path(
        "sections/<int:section_pk>/feedback/",
        views_professor.SectionFeedbackView.as_view(),
        name="section_feedback",
    ),
    path(
        "sections/<int:section_pk>/feedback/concerns/",
        views_professor_feedback.SectionFeedbackConcernsApiView.as_view(),
        name="section_feedback_concerns_api",
    ),
    path(
        "sections/<int:section_pk>/feedback/<int:mistake_pk>/note/",
        views_professor_feedback.SectionFeedbackFacultyNoteView.as_view(),
        name="section_feedback_faculty_note",
    ),
    path(
        "subjects/<int:pk>/",
        views_professor.SubjectDetailView.as_view(),
        name="subject_detail",
    ),
    path(
        "subjects/<int:subject_pk>/roster/",
        views_professor.SubjectRosterView.as_view(),
        name="subject_roster",
    ),
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
        "courses/<int:course_pk>/questions/import-csv/",
        question_views.QuestionCSVImportView.as_view(),
        name="question_csv_import",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-generate/",
        question_views.QuestionAIGenerateView.as_view(),
        name="question_ai_generate",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-generate/<int:job_id>/",
        question_views.QuestionAIGenerateStatusView.as_view(),
        name="question_ai_generate_status",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-validate/",
        question_views.QuestionAIValidateView.as_view(),
        name="question_ai_validate",
    ),
    path(
        "courses/<int:course_pk>/questions/ai-detect-topics/",
        question_views.QuestionAIDetectTopicsView.as_view(),
        name="question_ai_detect_topics",
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
        "courses/<int:course_pk>/questions/<int:question_pk>/toggle-active/",
        question_views.QuestionToggleActiveView.as_view(),
        name="question_toggle_active",
    ),
    path(
        "courses/<int:course_pk>/questions/suggest-difficulty/",
        question_views.QuestionSuggestDifficultyView.as_view(),
        name="question_suggest_difficulty",
    ),
    path(
        "courses/<int:course_pk>/feedback/",
        views_professor_feedback.FeedbackListView.as_view(),
        name="feedback_list",
    ),
    path(
        "courses/<int:course_pk>/feedback/concerns/",
        views_professor_feedback.FeedbackConcernsApiView.as_view(),
        name="feedback_concerns_api",
    ),
    path(
        "courses/<int:course_pk>/feedback/<int:mistake_pk>/note/",
        views_professor_feedback.FeedbackFacultyNoteView.as_view(),
        name="feedback_faculty_note",
    ),
]
