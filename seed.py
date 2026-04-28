import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tasktracker.settings')
django.setup()

from core.models import User, Project, ProjectMember, Board, List, Card, Label, Comment, CardAssignment, Notification

# Create users
admin = User.objects.create_superuser('admin', 'admin@taskflow.com', 'admin123', role='admin', first_name='Admin', last_name='User')
m1 = User.objects.create_user('dara', 'dara@taskflow.com', 'member123', role='member', first_name='Dara', last_name='Chan')
m2 = User.objects.create_user('sophea', 'sophea@taskflow.com', 'member123', role='member', first_name='Sophea', last_name='Lim')
m3 = User.objects.create_user('virak', 'virak@taskflow.com', 'member123', role='member', first_name='Virak', last_name='Sok')

print("✓ Users created")

# Project 1: Website Redesign
p1 = Project.objects.create(owner=admin, name='Website Redesign', description='Redesign the company website with modern UI/UX', status='active')
ProjectMember.objects.create(project=p1, user=admin, role='owner')
ProjectMember.objects.create(project=p1, user=m1, role='admin')
ProjectMember.objects.create(project=p1, user=m2, role='member')

b1 = Board.objects.create(project=p1, name='Sprint 1', position=0)
todo1 = List.objects.create(board=b1, title='To Do / ត្រូវធ្វើ', position=0)
doing1 = List.objects.create(board=b1, title='Doing / កំពុងធ្វើ', position=1)
done1 = List.objects.create(board=b1, title='Done / បានធ្វើ', position=2)

lb1 = Label.objects.create(project=p1, name='Frontend', color='#3b82f6')
lb2 = Label.objects.create(project=p1, name='Backend', color='#7c3aed')
lb3 = Label.objects.create(project=p1, name='Bug', color='#ef4444')
lb4 = Label.objects.create(project=p1, name='Feature', color='#10b981')

from datetime import date, timedelta
today = date.today()

c1 = Card.objects.create(list=todo1, created_by=admin, title='Design homepage mockup', priority='high', status='todo', deadline=today+timedelta(days=7), position=0)
c1.labels.add(lb1)
CardAssignment.objects.create(card=c1, user=m1)

c2 = Card.objects.create(list=todo1, created_by=admin, title='Set up project repository', priority='medium', status='todo', deadline=today+timedelta(days=3), position=1)
c2.labels.add(lb2)
CardAssignment.objects.create(card=c2, user=m2)

c3 = Card.objects.create(list=doing1, created_by=m1, title='Build navigation component', priority='high', status='doing', deadline=today+timedelta(days=2), position=0)
c3.labels.add(lb1, lb4)
CardAssignment.objects.create(card=c3, user=m1)
CardAssignment.objects.create(card=c3, user=m2)
Comment.objects.create(card=c3, user=m1, content='Started working on the mobile menu. Should be done by tomorrow.')
Comment.objects.create(card=c3, user=m2, content='Looks great! Make sure to test on Safari.')

c4 = Card.objects.create(list=doing1, created_by=m2, title='Fix responsive layout bugs', priority='critical', status='doing', deadline=today-timedelta(days=1), position=1)
c4.labels.add(lb3)
CardAssignment.objects.create(card=c4, user=m2)

c5 = Card.objects.create(list=done1, created_by=admin, title='Project requirements document', priority='medium', status='done', deadline=today-timedelta(days=5), position=0)
CardAssignment.objects.create(card=c5, user=admin)

c6 = Card.objects.create(list=done1, created_by=m1, title='Setup CI/CD pipeline', priority='low', status='done', deadline=today-timedelta(days=3), position=1)
c6.labels.add(lb2)
CardAssignment.objects.create(card=c6, user=m1)

print("✓ Project 1 created")

# Project 2: Mobile App
p2 = Project.objects.create(owner=m1, name='Mobile App Development', description='Build a cross-platform mobile app for task management', status='active')
ProjectMember.objects.create(project=p2, user=m1, role='owner')
ProjectMember.objects.create(project=p2, user=m3, role='member')

b2 = Board.objects.create(project=p2, name='Main Board', position=0)
todo2 = List.objects.create(board=b2, title='To Do / ត្រូវធ្វើ', position=0)
doing2 = List.objects.create(board=b2, title='Doing / កំពុងធ្វើ', position=1)
done2 = List.objects.create(board=b2, title='Done / បានធ្វើ', position=2)

lb5 = Label.objects.create(project=p2, name='iOS', color='#06b6d4')
lb6 = Label.objects.create(project=p2, name='Android', color='#84cc16')

c7 = Card.objects.create(list=todo2, created_by=m1, title='Design app wireframes', priority='high', status='todo', deadline=today+timedelta(days=10), position=0)
c7.labels.add(lb5, lb6)
CardAssignment.objects.create(card=c7, user=m3)

c8 = Card.objects.create(list=doing2, created_by=m1, title='Implement login screen', priority='medium', status='doing', position=0)
c8.labels.add(lb5)
CardAssignment.objects.create(card=c8, user=m1)

c9 = Card.objects.create(list=done2, created_by=m3, title='Setup React Native project', priority='low', status='done', deadline=today-timedelta(days=2), position=0)
CardAssignment.objects.create(card=c9, user=m3)

print("✓ Project 2 created")

# Notifications
Notification.objects.create(user=m1, type='assigned', message='You were assigned to "Build navigation component"', link=f'/cards/{c3.id}/')
Notification.objects.create(user=m1, type='comment', message='Sophea commented on "Build navigation component"', link=f'/cards/{c3.id}/')
Notification.objects.create(user=m2, type='assigned', message='You were assigned to "Fix responsive layout bugs"', link=f'/cards/{c4.id}/')
Notification.objects.create(user=m2, type='deadline', message='Task "Fix responsive layout bugs" is overdue!', link=f'/cards/{c4.id}/')

print("✓ Notifications created")
print("\n✅ Seed complete!")
print("Admin: admin / admin123")
print("Members: dara / sophea / virak — all use password: member123")
