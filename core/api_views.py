from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from django.contrib.auth import authenticate
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import (
    User, Project, ProjectMember, Board, List, Card,
    Label, Comment, Attachment, Notification, CardAssignment
)
from .serializers import (
    UserSerializer, RegisterSerializer, ProjectSerializer, ProjectMemberSerializer,
    BoardSerializer, ListSerializer, CardSerializer, LabelSerializer,
    CommentSerializer, AttachmentSerializer, NotificationSerializer, CardMoveSerializer
)


# ─── AUTH ─────────────────────────────────────────────────────────────────────

class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if user:
            token, _ = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': UserSerializer(user).data
            })
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutAPIView(APIView):
    def post(self, request):
        request.user.auth_token.delete()
        return Response({'message': 'Logged out successfully'})


class MeAPIView(APIView):
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ─── USERS (Admin only) ───────────────────────────────────────────────────────

class UserListAPIView(generics.ListAPIView):
    serializer_class = UserSerializer

    def get_queryset(self):
        if not self.request.user.is_admin:
            return User.objects.filter(id=self.request.user.id)
        q = self.request.query_params.get('q', '')
        qs = User.objects.all()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
        return qs


class UserDetailAPIView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    queryset = User.objects.all()

    def update(self, request, *args, **kwargs):
        if not request.user.is_admin and request.user.pk != kwargs['pk']:
            return Response({'error': 'Permission denied'}, status=403)
        return super().update(request, *args, **kwargs)


# ─── PROJECTS ─────────────────────────────────────────────────────────────────

class ProjectListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_admin:
            qs = Project.objects.all()
        else:
            member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
            qs = Project.objects.filter(Q(owner=user) | Q(id__in=member_ids)).distinct()
        q = self.request.query_params.get('q', '')
        if q:
            qs = qs.filter(name__icontains=q)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        ProjectMember.objects.create(project=project, user=self.request.user, role='owner')
        board = Board.objects.create(project=project, name='Main Board', position=0)
        List.objects.create(board=board, title='To Do / ត្រូវធ្វើ', position=0)
        List.objects.create(board=board, title='Doing / កំពុងធ្វើ', position=1)
        List.objects.create(board=board, title='Done / បានធ្វើ', position=2)


class ProjectDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_admin:
            return Project.objects.all()
        member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
        return Project.objects.filter(Q(owner=user) | Q(id__in=member_ids)).distinct()

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if project.owner != request.user and not request.user.is_admin:
            return Response({'error': 'Only owner can delete'}, status=403)
        return super().destroy(request, *args, **kwargs)


class ProjectMembersAPIView(APIView):
    def get(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        members = ProjectMember.objects.filter(project=project).select_related('user')
        return Response(ProjectMemberSerializer(members, many=True).data)

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        user_id = request.data.get('user_id')
        role = request.data.get('role', 'member')
        try:
            user = User.objects.get(id=user_id)
            member, created = ProjectMember.objects.get_or_create(
                project=project, user=user, defaults={'role': role}
            )
            if not created:
                return Response({'error': 'User already a member'}, status=400)
            Notification.objects.create(
                user=user, type='assigned',
                message=f'You were added to project "{project.name}"',
                link=f'/projects/{project.id}/'
            )
            return Response(ProjectMemberSerializer(member).data, status=201)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

    def delete(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        user_id = request.data.get('user_id')
        ProjectMember.objects.filter(project=project, user_id=user_id).delete()
        return Response(status=204)


# ─── BOARDS ───────────────────────────────────────────────────────────────────

class BoardListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = BoardSerializer

    def get_queryset(self):
        return Board.objects.filter(project_id=self.kwargs['project_id'])

    def perform_create(self, serializer):
        project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        serializer.save(project=project)


class BoardDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = BoardSerializer
    queryset = Board.objects.all()


# ─── LISTS ────────────────────────────────────────────────────────────────────

class ListListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = ListSerializer

    def get_queryset(self):
        return List.objects.filter(board_id=self.kwargs['board_id'])

    def perform_create(self, serializer):
        board = get_object_or_404(Board, pk=self.kwargs['board_id'])
        serializer.save(board=board)


class ListDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ListSerializer
    queryset = List.objects.all()


# ─── CARDS ────────────────────────────────────────────────────────────────────

class CardListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CardSerializer

    def get_queryset(self):
        qs = Card.objects.filter(list_id=self.kwargs['list_id'])
        priority = self.request.query_params.get('priority')
        status_param = self.request.query_params.get('status')
        if priority:
            qs = qs.filter(priority=priority)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        lst = get_object_or_404(List, pk=self.kwargs['list_id'])
        status_map = {'To Do / ត្រូវធ្វើ': 'todo', 'Doing / កំពុងធ្វើ': 'doing', 'Done / បានធ្វើ': 'done'}
        card_status = status_map.get(lst.title, 'todo')
        card = serializer.save(
            list=lst,
            created_by=self.request.user,
            status=card_status,
            position=lst.cards.count()
        )
        CardAssignment.objects.get_or_create(card=card, user=self.request.user)


class CardDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CardSerializer
    queryset = Card.objects.all()


class CardMoveAPIView(APIView):
    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        serializer = CardMoveSerializer(data=request.data)
        if serializer.is_valid():
            lst = get_object_or_404(List, pk=serializer.validated_data['list_id'])
            card.list = lst
            card.position = serializer.validated_data['position']
            status_map = {'To Do / ត្រូវធ្វើ': 'todo', 'Doing / កំពុងធ្វើ': 'doing', 'Done / បានធ្វើ': 'done'}
            card.status = status_map.get(lst.title, card.status)
            card.save()
            return Response(CardSerializer(card).data)
        return Response(serializer.errors, status=400)


class CardAssignAPIView(APIView):
    def post(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        user_id = request.data.get('user_id')
        try:
            user = User.objects.get(id=user_id)
            CardAssignment.objects.get_or_create(card=card, user=user)
            Notification.objects.create(
                user=user, type='assigned',
                message=f'You were assigned to task "{card.title}"',
                link=f'/cards/{card.id}/'
            )
            return Response(CardSerializer(card).data)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

    def delete(self, request, pk):
        card = get_object_or_404(Card, pk=pk)
        user_id = request.data.get('user_id')
        CardAssignment.objects.filter(card=card, user_id=user_id).delete()
        return Response(status=204)


# ─── COMMENTS ─────────────────────────────────────────────────────────────────

class CommentListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(card_id=self.kwargs['card_id'])

    def perform_create(self, serializer):
        card = get_object_or_404(Card, pk=self.kwargs['card_id'])
        comment = serializer.save(user=self.request.user, card=card)
        for assignee in card.assignees.exclude(id=self.request.user.id):
            Notification.objects.create(
                user=assignee, type='comment',
                message=f'{self.request.user.username} commented on "{card.title}"',
                link=f'/cards/{card.id}/'
            )


class CommentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CommentSerializer

    def get_queryset(self):
        return Comment.objects.filter(user=self.request.user)


# ─── LABELS ───────────────────────────────────────────────────────────────────

class LabelListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = LabelSerializer

    def get_queryset(self):
        return Label.objects.filter(project_id=self.kwargs['project_id'])

    def perform_create(self, serializer):
        project = get_object_or_404(Project, pk=self.kwargs['project_id'])
        serializer.save(project=project)


# ─── ATTACHMENTS ──────────────────────────────────────────────────────────────

class AttachmentListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = AttachmentSerializer

    def get_queryset(self):
        return Attachment.objects.filter(card_id=self.kwargs['card_id'])

    def perform_create(self, serializer):
        card = get_object_or_404(Card, pk=self.kwargs['card_id'])
        serializer.save(uploaded_by=self.request.user, card=card)


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

class NotificationListAPIView(generics.ListAPIView):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)


class NotificationMarkReadAPIView(APIView):
    def post(self, request, pk):
        Notification.objects.filter(id=pk, user=request.user).update(is_read=True)
        return Response({'ok': True})

    def delete(self, request, pk=None):
        Notification.objects.filter(user=request.user).update(is_read=True)
        return Response({'ok': True, 'message': 'All marked as read'})


# ─── SEARCH ───────────────────────────────────────────────────────────────────

class SearchAPIView(APIView):
    def get(self, request):
        q = request.query_params.get('q', '').strip()
        if not q:
            return Response({'cards': [], 'projects': []})

        user = request.user
        if user.is_admin:
            cards = Card.objects.filter(Q(title__icontains=q) | Q(description__icontains=q))[:20]
            projects = Project.objects.filter(name__icontains=q)[:10]
        else:
            member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
            accessible = Project.objects.filter(Q(owner=user) | Q(id__in=member_ids))
            cards = Card.objects.filter(
                Q(title__icontains=q) | Q(description__icontains=q),
                list__board__project__in=accessible
            )[:20]
            projects = accessible.filter(name__icontains=q)[:10]

        return Response({
            'cards': CardSerializer(cards, many=True).data,
            'projects': ProjectSerializer(projects, many=True).data,
        })


# ─── DASHBOARD STATS ──────────────────────────────────────────────────────────

class DashboardAPIView(APIView):
    def get(self, request):
        user = request.user
        my_cards = Card.objects.filter(assignees=user)
        total = my_cards.count()
        done = my_cards.filter(status='done').count()
        doing = my_cards.filter(status='doing').count()
        todo = my_cards.filter(status='todo').count()
        overdue = [c for c in my_cards.exclude(status='done').filter(deadline__isnull=False) if c.is_overdue]

        if user.is_admin:
            projects = Project.objects.all()
        else:
            member_ids = ProjectMember.objects.filter(user=user).values_list('project_id', flat=True)
            projects = Project.objects.filter(Q(owner=user) | Q(id__in=member_ids)).distinct()

        return Response({
            'stats': {
                'total_tasks': total,
                'done': done,
                'doing': doing,
                'todo': todo,
                'overdue': len(overdue),
            },
            'projects': ProjectSerializer(projects[:6], many=True).data,
            'my_tasks': CardSerializer(my_cards.exclude(status='done').order_by('deadline')[:5], many=True).data,
            'unread_notifications': user.notifications.filter(is_read=False).count(),
        })
