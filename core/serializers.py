from rest_framework import serializers
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


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "role",
            "is_active",
            "date_joined",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ["username", "email", "password", "first_name", "last_name", "role"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name", "color", "project"]


class ProjectMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source="user", write_only=True
    )

    class Meta:
        model = ProjectMember
        fields = ["id", "user", "user_id", "role", "joined_at"]


class ProjectSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    members_count = serializers.SerializerMethodField()
    total_cards = serializers.IntegerField(read_only=True)
    done_cards = serializers.IntegerField(read_only=True)
    progress = serializers.IntegerField(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "name",
            "description",
            "status",
            "owner",
            "members_count",
            "total_cards",
            "done_cards",
            "progress",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["owner", "created_at", "updated_at"]

    def get_members_count(self, obj):
        return obj.members.count()


class BoardSerializer(serializers.ModelSerializer):
    lists_count = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = [
            "id",
            "name",
            "background",
            "position",
            "project",
            "lists_count",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_lists_count(self, obj):
        return obj.lists.count()


class CardSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    assignees = UserSerializer(many=True, read_only=True)
    labels = LabelSerializer(many=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    comments_count = serializers.SerializerMethodField()
    list_title = serializers.CharField(source="list.title", read_only=True)
    project_name = serializers.CharField(
        source="list.board.project.name", read_only=True
    )

    class Meta:
        model = Card
        fields = [
            "id",
            "title",
            "description",
            "priority",
            "status",
            "deadline",
            "position",
            "list",
            "list_title",
            "project_name",
            "created_by",
            "assignees",
            "labels",
            "is_overdue",
            "comments_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def get_comments_count(self, obj):
        return obj.comments.count()


class ListSerializer(serializers.ModelSerializer):
    cards = CardSerializer(many=True, read_only=True)
    cards_count = serializers.SerializerMethodField()

    class Meta:
        model = List
        fields = [
            "id",
            "title",
            "position",
            "board",
            "cards_count",
            "cards",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def get_cards_count(self, obj):
        return obj.cards.count()


class CommentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "content", "user", "card", "created_at", "updated_at"]
        read_only_fields = ["user", "created_at", "updated_at"]


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Attachment
        fields = [
            "id",
            "file_name",
            "file_url",
            "file",
            "card",
            "uploaded_by",
            "uploaded_at",
        ]
        read_only_fields = ["uploaded_by", "uploaded_at", "file_name"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and request:
            return request.build_absolute_uri(obj.file.url)
        return None

    def create(self, validated_data):
        validated_data["file_name"] = validated_data["file"].name
        return super().create(validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "message", "link", "is_read", "created_at"]
        read_only_fields = ["type", "message", "link", "created_at"]


class CardMoveSerializer(serializers.Serializer):
    list_id = serializers.IntegerField()
    position = serializers.IntegerField(default=0)
