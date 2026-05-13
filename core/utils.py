from datetime import date
from django.http import JsonResponse
from .models import AccessToken

def is_valid_token(token):
    try:
        access = AccessToken.objects.get(token=token, is_active=True)
        return access.expire_date >= date.today()
    except AccessToken.DoesNotExist:
        return False
