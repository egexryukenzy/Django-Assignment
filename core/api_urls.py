from django.urls import path
from . import api_views

urlpatterns = [
    # ── Auth
    path('auth/register/',  api_views.RegisterAPIView.as_view(),  name='api_register'),
    path('auth/login/',     api_views.LoginAPIView.as_view(),     name='api_login'),
    path('auth/logout/',    api_views.LogoutAPIView.as_view(),    name='api_logout'),
    path('auth/me/',        api_views.MeAPIView.as_view(),        name='api_me'),

    # ── Dashboard
    path('dashboard/',      api_views.DashboardAPIView.as_view(), name='api_dashboard'),

    # ── Search
    path('search/',         api_views.SearchAPIView.as_view(),    name='api_search'),

    # ── Users
    path('users/',          api_views.UserListAPIView.as_view(),       name='api_users'),
    path('users/<int:pk>/', api_views.UserDetailAPIView.as_view(),     name='api_user_detail'),

    # ── Projects
    path('projects/',              api_views.ProjectListCreateAPIView.as_view(), name='api_projects'),
    path('projects/<int:pk>/',     api_views.ProjectDetailAPIView.as_view(),     name='api_project_detail'),
    path('projects/<int:pk>/members/', api_views.ProjectMembersAPIView.as_view(), name='api_project_members'),
    path('projects/<int:project_id>/boards/',  api_views.BoardListCreateAPIView.as_view(), name='api_boards'),
    path('projects/<int:project_id>/labels/',  api_views.LabelListCreateAPIView.as_view(), name='api_labels'),

    # ── Boards
    path('boards/<int:pk>/',                 api_views.BoardDetailAPIView.as_view(),     name='api_board_detail'),
    path('boards/<int:board_id>/lists/',     api_views.ListListCreateAPIView.as_view(),  name='api_lists'),

    # ── Lists
    path('lists/<int:pk>/',                  api_views.ListDetailAPIView.as_view(),      name='api_list_detail'),
    path('lists/<int:list_id>/cards/',       api_views.CardListCreateAPIView.as_view(),  name='api_cards'),

    # ── Cards
    path('cards/<int:pk>/',                  api_views.CardDetailAPIView.as_view(),      name='api_card_detail'),
    path('cards/<int:pk>/move/',             api_views.CardMoveAPIView.as_view(),        name='api_card_move'),
    path('cards/<int:pk>/assign/',           api_views.CardAssignAPIView.as_view(),      name='api_card_assign'),
    path('cards/<int:card_id>/comments/',    api_views.CommentListCreateAPIView.as_view(), name='api_comments'),
    path('cards/<int:card_id>/attachments/', api_views.AttachmentListCreateAPIView.as_view(), name='api_attachments'),

    # ── Comments
    path('comments/<int:pk>/',              api_views.CommentDetailAPIView.as_view(),    name='api_comment_detail'),

    # ── Notifications
    path('notifications/',                   api_views.NotificationListAPIView.as_view(),         name='api_notifications'),
    path('notifications/read-all/',          api_views.NotificationMarkReadAPIView.as_view(),      name='api_notif_read_all'),
    path('notifications/<int:pk>/read/',     api_views.NotificationMarkReadAPIView.as_view(),      name='api_notif_read'),
]
