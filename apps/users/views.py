"""User profile views."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View

from allauth.account.models import EmailAddress

from apps.research.forms import PilotConsentForm, PostSurveyForm, PreSurveyForm
from apps.research.models import PilotConsent, SurveyResponse
from apps.users.forms import (
    EmailChangeRequestForm,
    ExamiQChangePasswordForm,
    ProfileUpdateForm,
)
from apps.users.models import User
from apps.users.services import get_account_activity


class ProfileView(LoginRequiredMixin, View):
    template_name = "users/profile.html"

    def get_forms(self, user):
        return {
            "profile_form": ProfileUpdateForm(user=user),
            "email_form": EmailChangeRequestForm(user=user),
            "password_form": ExamiQChangePasswordForm(user=user),
        }

    def get_survey_context(self, user):
        if user.role != User.Role.STUDENT:
            return {}
        consent = PilotConsent.objects.filter(student=user).first()
        pre = SurveyResponse.objects.filter(
            student=user, survey_type=SurveyResponse.SurveyType.PRE
        ).first()
        post = SurveyResponse.objects.filter(
            student=user, survey_type=SurveyResponse.SurveyType.POST
        ).first()
        return {
            "pilot_consent": consent,
            "consent_form": PilotConsentForm(instance=consent or PilotConsent(student=user)),
            "pre_survey": pre,
            "post_survey": post,
            "pre_survey_form": PreSurveyForm(instance=pre),
            "post_survey_form": PostSurveyForm(instance=post),
            "show_pilot_section": True,
        }

    def get_context(self, user, forms=None):
        forms = forms or self.get_forms(user)
        return {
            **forms,
            **self.get_survey_context(user),
            "pending_emails": EmailAddress.objects.filter(user=user, verified=False),
            "account_activity": get_account_activity(user),
        }

    def get(self, request):
        return render(request, self.template_name, self.get_context(request.user))

    def post(self, request):
        action = request.POST.get("action")
        user = request.user

        if action == "pilot_consent" and user.role == User.Role.STUDENT:
            consent, _ = PilotConsent.objects.get_or_create(student=user)
            form = PilotConsentForm(request.POST, instance=consent)
            if form.is_valid():
                obj = form.save(commit=False)
                if obj.consented and not obj.consented_at:
                    obj.consented_at = timezone.now()
                obj.save()
                messages.success(request, "Pilot study consent saved.")
                return redirect("users:profile")
            ctx = self.get_context(user)
            ctx["consent_form"] = form
            return render(request, self.template_name, ctx)

        if action == "pre_survey" and user.role == User.Role.STUDENT:
            existing = SurveyResponse.objects.filter(
                student=user, survey_type=SurveyResponse.SurveyType.PRE
            ).first()
            form = PreSurveyForm(request.POST, instance=existing)
            if form.is_valid():
                survey = form.save(commit=False)
                survey.student = user
                survey.survey_type = SurveyResponse.SurveyType.PRE
                survey.save()
                messages.success(request, "Pre-study survey submitted. Thank you!")
                return redirect("users:profile")
            ctx = self.get_context(user)
            ctx["pre_survey_form"] = form
            return render(request, self.template_name, ctx)

        if action == "post_survey" and user.role == User.Role.STUDENT:
            existing = SurveyResponse.objects.filter(
                student=user, survey_type=SurveyResponse.SurveyType.POST
            ).first()
            form = PostSurveyForm(request.POST, instance=existing)
            if form.is_valid():
                survey = form.save(commit=False)
                survey.student = user
                survey.survey_type = SurveyResponse.SurveyType.POST
                survey.save()
                messages.success(request, "Post-study survey submitted. Thank you!")
                return redirect("users:profile")
            ctx = self.get_context(user)
            ctx["post_survey_form"] = form
            return render(request, self.template_name, ctx)

        if action == "update_profile":
            form = ProfileUpdateForm(user=user, data=request.POST, files=request.FILES)
            forms = self.get_forms(user)
            forms["profile_form"] = form
            if form.is_valid():
                form.save()
                messages.success(request, "Profile updated.")
                return redirect("users:profile")
            return render(request, self.template_name, self.get_context(user, forms))

        if action == "remove_photo":
            if user.profile_photo:
                user.profile_photo.delete(save=False)
                user.profile_photo = None
                user.save(update_fields=["profile_photo"])
                messages.success(request, "Profile photo removed.")
            return redirect("users:profile")

        if action == "request_email_change":
            form = EmailChangeRequestForm(user=user, data=request.POST)
            forms = self.get_forms(user)
            forms["email_form"] = form
            if form.is_valid():
                form.save(request)
                messages.info(request, "Check your inbox to confirm the new email.")
                return redirect("users:profile")
            return render(request, self.template_name, self.get_context(user, forms))

        if action == "change_password":
            form = ExamiQChangePasswordForm(user=user, data=request.POST)
            forms = self.get_forms(user)
            forms["password_form"] = form
            if form.is_valid():
                form.save()
                messages.success(request, "Password updated.")
                return redirect("users:profile")
            return render(request, self.template_name, self.get_context(user, forms))

        return render(request, self.template_name, self.get_context(user))
