from rest_framework.permissions import BasePermission

from .utils import is_valid_token


class HasAccessToken(BasePermission):
    message = "A valid admin access token is required."

    def has_permission(self, request, view):
        token = request.headers.get("X-ACCESS-TOKEN") or request.query_params.get("token")
        return bool(token and is_valid_token(token))
