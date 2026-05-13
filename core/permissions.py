from datetime import date
from rest_framework.permissions import BasePermission
from .models import AccessToken

from .utils import is_valid_token

class HasAccessToken(BasePermission):
    def has_permission(self, request, view):
        token = request.headers.get("X-ACCESS-TOKEN") or request.query_params.get("token")
        return token and is_valid_token(token)