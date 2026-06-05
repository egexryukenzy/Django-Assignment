from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Prefetch, Q
from django.views.decorators.http import require_POST
from django.utils import timezone
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


def is_project_leader(user, project):
    if not user.is_authenticated:
        return False
    return (
        user.is_admin
        or project.owner_id == user.id
        or ProjectMember.objects.filter(project=project, user=user, role="owner").exists()
    )


def can_access_project(user, project):
    if not user.is_authenticated:
        return False
    return (
        user.is_admin
        or project.owner_id == user.id
        or ProjectMember.objects.filter(project=project, user=user).exists()
    )


def list_status(lst):
    title = lst.title.lower()
    if title.startswith("doing"):
        return "doing"
    if title.startswith("done"):
        return "done"
    if title.startswith("to do") or title.startswith("todo"):
        return "todo"
    return None


def get_status_list(board, status):
    prefixes = {
        "todo": ("to do", "todo"),
        "doing": ("doing",),
        "done": ("done",),
    }[status]
    for lst in board.lists.all():
        title = lst.title.lower()
        if any(title.startswith(prefix) for prefix in prefixes):
            return lst
    return None


def move_card_to_status(card, status):
    target_list = get_status_list(card.list.board, status)
    if not target_list:
        return False
    card.list = target_list
    card.status = status
    card.position = target_list.cards.count()
    card.save()
    return True


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

    if user.is_admin:
        projects = Project.objects.all()
    else:
        member_ids = ProjectMember.objects.filter(user=user).values_list(
            "project_id", flat=True
        )
        projects = Project.objects.filter(
            Q(owner=user) | Q(id__in=member_ids)
        ).distinct()

    projects = projects.order_by("-created_at")
    total_projects = projects.count()

    completed_projects = projects.filter(status="completed").count()
    active_projects = projects.filter(status="active").count()

    cards = Card.objects.filter(list__board__project__in=projects).distinct()

    total_tasks = cards.count()
    done_tasks = cards.filter(status="done").count()
    doing_tasks = cards.filter(status="doing").count()
    todo_tasks = cards.filter(status="todo").count()

    my_cards = (
        cards.filter(assignees=user).exclude(status="done").order_by("deadline")[:5]
    )
    completed_cards = cards.filter(assignees=user, status="done").order_by("-updated_at")[:5]

    overdue_cards = [c for c in my_cards if c.is_overdue]

    notifications = user.notifications.filter(is_read=False).order_by("-created_at")[:5]
    unread_count = user.notifications.filter(is_read=False).count()

    context = {
        "projects": projects[:6],
        "completed_projects": completed_projects,
        "active_projects": active_projects,
        "total_tasks": total_tasks,
        "done_tasks": done_tasks,
        "doing_tasks": doing_tasks,
        "todo_tasks": todo_tasks,
        "total_projects": total_projects,
        "my_cards": my_cards,
        "completed_cards": completed_cards,
        "overdue_cards": overdue_cards,
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(request, "dashboard.html", context)


@login_required
def project_api_crud(request):
    if not (request.user.is_admin or request.user.is_staff or request.user.is_superuser):
        return redirect("dashboard")
    from .models import AccessToken

    access_token = AccessToken.objects.filter(
        is_active=True,
        expire_date__gte=timezone.now().date(),
    ).order_by("-id").first()

    return render(
        request,
        "PostAPIProject.html",
        {
            "api_access_token": access_token.token if access_token else "",
            "unread_count": request.user.notifications.filter(is_read=False).count(),
        },
    )


@login_required
def board_api_crud(request):
    if not (request.user.is_admin or request.user.is_staff or request.user.is_superuser):
        return redirect("dashboard")
    from .models import AccessToken

    access_token = AccessToken.objects.filter(
        is_active=True,
        expire_date__gte=timezone.now().date(),
    ).order_by("-id").first()

    return render(
        request,
        "PostAPIBoard.html",
        {
            "api_access_token": access_token.token if access_token else "",
            "unread_count": request.user.notifications.filter(is_read=False).count(),
        },
    )


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
        deadline = request.POST.get("deadline") or None
        project = Project.objects.create(
            owner=request.user, name=name, description=description, deadline=deadline
        )
        ProjectMember.objects.create(project=project, user=request.user, role="owner")
        board = Board.objects.create(project=project, name="Main Board", position=0)
        List.objects.create(board=board, title="To Do", position=0)
        List.objects.create(board=board, title="Doing", position=1)
        List.objects.create(board=board, title="Done", position=2)
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
    if not can_access_project(request.user, project):
        messages.error(request, "Access denied")
        return redirect("projects")

    members = ProjectMember.objects.filter(project=project).select_related("user")
    boards = project.boards.all()
    member_user_ids = members.values_list("user_id", flat=True)
    all_users = User.objects.filter(is_active=True).exclude(id__in=member_user_ids)
    can_lead = is_project_leader(request.user, project)
    context = {
        "project": project,
        "members": members,
        "boards": boards,
        "all_users": all_users,
        "can_lead": can_lead,
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
        project.deadline = request.POST.get("deadline") or None
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
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("project_detail", project_id=project_id)

    user_id = request.POST.get("user_id")
    role = request.POST.get("role", "member")
    if role == "owner":
        role = "member"
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
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("project_detail", project_id=project_id)
    if user_id == project.owner_id:
        messages.error(request, "Project owner cannot be removed.")
        return redirect("project_detail", project_id=project_id)
    ProjectMember.objects.filter(project=project, user_id=user_id).delete()
    messages.success(request, "Member removed.")
    return redirect("project_detail", project_id=project_id)

@login_required
def board_view(request, project_id, board_id):
    project = get_object_or_404(Project, id=project_id)
    board = get_object_or_404(Board, id=board_id, project=project)
    if not can_access_project(request.user, project):
        return redirect("projects")

    can_lead = is_project_leader(request.user, project)
    visible_cards = Card.objects.prefetch_related("assignees", "labels")
    if not can_lead:
        visible_cards = visible_cards.filter(Q(assignees=request.user) | Q(status="todo")).distinct()
    lists = list(
        board.lists.prefetch_related(
            Prefetch("cards", queryset=visible_cards, to_attr="visible_cards")
        ).all()
    )
    for lst in lists:
        lst.can_add_card = can_lead and list_status(lst) == "todo"
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
        "can_lead": can_lead,
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "board/kanban.html", context)

@login_required
@require_POST
def board_create(request, project_id):
    project = get_object_or_404(Project, id=project_id)
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("project_detail", project_id=project_id)
    name = request.POST.get("name", "New Board")
    board = Board.objects.create(
        project=project, name=name, position=project.boards.count()
    )
    List.objects.create(board=board, title="To Do", position=0)
    List.objects.create(board=board, title="Doing", position=1)
    List.objects.create(board=board, title="Done", position=2)
    return redirect("board", project_id=project_id, board_id=board.id)

@login_required
@require_POST
def project_complete(request, project_id, board_id):
    project = get_object_or_404(Project, id=project_id)
    board = get_object_or_404(Board, id=board_id, project=project)
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("board", project_id=project.id, board_id=board.id)
    project.status = "completed"
    project.save(update_fields=["status", "updated_at"])
    messages.success(request, f'Project "{project.name}" completed!')
    return redirect("dashboard")

@login_required
@require_POST
def list_create(request, board_id):
    board = get_object_or_404(Board, id=board_id)
    if not is_project_leader(request.user, board.project):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Permission denied"}, status=403)
        messages.error(request, "Permission denied")
        return redirect("board", project_id=board.project.id, board_id=board.id)
    title = request.POST.get("title", "New List")
    lst = List.objects.create(board=board, title=title, position=board.lists.count())
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"id": lst.id, "title": lst.title})
    return redirect("board", project_id=board.project.id, board_id=board.id)

@login_required
@require_POST
def card_create(request, list_id):
    lst = get_object_or_404(List, id=list_id)
    project = lst.board.project
    if not is_project_leader(request.user, project):
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Permission denied"}, status=403)
        messages.error(request, "Permission denied")
        return redirect("board", project_id=project.id, board_id=lst.board.id)
    if list_status(lst) != "todo":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": "Cards can only be added to To Do"}, status=400)
        messages.error(request, "Cards can only be added to To Do.")
        return redirect("board", project_id=project.id, board_id=lst.board.id)

    title = request.POST.get("title", "").strip()
    priority = request.POST.get("priority", "medium")
    deadline = request.POST.get("deadline") or None
    card = Card.objects.create(
        list=lst,
        created_by=request.user,
        title=title,
        priority=priority,
        deadline=deadline,
        status="todo",
        position=lst.cards.count(),
    )
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
    return redirect("board", project_id=project.id, board_id=lst.board.id)

@login_required
def card_detail(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    project = card.list.board.project
    can_lead = is_project_leader(request.user, project)
    is_assigned = CardAssignment.objects.filter(card=card, user=request.user).exists()
    can_choose_open_work = card.status == "todo" and can_access_project(request.user, project)
    if not can_access_project(request.user, project) or (not can_lead and not is_assigned and not can_choose_open_work):
        messages.error(request, "Access denied")
        return redirect("projects")

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
            if not can_lead:
                messages.error(request, "Permission denied")
                return redirect("card_detail", card_id=card.id)
            card.title = request.POST.get("title", card.title)
            card.description = request.POST.get("description", card.description)
            card.priority = request.POST.get("priority", card.priority)
            next_status = request.POST.get("status", card.status)
            deadline = request.POST.get("deadline")
            card.deadline = deadline if deadline else None
            if next_status in dict(Card.STATUS_CHOICES):
                card.status = next_status
            card.save()
            move_card_to_status(card, card.status)
            messages.success(request, "Card updated!")
        elif action == "choose_work":
            if can_choose_open_work:
                CardAssignment.objects.get_or_create(card=card, user=request.user)
                move_card_to_status(card, "doing")
                messages.success(request, "Task moved to Doing.")
                return redirect("board", project_id=project.id, board_id=card.list.board.id)
            else:
                messages.error(request, "You cannot choose this task.")
        elif action == "mark_done":
            if is_assigned and card.status == "doing":
                move_card_to_status(card, "done")
                messages.success(request, "Task marked done.")
                return redirect("board", project_id=project.id, board_id=card.list.board.id)
            else:
                messages.error(request, "You cannot mark this task done.")
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
            if not can_lead:
                messages.error(request, "Permission denied")
                return redirect("card_detail", card_id=card.id)
            user_id = request.POST.get("user_id")
            try:
                u = User.objects.get(id=user_id)
                if not ProjectMember.objects.filter(project=project, user=u).exists():
                    messages.error(request, "User must be a project member first.")
                else:
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
            if not can_lead:
                messages.error(request, "Permission denied")
                return redirect("card_detail", card_id=card.id)
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
            if not can_lead:
                messages.error(request, "Permission denied")
                return redirect("card_detail", card_id=card.id)
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
        "can_lead": can_lead,
        "is_assigned": is_assigned,
        "can_choose_work": can_choose_open_work,
        "can_mark_done": is_assigned and card.status == "doing",
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    return render(request, "board/card_detail.html", context)

@login_required
def card_delete(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    board_id = card.list.board.id
    project = card.list.board.project
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("card_detail", card_id=card.id)
    project_id = project.id
    card.delete()
    messages.success(request, "Card deleted.")
    return redirect("board", project_id=project_id, board_id=board_id)

@login_required
@require_POST
def card_move(request):
    data = json.loads(request.body)
    card_id = data.get("card_id")
    list_id = data.get("list_id")
    position = data.get("position", 0)
    try:
        card = Card.objects.get(id=card_id)
        lst = List.objects.get(id=list_id)
        if lst.board_id != card.list.board_id:
            return JsonResponse({"ok": False, "error": "Invalid list"}, status=400)
        if not is_project_leader(request.user, card.list.board.project):
            return JsonResponse({"ok": False, "error": "Permission denied"}, status=403)
        card.list = lst
        card.position = position
        status = list_status(lst)
        if status:
            card.status = status
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


@login_required
def notifications_poll(request):
    after_id = request.GET.get("after", "0")
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    new_notifs = (
        request.user.notifications.filter(id__gt=after_id)
        .order_by("id")
        .values("id", "type", "message", "link", "is_read")[:10]
    )
    latest_id = (
        request.user.notifications.order_by("-id")
        .values_list("id", flat=True)
        .first()
        or after_id
    )

    return JsonResponse(
        {
            "unread_count": request.user.notifications.filter(is_read=False).count(),
            "latest_id": latest_id,
            "new": list(new_notifs),
        }
    )


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
    if not is_project_leader(request.user, project):
        messages.error(request, "Permission denied")
        return redirect("project_detail", project_id=project_id)
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

@login_required
def member_api_docs(request):
    api_sections = [
        {
            'title': 'Projects',
            'icon': 'folder-open',
            'endpoints': [
                {'method': 'GET', 'url': '/api/v1/projects/',              'desc': 'List your accessible projects'},
                {'method': 'GET', 'url': '/api/v1/projects/<id>/',         'desc': 'Get project detail'},
                {'method': 'GET', 'url': '/api/v1/projects/<id>/members/', 'desc': 'List project members'},
                {'method': 'GET', 'url': '/api/v1/projects/<id>/boards/',  'desc': 'List boards in project'},
                {'method': 'GET', 'url': '/api/v1/projects/<id>/labels/',  'desc': 'List labels in project'},
            ]
        },
        {
            'title': 'Boards',
            'icon': 'table-columns',
            'endpoints': [
                {'method': 'GET', 'url': '/api/v1/boards/<id>/',       'desc': 'Get board detail'},
                {'method': 'GET', 'url': '/api/v1/boards/<id>/lists/', 'desc': 'List all lists in board'},
                {'method': 'GET', 'url': '/api/v1/lists/<id>/',        'desc': 'Get list detail'},
            ]
        },
        {
            'title': 'Cards',
            'icon': 'square-check',
            'endpoints': [
                {'method': 'GET', 'url': '/api/v1/lists/<id>/cards/',       'desc': 'Get all cards in list'},
                {'method': 'GET', 'url': '/api/v1/cards/<id>/',             'desc': 'Get card detail'},
                {'method': 'GET', 'url': '/api/v1/cards/<id>/comments/',    'desc': 'Get comments on card'},
                {'method': 'GET', 'url': '/api/v1/cards/<id>/attachments/', 'desc': 'Get attachments on card'},
            ]
        },
    ]

    return render(request, 'admin_panel/api_docs.html', {
        'docs_title': 'Member API Documentation',
        'api_sections': api_sections,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


@login_required
def admin_api_docs(request):
    if not request.user.is_admin:
        return redirect('dashboard')

    api_sections = [
        {
            'title': 'Auth',
            'icon': 'lock',
            'endpoints': [
                {'method': 'POST',  'url': '/api/v1/auth/register/', 'desc': 'Register a new user'},
                {'method': 'POST',  'url': '/api/v1/auth/login/',    'desc': 'Login and get token'},
                {'method': 'POST',  'url': '/api/v1/auth/logout/',   'desc': 'Logout (delete token)'},
                {'method': 'GET',   'url': '/api/v1/auth/me/',       'desc': 'Get current user info'},
                {'method': 'PATCH', 'url': '/api/v1/auth/me/',       'desc': 'Update current user info'},
            ]
        },
        {
            'title': 'Users',
            'icon': 'users',
            'endpoints': [
                {'method': 'GET',   'url': '/api/v1/users/',      'desc': 'List all users (admin only)'},
                {'method': 'GET',   'url': '/api/v1/users/<id>/', 'desc': 'Get user detail'},
                {'method': 'PATCH', 'url': '/api/v1/users/<id>/', 'desc': 'Update user'},
            ]
        },
        {
            'title': 'Projects',
            'icon': 'folder-open',
            'endpoints': [
                {'method': 'GET',    'url': '/api/v1/projects/',              'desc': 'List all accessible projects'},
                {'method': 'POST',   'url': '/api/v1/projects/',              'desc': 'Create a new project'},
                {'method': 'GET',    'url': '/api/v1/projects/<id>/',         'desc': 'Get project detail'},
                {'method': 'PUT',    'url': '/api/v1/projects/<id>/',         'desc': 'Update project'},
                {'method': 'DELETE', 'url': '/api/v1/projects/<id>/',         'desc': 'Delete project'},
                {'method': 'GET',    'url': '/api/v1/projects/<id>/members/', 'desc': 'List project members'},
                {'method': 'POST',   'url': '/api/v1/projects/<id>/members/', 'desc': 'Add member to project'},
                {'method': 'DELETE', 'url': '/api/v1/projects/<id>/members/', 'desc': 'Remove member from project'},
                {'method': 'GET',    'url': '/api/v1/projects/<id>/boards/',  'desc': 'List boards in project'},
                {'method': 'POST',   'url': '/api/v1/projects/<id>/boards/',  'desc': 'Create board in project'},
                {'method': 'GET',    'url': '/api/v1/projects/<id>/labels/',  'desc': 'List labels in project'},
                {'method': 'POST',   'url': '/api/v1/projects/<id>/labels/',  'desc': 'Create label in project'},
            ]
        },
        {
            'title': 'Boards',
            'icon': 'table-columns',
            'endpoints': [
                {'method': 'GET',    'url': '/api/v1/boards/<id>/',       'desc': 'Get board detail'},
                {'method': 'PUT',    'url': '/api/v1/boards/<id>/',       'desc': 'Update board'},
                {'method': 'DELETE', 'url': '/api/v1/boards/<id>/',       'desc': 'Delete board'},
                {'method': 'GET',    'url': '/api/v1/boards/<id>/lists/', 'desc': 'List all lists in board'},
                {'method': 'POST',   'url': '/api/v1/boards/<id>/lists/', 'desc': 'Create list in board'},
            ]
        },
        {
            'title': 'Lists',
            'icon': 'list',
            'endpoints': [
                {'method': 'GET',    'url': '/api/v1/lists/<id>/',       'desc': 'Get list detail'},
                {'method': 'PUT',    'url': '/api/v1/lists/<id>/',       'desc': 'Update list'},
                {'method': 'DELETE', 'url': '/api/v1/lists/<id>/',       'desc': 'Delete list'},
                {'method': 'GET',    'url': '/api/v1/lists/<id>/cards/', 'desc': 'Get all cards in list'},
            ]
        },
        {
            'title': 'Cards',
            'icon': 'square-check',
            'endpoints': [
                {'method': 'POST',   'url': '/api/v1/cards/',                  'desc': 'Create card'},
                {'method': 'GET',    'url': '/api/v1/cards/<id>/',             'desc': 'Get card detail'},
                {'method': 'PUT',    'url': '/api/v1/cards/<id>/',             'desc': 'Update card'},
                {'method': 'DELETE', 'url': '/api/v1/cards/<id>/',             'desc': 'Delete card'},
                {'method': 'POST',   'url': '/api/v1/cards/<id>/move/',        'desc': 'Move card to another list'},
                {'method': 'POST',   'url': '/api/v1/cards/<id>/assign/',      'desc': 'Assign user to card'},
                {'method': 'DELETE', 'url': '/api/v1/cards/<id>/assign/',      'desc': 'Unassign user from card'},
                {'method': 'GET',    'url': '/api/v1/cards/<id>/comments/',    'desc': 'Get comments on card'},
                {'method': 'POST',   'url': '/api/v1/cards/<id>/comments/',    'desc': 'Add comment to card'},
                {'method': 'GET',    'url': '/api/v1/cards/<id>/attachments/', 'desc': 'Get attachments on card'},
                {'method': 'POST',   'url': '/api/v1/cards/<id>/attachments/', 'desc': 'Upload attachment to card'},
            ]
        },
        {
            'title': 'Comments',
            'icon': 'comments',
            'endpoints': [
                {'method': 'GET',    'url': '/api/v1/comments/<id>/', 'desc': 'Get comment detail'},
                {'method': 'PUT',    'url': '/api/v1/comments/<id>/', 'desc': 'Edit comment'},
                {'method': 'DELETE', 'url': '/api/v1/comments/<id>/', 'desc': 'Delete comment'},
            ]
        },
        {
            'title': 'Notifications',
            'icon': 'bell',
            'endpoints': [
                {'method': 'GET',   'url': '/api/v1/notifications/',           'desc': 'List all notifications'},
                {'method': 'POST',  'url': '/api/v1/notifications/<id>/read/', 'desc': 'Mark notification as read'},
                {'method': 'DELETE','url': '/api/v1/notifications/read-all/', 'desc': 'Mark all as read'},
            ]
        },
        {
            'title': 'Search & Dashboard',
            'icon': 'chart-pie',
            'endpoints': [
                {'method': 'GET', 'url': '/api/v1/search/?q=<query>', 'desc': 'Search cards and projects'},
                {'method': 'GET', 'url': '/api/v1/dashboard/',        'desc': 'Get dashboard stats & tasks'},
            ]
        },
    ]

    return render(request, 'admin_panel/api_docs.html', {
        'api_sections': api_sections,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


# ─── Label Edit / Delete ──────────────────────────────────────────────────────

@login_required
def label_edit(request, label_id):
    label = get_object_or_404(Label, id=label_id)
    project = label.project
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can edit labels.")
        return redirect('project_detail', project_id=project.id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        color = request.POST.get('color', label.color)
        if name:
            label.name = name
            label.color = color
            label.save()
            messages.success(request, "Label updated.")
    return redirect('project_detail', project_id=project.id)


@login_required
def label_delete(request, label_id):
    label = get_object_or_404(Label, id=label_id)
    project = label.project
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can delete labels.")
        return redirect('project_detail', project_id=project.id)
    if request.method == 'POST':
        label.delete()
        messages.success(request, "Label deleted.")
    return redirect('project_detail', project_id=project.id)


# ─── Board Edit / Delete ──────────────────────────────────────────────────────

@login_required
def board_edit(request, project_id, board_id):
    project = get_object_or_404(Project, id=project_id)
    board = get_object_or_404(Board, id=board_id, project=project)
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can edit boards.")
        return redirect('project_detail', project_id=project_id)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            board.name = name
            board.save()
            messages.success(request, "Board updated.")
    return redirect('project_detail', project_id=project_id)


@login_required
def board_delete(request, project_id, board_id):
    project = get_object_or_404(Project, id=project_id)
    board = get_object_or_404(Board, id=board_id, project=project)
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can delete boards.")
        return redirect('project_detail', project_id=project_id)
    if request.method == 'POST':
        if project.boards.count() <= 1:
            messages.error(request, "Cannot delete the last board.")
            return redirect('project_detail', project_id=project_id)
        board.delete()
        messages.success(request, "Board deleted.")
    return redirect('project_detail', project_id=project_id)


# ─── List Edit / Delete ───────────────────────────────────────────────────────

@login_required
def list_edit(request, list_id):
    lst = get_object_or_404(List, id=list_id)
    board = lst.board
    project = board.project
    if not can_access_project(request.user, project):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        if name:
            lst.title = name
            lst.save()
            messages.success(request, "List renamed.")
    return redirect('board', project_id=project.id, board_id=board.id)


@login_required
def list_delete(request, list_id):
    lst = get_object_or_404(List, id=list_id)
    board = lst.board
    project = board.project
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can delete lists.")
        return redirect('board', project_id=project.id, board_id=board.id)
    if request.method == 'POST':
        if board.lists.count() <= 1:
            messages.error(request, "Cannot delete the last list.")
            return redirect('board', project_id=project.id, board_id=board.id)
        lst.delete()
        messages.success(request, "List deleted.")
    return redirect('board', project_id=project.id, board_id=board.id)


# ─── Member Role Update ───────────────────────────────────────────────────────

@login_required
def member_role_update(request, project_id, user_id):
    project = get_object_or_404(Project, id=project_id)
    if not is_project_leader(request.user, project):
        messages.error(request, "Only project leaders can change roles.")
        return redirect('project_detail', project_id=project_id)
    member = get_object_or_404(ProjectMember, project=project, user_id=user_id)
    if request.method == 'POST':
        role = request.POST.get('role', '').strip()
        if role in ['leader', 'member']:
            member.role = role
            member.save()
            messages.success(request, "Member role updated.")
    return redirect('project_detail', project_id=project_id)


# ─── Card Duplicate ───────────────────────────────────────────────────────────

@login_required
def card_duplicate(request, card_id):
    card = get_object_or_404(Card, id=card_id)
    project = card.list.board.project
    if not can_access_project(request.user, project):
        messages.error(request, "Access denied.")
        return redirect('dashboard')
    if request.method == 'POST':
        new_card = Card.objects.create(
            list=card.list,
            title=card.title + ' (Copy)',
            description=card.description,
            priority=card.priority,
            status=card.status,
            deadline=card.deadline,
            created_by=request.user,
        )
        new_card.labels.set(card.labels.all())
        messages.success(request, "Card duplicated.")
        return redirect('board', project_id=project.id, board_id=card.list.board.id)
    return redirect('board', project_id=project.id, board_id=card.list.board.id)


# ─── Admin Access Tokens ──────────────────────────────────────────────────────

@login_required
def admin_access_tokens(request):
    if not request.user.is_staff:
        return redirect('dashboard')
    from .models import AccessToken
    tokens = AccessToken.objects.all().order_by('-id')
    today = timezone.now().date()
    return render(request, 'admin_panel/access_tokens.html', {
        'tokens': tokens,
        'active_count': tokens.filter(is_active=True, expire_date__gte=today).count(),
        'inactive_count': tokens.filter(is_active=False).count(),
        'expired_count': tokens.filter(expire_date__lt=today).count(),
        'today': today,
        'unread_count': request.user.notifications.filter(is_read=False).count(),
    })


@login_required
def admin_create_access_token(request):
    if not request.user.is_staff:
        return redirect('dashboard')
    if request.method == 'POST':
        from .models import AccessToken
        import uuid
        company_name = request.POST.get('company_name', '').strip()
        expire_date = request.POST.get('expire_date', None) or None
        if company_name:
            token_value = uuid.uuid4().hex
            AccessToken.objects.create(
                company_name=company_name,
                token=token_value,
                expire_date=expire_date,
                is_active=True,
            )
            messages.success(request, f"Token created for {company_name}.")
    return redirect('admin_access_tokens')


@login_required
def admin_delete_access_token(request, token_id):
    if not request.user.is_staff:
        return redirect('dashboard')
    from .models import AccessToken
    token = get_object_or_404(AccessToken, id=token_id)
    if request.method == 'POST':
        token.delete()
        messages.success(request, "Token deleted.")
    return redirect('admin_access_tokens')


@login_required
def admin_toggle_access_token(request, token_id):
    if not request.user.is_staff:
        return redirect('dashboard')
    from .models import AccessToken
    token = get_object_or_404(AccessToken, id=token_id)
    if request.method == 'POST':
        token.is_active = not token.is_active
        token.save()
        status = "activated" if token.is_active else "deactivated"
        messages.success(request, f"Token {status}.")
    return redirect('admin_access_tokens')

# ─── REAL-TIME NOTIFICATIONS (SSE) ───────────────────────────────────────────

import time
import json as _json
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET

@login_required
@require_GET
def notifications_stream(request):
    def event_stream(user_id):
        from .models import Notification, User as _User

        seen_ids = set(
            Notification.objects.filter(user_id=user_id).values_list("id", flat=True)
        )
        yield "event: connected\ndata: {}\n\n"

        while True:
            time.sleep(15)
            try:
                user = _User.objects.get(pk=user_id)
            except _User.DoesNotExist:
                break

            unread_count = Notification.objects.filter(user=user, is_read=False).count()
            new_notifs = Notification.objects.filter(user=user).exclude(id__in=seen_ids).order_by("id")

            new_data = []
            for n in new_notifs:
                new_data.append({
                    "id": n.id, "type": n.type,
                    "message": n.message, "link": n.link, "is_read": n.is_read,
                })
                seen_ids.add(n.id)

            payload = _json.dumps({"unread_count": unread_count, "new": new_data})
            yield f"data: {payload}\n\n"

    response = StreamingHttpResponse(event_stream(request.user.pk), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


