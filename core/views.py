from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
import json

from .models import (
    User,
    Project,
    ProjectMember,
    Board,
    List,
    Card,
    Label,
    Comment,
    Attachment,
    Notification,
    CardAssignment,
)


# ─── AUTH ─────────────────────────────────────────────────────────────────────


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Invalid username or password")
    return render(request, "auth/login.html")

def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        full_name = request.POST.get("full_name", "")
        role = request.POST.get("role", "member")
        avatar = request.FILES.get("avatar")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken")
        elif User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=full_name.split()[0] if full_name else "",
                last_name=" ".join(full_name.split()[1:])
                if full_name and len(full_name.split()) > 1
                else "",
                role=role,
            )
            if avatar:
                user.avatar = avatar
                user.save()

            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect("dashboard")

    return render(request, "auth/register.html")


def logout_view(request):
    logout(request)
    return redirect("login")


# ─── DASHBOARD ────────────────────────────────────────────────────────────────


@login_required
def dashboard(request):
    user = request.user

    # ─── PROJECTS ─────────────────────────────
    if user.is_admin:
        projects = Project.objects.all()
    else:
        member_ids = ProjectMember.objects.filter(user=user).values_list(
            "project_id", flat=True
        )
        projects = Project.objects.filter(
            Q(owner=user) | Q(id__in=member_ids)
        ).distinct()

    projects = projects.order_by("-created_at")  # newest first
    total_projects = projects.count()

    # 🔥 Project stats (NEW)
    completed_projects = projects.filter(status="completed").count()
    active_projects = projects.filter(status="active").count()

    # ─── TASKS (CARDS) ───────────────────────
    cards = Card.objects.filter(list__board__project__in=projects).distinct()

    total_tasks = cards.count()
    done_tasks = cards.filter(status="done").count()
    doing_tasks = cards.filter(status="doing").count()
    todo_tasks = cards.filter(status="todo").count()

    # ─── MY TASKS ────────────────────────────
    my_cards = (
        cards.filter(assignees=user).exclude(status="done").order_by("deadline")[:5]
    )

    # ─── OVERDUE ─────────────────────────────
    overdue_cards = [c for c in my_cards if c.is_overdue]

    # ─── NOTIFICATIONS ───────────────────────
    notifications = user.notifications.filter(is_read=False).order_by("-created_at")[:5]
    unread_count = user.notifications.filter(is_read=False).count()

    context = {
        # Projects
        "projects": projects[:6],  # show latest 6 in dashboard
        "completed_projects": completed_projects,
        "active_projects": active_projects,
        # Tasks
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "doing_tasks": doing_tasks,
        "todo_tasks": todo_tasks,
        "total_projects": total_projects,
        # Cards
        "my_cards": my_cards,
        "overdue_cards": overdue_cards,
        # Notifications
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(request, "dashboard.html", context)


# ─── PROJECTS ─────────────────────────────────────────────────────────────────


@login_required
def project_list(request):
    user = request.user
    if user.is_admin:
        projects = Project.objects.all().order_by("-created_at")
    else:
        member_ids = ProjectMember.objects.filter(user=user).values_list(
            "project_id", flat=True
        )
        projects = (
            Project.objects.filter(Q(owner=user) | Q(id__in=member_ids))
            .distinct()
            .order_by("-created_at")
        )

    q = request.GET.get("q", "")
    if q:
        projects = projects.filter(name__icontains=q)

    context = {
        "projects": projects,
        "q": q,
        "unread_count": user.notifications.filter(is_read=False).count(),
    }
    return render(request, "projects/list.html", context)


@login_required
def project_create(request):
    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description", "")
        project = Project.objects.create(
            owner=request.user, name=name, description=description
        )
        ProjectMember.objects.create(project=project, user=request.user, role="owner")
        # Default board with 3 lists
        board = Board.objects.create(project=project, name="Main Board", position=0)
        List.objects.create(board=board, title="To Do / ត្រូវធ្វើ", position=0)
        List.objects.create(board=board, title="Doing / កំពុងធ្វើ", position=1)
        List.objects.create(board=board, title="Done / បានធ្វើ", position=2)
        messages.success(request, f'Project "{name}" created!')
        return redirect("board", project_id=project.id, board_id=board.id)
    return render(
        request,
        "projects/create.html",
        {"unread_count": request.user.notifications.filter(is_read=False).count()},
    )


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    can_access = (
        request.user.is_admin
        or project.owner == request.user
        or ProjectMember.objects.filter(project=project, user=request.user).exists()
    )
    if not can_access:
        messages.error(request, "Access denied")
        return redirect("projects")

    members = ProjectMember.objects.filter(project=project).select_related("user")
    boards = project.boards.all()
    member_user_ids = members.values_list("user_id", flat=True)
    all_users = User.objects.filter(is_active=True).exclude(id__in=member_user_ids)
    context = {
        "project": project,
        "members": members,
        "boards": boards,
        "all_users": all_users,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "projects/detail.html", context)


@login_required
def project_edit(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if request.user != project.owner and not request.user.is_admin:
        messages.error(request, "Permission denied")
        return redirect("project_detail", project_id=project_id)
    if request.method == "POST":
        project.name = request.POST.get("name", project.name)
        project.description = request.POST.get("description", project.description)
        project.status = request.POST.get("status", project.status)
        project.save()
        messages.success(request, "Project updated!")
        return redirect("project_detail", project_id=project_id)
    return render(
        request,
        "projects/edit.html",
        {
            "project": project,
            "unread_count": request.user.notifications.filter(is_read=False).count(),
        },
    )


@login_required
def project_delete(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if request.user != project.owner and not request.user.is_admin:
        messages.error(request, "Permission denied")
        return redirect("projects")
    if request.method == "POST":
        project.delete()
        messages.success(request, "Project deleted.")
        return redirect("projects")
    return redirect("projects")


@login_required
@require_POST
def project_add_member(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    user_id = request.POST.get("user_id")
    role = request.POST.get("role", "member")
    try:
        user = User.objects.get(id=user_id)
        ProjectMember.objects.get_or_create(
            project=project, user=user, defaults={"role": role}
        )
        Notification.objects.create(
            user=user,
            type="assigned",
            message=f'You were added to project "{project.name}"',
            link=f"/projects/{project.id}/",
        )
        messages.success(request, f"{user.username} added!")
    except User.DoesNotExist:
        messages.error(request, "User not found")
    return redirect("project_detail", project_id=project_id)


@login_required
def project_remove_member(request, project_id, user_id):
    project = get_object_or_404(Project, id=project_id)
    ProjectMember.objects.filter(project=project, user_id=user_id).delete()
    messages.success(request, "Member removed.")
    return redirect("project_detail", project_id=project_id)


# ─── BOARD / KANBAN ───────────────────────────────────────────────────────────


@login_required
def board_view(request, project_id, board_id):
    project = get_object_or_404(Project, id=project_id)
    board = get_object_or_404(Board, id=board_id, project=project)
    can_access = (
        request.user.is_admin
        or project.owner == request.user
        or ProjectMember.objects.filter(project=project, user=request.user).exists()
    )
    if not can_access:
        return redirect("projects")

    lists = board.lists.prefetch_related("cards__assignees", "cards__labels").all()
    members = ProjectMember.objects.filter(project=project).select_related("user")
    labels = project.labels.all()
    all_boards = project.boards.all()

    context = {
        "project": project,
        "board": board,
        "lists": lists,
        "members": members,
        "labels": labels,
        "all_boards": all_boards,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "board/kanban.html", context)


@login_required
@require_POST
def board_create(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    name = request.POST.get("name", "New Board")
    board = Board.objects.create(
        project=project, name=name, position=project.boards.count()
    )
    List.objects.create(board=board, title="To Do / ត្រូវធ្វើ", position=0)
    List.objects.create(board=board, title="Doing / កំពុងធ្វើ", position=1)
    List.objects.create(board=board, title="Done / បានធ្វើ", position=2)
    return redirect("board", project_id=project_id, board_id=board.id)


@login_required
@require_POST
def list_create(request, board_id):
    board = get_object_or_404(Board, id=board_id)
    title = request.POST.get("title", "New List")
    lst = List.objects.create(board=board, title=title, position=board.lists.count())
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"id": lst.id, "title": lst.title})
    return redirect("board", project_id=board.project.id, board_id=board.id)


# ─── CARDS ────────────────────────────────────────────────────────────────────


@login_required
@require_POST
def card_create(request, list_id):
    lst = get_object_or_404(List, id=list_id)
    title = request.POST.get("title", "")
    priority = request.POST.get("priority", "medium")
    deadline = request.POST.get("deadline") or None
    status_map = {
        "To Do / ត្រូវធ្វើ": "todo",
        "Doing / កំពុងធ្វើ": "doing",
        "Done / បានធ្វើ": "done",
    }
    status = status_map.get(lst.title, "todo")
    card = Card.objects.create(
        list=lst,
        created_by=request.user,
        title=title,
        priority=priority,
        deadline=deadline,
        status=status,
        position=lst.cards.count(),
    )
    CardAssignment.objects.get_or_create(card=card, user=request.user)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "id": card.id,
                "title": card.title,
                "priority": card.priority,
                "status": card.status,
                "deadline": str(card.deadline) if card.deadline else "",
                "is_overdue": card.is_overdue,
            }
        )
    return redirect("board", project_id=lst.board.project.id, board_id=lst.board.id)


@login_required
def card_detail(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    project = card.list.board.project
    members = ProjectMember.objects.filter(project=project).select_related("user")
    labels = project.labels.all()
    comments = card.comments.select_related("user").all()
    attachments = card.attachments.all()
    assigned_ids = CardAssignment.objects.filter(card=card).values_list(
        "user_id", flat=True
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "edit":
            card.title = request.POST.get("title", card.title)
            card.description = request.POST.get("description", card.description)
            card.priority = request.POST.get("priority", card.priority)
            card.status = request.POST.get("status", card.status)
            deadline = request.POST.get("deadline")
            card.deadline = deadline if deadline else None
            card.save()
            # Update list based on status
            board = card.list.board
            status_to_title = {
                "todo": "To Do / ត្រូវធ្វើ",
                "doing": "Doing / កំពុងធ្វើ",
                "done": "Done / បានធ្វើ",
            }
            target_title = status_to_title.get(card.status)
            target_list = board.lists.filter(title=target_title).first()
            if target_list:
                card.list = target_list
                card.save()
            messages.success(request, "Card updated!")
        elif action == "comment":
            content = request.POST.get("content", "").strip()
            if content:
                Comment.objects.create(card=card, user=request.user, content=content)
                for assignee in card.assignees.exclude(id=request.user.id):
                    Notification.objects.create(
                        user=assignee,
                        type="comment",
                        message=f'{request.user.username} commented on "{card.title}"',
                        link=f"/cards/{card.id}/",
                    )
        elif action == "assign":
            user_id = request.POST.get("user_id")
            try:
                u = User.objects.get(id=user_id)
                CardAssignment.objects.get_or_create(card=card, user=u)
                Notification.objects.create(
                    user=u,
                    type="assigned",
                    message=f'You were assigned to task "{card.title}"',
                    link=f"/cards/{card.id}/",
                )
                messages.success(request, f"{u.username} assigned!")
            except User.DoesNotExist:
                pass
        elif action == "unassign":
            user_id = request.POST.get("user_id")
            CardAssignment.objects.filter(card=card, user_id=user_id).delete()
        elif action == "attach":
            f = request.FILES.get("file")
            if f:
                Attachment.objects.create(
                    card=card, uploaded_by=request.user, file=f, file_name=f.name
                )
                messages.success(request, "File attached!")
        elif action == "label":
            label_ids = request.POST.getlist("label_ids")
            card.labels.set(label_ids)
        return redirect("card_detail", card_id=card.id)

    context = {
        "card": card,
        "project": project,
        "members": members,
        "labels": labels,
        "comments": comments,
        "attachments": attachments,
        "assigned_ids": list(assigned_ids),
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "board/card_detail.html", context)


@login_required
def card_delete(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    board_id = card.list.board.id
    project_id = card.list.board.project.id
    card.delete()
    messages.success(request, "Card deleted.")
    return redirect("board", project_id=project_id, board_id=board_id)


@login_required
@require_POST
def card_move(request):
    """AJAX: move card to new list and position"""
    data = json.loads(request.body)
    card_id = data.get("card_id")
    list_id = data.get("list_id")
    position = data.get("position", 0)
    try:
        card = Card.objects.get(id=card_id)
        lst = List.objects.get(id=list_id)
        card.list = lst
        card.position = position
        # Update status based on list title
        status_map = {
            "To Do / ត្រូវធ្វើ": "todo",
            "Doing / កំពុងធ្វើ": "doing",
            "Done / បានធ្វើ": "done",
        }
        card.status = status_map.get(lst.title, card.status)
        card.save()
        return JsonResponse({"ok": True, "status": card.status})
    except (Card.DoesNotExist, List.DoesNotExist):
        return JsonResponse({"ok": False}, status=404)


@login_required
def comment_delete(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id, user=request.user)
    card_id = comment.card.id
    comment.delete()
    return redirect("card_detail", card_id=card_id)


# ─── SEARCH ───────────────────────────────────────────────────────────────────


@login_required
def search(request):
    q = request.GET.get("q", "")
    cards = []
    projects = []
    if q:
        user = request.user
        if user.is_admin:
            cards = Card.objects.filter(
                Q(title__icontains=q) | Q(description__icontains=q)
            ).select_related("list__board__project")[:20]
            projects = Project.objects.filter(name__icontains=q)[:10]
        else:
            member_ids = ProjectMember.objects.filter(user=user).values_list(
                "project_id", flat=True
            )
            accessible = Project.objects.filter(Q(owner=user) | Q(id__in=member_ids))
            cards = Card.objects.filter(
                Q(title__icontains=q) | Q(description__icontains=q),
                list__board__project__in=accessible,
            ).select_related("list__board__project")[:20]
            projects = accessible.filter(name__icontains=q)[:10]
    context = {
        "q": q,
        "cards": cards,
        "projects": projects,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "search.html", context)


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────


@login_required
def notifications(request):
    notifs = request.user.notifications.all()[:30]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    context = {
        "notifications": notifs,
        "unread_count": 0,
    }
    return render(request, "notifications.html", context)


@login_required
@require_POST
def notification_read(request, notif_id):
    Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
    return JsonResponse({"ok": True})


# ─── ADMIN VIEWS ──────────────────────────────────────────────────────────────


@login_required
def admin_users(request):
    if not request.user.is_admin:
        return redirect("dashboard")
    users = User.objects.all().order_by("-date_joined")
    q = request.GET.get("q", "")
    if q:
        users = users.filter(Q(username__icontains=q) | Q(email__icontains=q))
    context = {
        "users": users,
        "q": q,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "admin_panel/users.html", context)


@login_required
def admin_create_user(request):
    if not request.user.is_admin:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        first_name = request.POST.get("first_name", "")
        last_name = request.POST.get("last_name", "")
        role = request.POST.get("role", "member")
        if User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" already taken.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, f'Email "{email}" already registered.')
        elif len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        else:
            User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=role,
            )
            messages.success(request, f'User "{username}" created successfully!')
    return redirect("admin_users")


@login_required
def admin_update_user(request, user_id):
    if not request.user.is_admin:
        return redirect("dashboard")
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        role = request.POST.get("role", "member")
        password = request.POST.get("password", "").strip()

        if User.objects.filter(username=username).exclude(id=user_id).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        elif User.objects.filter(email=email).exclude(id=user_id).exists():
            messages.error(request, f'Email "{email}" is already registered.')
        elif password and len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
        else:
            user.username = username
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.role = role
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, f'User "{username}" updated successfully!')
    return redirect("admin_users")


@login_required
def admin_delete_user(request, user_id):
    if not request.user.is_admin:
        return redirect("dashboard")
    if request.user.id == user_id:
        messages.error(request, "You cannot delete your own account.")
        return redirect("admin_users")
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        username = user.username
        user.delete()
        messages.success(request, f'User "{username}" deleted.')
    return redirect("admin_users")


@login_required
def admin_toggle_user(request, user_id):
    if not request.user.is_admin:
        return redirect("dashboard")
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save()
    messages.success(
        request, f"User {'activated' if user.is_active else 'deactivated'}."
    )
    return redirect("admin_users")


@login_required
def admin_reports(request):
    if not request.user.is_admin:
        return redirect("dashboard")
    total_users = User.objects.count()
    total_projects = Project.objects.count()
    total_cards = Card.objects.count()
    done_cards = Card.objects.filter(status="done").count()
    active_projects = Project.objects.filter(status="active").count()
    overdue = [
        c
        for c in Card.objects.exclude(status="done").filter(deadline__isnull=False)
        if c.is_overdue
    ]

    projects_data = []
    for p in Project.objects.all():
        projects_data.append(
            {
                "name": p.name,
                "total": p.total_cards,
                "done": p.done_cards,
                "progress": p.progress,
                "members": p.members.count(),
            }
        )

    context = {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_cards": total_cards,
        "done_cards": done_cards,
        "active_projects": active_projects,
        "overdue_count": len(overdue),
        "projects_data": projects_data,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "admin_panel/reports.html", context)


@login_required
def label_create(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if request.method == "POST":
        name = request.POST.get("name", "")
        color = request.POST.get("color", "#3b82f6")
        Label.objects.create(project=project, name=name, color=color)
    return redirect("project_detail", project_id=project_id)


@login_required
def profile(request):
    user = request.user
    if request.method == "POST":
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        if request.FILES.get("avatar"):
            user.avatar = request.FILES["avatar"]
        new_pass = request.POST.get("new_password", "")
        if new_pass:
            user.set_password(new_pass)
        user.save()
        messages.success(request, "Profile updated!")
        return redirect("profile")
    context = {
        "user": user,
        "unread_count": user.notifications.filter(is_read=False).count(),
    }
    return render(request, "profile.html", context)
