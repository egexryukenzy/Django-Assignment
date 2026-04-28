from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    path('django-admin/', admin.site.urls),

    # Auth
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),

    # Projects
    path('projects/', views.project_list, name='projects'),
    path('projects/create/', views.project_create, name='project_create'),
    path('projects/<int:project_id>/', views.project_detail, name='project_detail'),
    path('projects/<int:project_id>/edit/', views.project_edit, name='project_edit'),
    path('projects/<int:project_id>/delete/', views.project_delete, name='project_delete'),
    path('projects/<int:project_id>/add-member/', views.project_add_member, name='project_add_member'),
    path('projects/<int:project_id>/remove-member/<int:user_id>/', views.project_remove_member, name='project_remove_member'),
    path('projects/<int:project_id>/labels/', views.label_create, name='label_create'),

    # Boards & Lists
    path('projects/<int:project_id>/boards/<int:board_id>/', views.board_view, name='board'),
    path('projects/<int:project_id>/boards/create/', views.board_create, name='board_create'),
    path('lists/<int:board_id>/create/', views.list_create, name='list_create'),

    # Cards
    path('lists/<int:list_id>/cards/create/', views.card_create, name='card_create'),
    path('cards/<int:card_id>/', views.card_detail, name='card_detail'),
    path('cards/<int:card_id>/delete/', views.card_delete, name='card_delete'),
    path('cards/move/', views.card_move, name='card_move'),
    path('comments/<int:comment_id>/delete/', views.comment_delete, name='comment_delete'),

    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/<int:notif_id>/read/', views.notification_read, name='notification_read'),

    # Search
    path('search/', views.search, name='search'),

    # Admin
    path('admin-panel/users/', views.admin_users, name='admin_users'),
    path('admin-panel/users/create/', views.admin_create_user, name='admin_create_user'),
    path('admin-panel/users/<int:user_id>/update/', views.admin_update_user, name='admin_update_user'),
    path('admin-panel/users/<int:user_id>/delete/', views.admin_delete_user, name='admin_delete_user'),
    path('admin-panel/users/<int:user_id>/toggle/', views.admin_toggle_user, name='admin_toggle_user'),
    path('admin-panel/reports/', views.admin_reports, name='admin_reports'),

    # Profile
    path('profile/', views.profile, name='profile'),

    # REST API
    path('api/v1/', include('core.api_urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
