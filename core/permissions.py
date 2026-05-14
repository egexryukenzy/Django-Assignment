from datetime import date
from rest_framework.permissions import BasePermission
from .models import AccessToken
from .utils import is_valid_token

class HasAccessToken(BasePermission):
    def has_permission(self, request, view):
        # Session-authenticated staff/admin → bypass (browsable API, Django admin)
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return True

        # Otherwise require X-ACCESS-TOKEN header or ?token= query param
        token = request.headers.get("X-ACCESS-TOKEN") or request.query_params.get("token")
        return bool(token and is_valid_token(token))
