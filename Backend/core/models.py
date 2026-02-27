from django.db import models
import uuid

class User(models.Model):
    username = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)

    is_verified = models.BooleanField(default=False)

    auth_token = models.UUIDField(default=uuid.uuid4, editable=False)

    def __str__(self):
        return self.email