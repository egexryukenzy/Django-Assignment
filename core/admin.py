from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Project, ProjectMember, Board, List, Card, Label, Comment, Attachment, Notification, CardAssignment

admin.site.register(User, UserAdmin)
admin.site.register(Project)
admin.site.register(ProjectMember)
admin.site.register(Board)
admin.site.register(List)
admin.site.register(Card)
admin.site.register(Label)
admin.site.register(Comment)
admin.site.register(Attachment)
admin.site.register(Notification)
admin.site.register(CardAssignment)
