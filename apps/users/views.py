"""User profile views."""

from allauth.account.models import EmailAddress
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from apps.users.faculty_pin_services import get_faculty_signup_pin_status
from apps.users.forms import (
    EmailChangeRequestForm,
    ExamiQChangePasswordForm,
    FacultySignupPinForm,
    ProfileUpdateForm,
)
from apps.users.models import User
from apps.users.services import get_account_activity


def _user_can_manage_faculty_signup_pin(user: User) -> bool:
    return user.role in (User.Role.PROFESSOR, User.Role.CHAIRPERSON)


class ProfileView(LoginRequiredMixin, View):
    template_name = "users/profile.html"

    def get_forms(self, user):
        forms = {
            "profile_form": ProfileUpdateForm(user=user),
            "email_form": EmailChangeRequestForm(user=user),
            "password_form": ExamiQChangePasswordForm(user=user),
        }
        if _user_can_manage_faculty_signup_pin(user):
            forms["faculty_pin_form"] = FacultySignupPinForm(user=user)
        return forms

    def get_context(self, user, forms=None):
        forms = forms or self.get_forms(user)
        context = {
            **forms,
            "pending_emails": EmailAddress.objects.filter(user=user, verified=False),
            "account_activity": get_account_activity(user),
            "can_manage_faculty_signup_pin": _user_can_manage_faculty_signup_pin(user),
        }
        if context["can_manage_faculty_signup_pin"]:
            context["faculty_signup_pin_status"] = get_faculty_signup_pin_status()
        return context

    def get(self, request):
        return render(request, self.template_name, self.get_context(request.user))

    def post(self, request):
        action = request.POST.get("action")
        user = request.user

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

        if action == "update_faculty_pin":
            if not _user_can_manage_faculty_signup_pin(user):
                return redirect("users:profile")
            form = FacultySignupPinForm(user=user, data=request.POST)
            forms = self.get_forms(user)
            forms["faculty_pin_form"] = form
            if form.is_valid():
                form.save()
                messages.success(
                    request,
                    "Faculty signup PIN updated. Other faculty accounts were notified by email.",
                )
                return redirect("users:profile")
            return render(request, self.template_name, self.get_context(user, forms))

        return render(request, self.template_name, self.get_context(user))
