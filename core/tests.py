import json

from django.test import TestCase
from django.urls import reverse

from .models import Board, Card, CardAssignment, List, Project, ProjectMember, User


class BoardLeaderWorkflowTests(TestCase):
    def setUp(self):
        self.leader = User.objects.create_user(username="leader", password="pass123")
        self.member = User.objects.create_user(username="member", password="pass123")
        self.other = User.objects.create_user(username="other", password="pass123")
        self.project = Project.objects.create(owner=self.leader, name="Project")
        ProjectMember.objects.create(project=self.project, user=self.leader, role="owner")
        ProjectMember.objects.create(project=self.project, user=self.member, role="member")
        self.board = Board.objects.create(project=self.project, name="Main Board")
        self.todo = List.objects.create(board=self.board, title="To Do", position=0)
        self.doing = List.objects.create(board=self.board, title="Doing", position=1)
        self.done = List.objects.create(board=self.board, title="Done", position=2)

    def login(self, user):
        self.client.force_login(user)

    def make_card(self, title="Task", status="todo", assignee=None):
        target_list = {"todo": self.todo, "doing": self.doing, "done": self.done}[status]
        card = Card.objects.create(
            list=target_list,
            created_by=self.leader,
            title=title,
            status=status,
            position=target_list.cards.count(),
        )
        if assignee:
            CardAssignment.objects.create(card=card, user=assignee)
        return card

    def test_project_creator_becomes_owner_member(self):
        creator = User.objects.create_user(username="creator", password="pass123")
        self.login(creator)
        response = self.client.post(
            reverse("project_create"),
            {"name": "Created Project", "description": ""},
        )
        project = Project.objects.get(name="Created Project")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(project.owner, creator)
        self.assertTrue(
            ProjectMember.objects.filter(project=project, user=creator, role="owner").exists()
        )

    def test_leader_can_add_members_and_assign_cards(self):
        card = self.make_card()
        self.login(self.leader)

        self.client.post(
            reverse("project_add_member", args=[self.project.id]),
            {"user_id": self.other.id, "role": "member"},
        )
        self.assertTrue(ProjectMember.objects.filter(project=self.project, user=self.other).exists())

        self.client.post(reverse("card_detail", args=[card.id]), {"action": "assign", "user_id": self.member.id})
        self.assertTrue(CardAssignment.objects.filter(card=card, user=self.member).exists())

    def test_leader_submits_project_complete_and_dashboard_count_updates(self):
        self.login(self.leader)

        response = self.client.get(reverse("board", args=[self.project.id, self.board.id]))
        self.assertContains(response, "Submit Project")

        response = self.client.post(
            reverse("project_complete", args=[self.project.id, self.board.id])
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "completed")

        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, '<div class="stat-number">1</div>', html=True)

    def test_member_cannot_submit_project_complete(self):
        self.login(self.member)

        response = self.client.get(reverse("board", args=[self.project.id, self.board.id]))
        self.assertNotContains(response, "Submit Project")

        response = self.client.post(
            reverse("project_complete", args=[self.project.id, self.board.id])
        )
        self.assertRedirects(response, reverse("board", args=[self.project.id, self.board.id]))
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "active")

    def test_member_cannot_manage_board_or_cards(self):
        card = self.make_card(assignee=self.member)
        self.login(self.member)

        self.client.post(
            reverse("project_add_member", args=[self.project.id]),
            {"user_id": self.other.id, "role": "member"},
        )
        self.assertFalse(ProjectMember.objects.filter(project=self.project, user=self.other).exists())

        self.client.post(reverse("card_create", args=[self.todo.id]), {"title": "Blocked"})
        self.assertFalse(Card.objects.filter(title="Blocked").exists())

        self.client.post(reverse("card_detail", args=[card.id]), {"action": "assign", "user_id": self.other.id})
        self.assertFalse(CardAssignment.objects.filter(card=card, user=self.other).exists())

        self.client.post(
            reverse("card_detail", args=[card.id]),
            {"action": "edit", "title": "Changed", "status": "done"},
        )
        card.refresh_from_db()
        self.assertEqual(card.title, "Task")
        self.assertEqual(card.status, "todo")

        self.client.get(reverse("card_delete", args=[card.id]))
        self.assertTrue(Card.objects.filter(id=card.id).exists())

        response = self.client.post(
            reverse("card_move"),
            data=json.dumps({"card_id": card.id, "list_id": self.doing.id, "position": 0}),
            content_type="application/json",
        )
        card.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(card.status, "todo")

    def test_leader_can_create_cards_only_in_todo(self):
        self.login(self.leader)

        self.client.post(reverse("card_create", args=[self.todo.id]), {"title": "Allowed"})
        allowed = Card.objects.get(title="Allowed")
        self.assertEqual(allowed.status, "todo")
        self.assertFalse(CardAssignment.objects.filter(card=allowed, user=self.leader).exists())

        self.client.post(reverse("card_create", args=[self.doing.id]), {"title": "No Doing"})
        self.client.post(reverse("card_create", args=[self.done.id]), {"title": "No Done"})
        self.assertFalse(Card.objects.filter(title="No Doing").exists())
        self.assertFalse(Card.objects.filter(title="No Done").exists())

        response = self.client.get(reverse("board", args=[self.project.id, self.board.id]))
        self.assertContains(response, "Submit")

    def test_member_can_choose_open_todo_card_and_finish_it(self):
        card = self.make_card()
        self.login(self.member)

        response = self.client.get(reverse("card_detail", args=[card.id]))
        self.assertContains(response, "Choose")
        self.assertNotContains(response, "Done</button>")

        response = self.client.post(reverse("card_detail", args=[card.id]), {"action": "choose_work"})
        self.assertRedirects(response, reverse("board", args=[self.project.id, self.board.id]))
        card.refresh_from_db()
        self.assertEqual(card.status, "doing")
        self.assertEqual(card.list, self.doing)
        self.assertTrue(CardAssignment.objects.filter(card=card, user=self.member).exists())

        response = self.client.get(reverse("card_detail", args=[card.id]))
        self.assertContains(response, "Done")
        response = self.client.post(reverse("card_detail", args=[card.id]), {"action": "mark_done"})
        self.assertRedirects(response, reverse("board", args=[self.project.id, self.board.id]))
        card.refresh_from_db()
        self.assertEqual(card.status, "done")
        self.assertEqual(card.list, self.done)

        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Completed Tasks")
        self.assertContains(response, '<div class="stat-number">1</div>', html=True)
        self.assertContains(response, card.title)

    def test_unassigned_member_cannot_mark_doing_card_done(self):
        card = self.make_card(status="doing")
        self.login(self.member)

        self.client.post(reverse("card_detail", args=[card.id]), {"action": "mark_done"})
        card.refresh_from_db()
        self.assertEqual(card.status, "doing")

    def test_member_board_view_shows_assigned_cards_and_open_todo_cards(self):
        assigned = self.make_card(title="Assigned Task", status="doing", assignee=self.member)
        open_todo = self.make_card(title="Open To Do")
        hidden_doing = self.make_card(title="Hidden Doing", status="doing")
        self.login(self.member)

        response = self.client.get(reverse("project_detail", args=[self.project.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add Board")
        response = self.client.get(reverse("board", args=[self.project.id, self.board.id]))

        self.assertContains(response, assigned.title)
        self.assertContains(response, open_todo.title)
        self.assertNotContains(response, hidden_doing.title)
        self.assertNotContains(response, "Add card")
        self.assertNotContains(response, "Add List")
