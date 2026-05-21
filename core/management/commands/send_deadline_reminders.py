from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = "Create deadline-reminder notifications for cards due within 24 hours."

    def handle(self, *args, **options):
        from core.models import Card, Notification

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)

        cards = Card.objects.filter(
            deadline__in=[today, tomorrow],
            status__in=["todo", "doing"],
        ).prefetch_related("assignees")

        created_count = 0

        for card in cards:
            days_left = (card.deadline - today).days
            time_label = "today / ថ្ងៃនេះ" if days_left == 0 else "tomorrow / ថ្ងៃស្អែក"
            message = f'Task "{card.title}" is due {time_label}!'

            for user in card.assignees.all():
                already_notified = Notification.objects.filter(
                    user=user,
                    type="deadline",
                    link=f"/cards/{card.id}/",
                    created_at__date=today,
                ).exists()

                if not already_notified:
                    Notification.objects.create(
                        user=user,
                        type="deadline",
                        message=message,
                        link=f"/cards/{card.id}/",
                    )
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"[Deadline Reminders] {created_count} notification(s) created "
            f"(checked {cards.count()} card(s) due today/tomorrow)."
        ))
