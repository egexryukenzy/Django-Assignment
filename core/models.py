from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class User(AbstractUser):
    ROLE_CHOICES = [("admin", "Admin"), ("member", "Member")]
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.username

    @property
    def is_admin(self):
        return self.role == "admin"


class Project(models.Model):
    STATUS_CHOICES = [("active", "Active"), ("archived", "Archived")]
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="owned_projects"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("completed", "Completed")],
        default="active",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def total_cards(self):
        return Card.objects.filter(list__board__project=self).count()

    @property
    def done_cards(self):
        return Card.objects.filter(list__board__project=self, status="done").count()

    @property
    def progress(self):
        total = self.total_cards
        return int((self.done_cards / total) * 100) if total > 0 else 0


class ProjectMember(models.Model):
    ROLE_CHOICES = [("owner", "Owner"), ("admin", "Admin"), ("member", "Member")]
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")

    def __str__(self):
        return f"{self.user.username} - {self.project.name}"


class Board(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="boards"
    )
    name = models.CharField(max_length=100)
    background = models.CharField(max_length=50, blank=True, default="#1e293b")
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"{self.project.name} / {self.name}"


class List(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="lists")
    title = models.CharField(max_length=100)
    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.title


class Label(models.Model):
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="labels"
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=20, default="#3b82f6")

    def __str__(self):
        return self.name


class Card(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [("todo", "To Do"), ("doing", "Doing"), ("done", "Done")]

    list = models.ForeignKey(List, on_delete=models.CASCADE, related_name="cards")
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_cards"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="medium"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="todo")
    deadline = models.DateField(null=True, blank=True)
    position = models.IntegerField(default=0)
    labels = models.ManyToManyField(Label, blank=True, related_name="cards")
    assignees = models.ManyToManyField(
        User, blank=True, related_name="assigned_cards", through="CardAssignment"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        if self.deadline and self.status != "done":
            return self.deadline < timezone.now().date()
        return False


class CardAssignment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("card", "user")


class Comment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.user.username} on {self.card.title}"


class Attachment(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to="attachments/")
    file_name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name


class Notification(models.Model):
    TYPE_CHOICES = [
        ("assigned", "Task Assigned"),
        ("comment", "New Comment"),
        ("deadline", "Deadline Soon"),
        ("status", "Status Changed"),
        ("mention", "Mentioned"),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username}: {self.message[:40]}"
