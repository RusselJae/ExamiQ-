from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.users.email_services import send_pending_registration_alert
from apps.users.models import User
from apps.users.notification_services import create_notification


@receiver(post_save, sender=User)
def notify_on_pending_staff_registration(sender, instance: User, created: bool, **kwargs):
    if not created:
        return
    if instance.role not in (User.Role.PROFESSOR, User.Role.CHAIRPERSON):
        return
    if instance.approval_status != User.ApprovalStatus.PENDING:
        return

    send_pending_registration_alert(instance)

    from apps.users.email_services import get_campus_admin_emails

    for email in get_campus_admin_emails():
        admin = User.objects.filter(email=email).first()
        if admin:
            create_notification(
                admin,
                f"New pending {instance.get_role_display().lower()} registration: {instance.email}",
                link="/campus/users/?status=pending",
            )
