from .models import Notification


def notify(user, title, body, kind="update"):
    return Notification.objects.create(
        recipient=user,
        title=title,
        body=body,
        kind=kind,
    )
