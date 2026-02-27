from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.core.mail import send_mail
from django.conf import settings
from .models import User
from .serializers import UserSerializer


# SIGNUP
@api_view(['POST'])
def signup(request):
    serializer = UserSerializer(data=request.data)

    if serializer.is_valid():
        user = serializer.save()

        verify_link = f"http://127.0.0.1:8000/api/verify/{user.auth_token}/"

        send_mail(
            "Verify your account",
            f"Click to verify: {verify_link}",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
        )

        return Response({"message": "Signup successful. Verify email."})

    return Response(serializer.errors)


# VERIFY EMAIL
@api_view(['GET'])
def verify_email(request, token):
    try:
        user = User.objects.get(auth_token=token)
        user.is_verified = True
        user.save()
        return Response({"message": "Email verified"})
    except User.DoesNotExist:
        return Response({"message": "Invalid token"})


# LOGIN
@api_view(['POST'])
def login(request):
    email = request.data.get('email')
    password = request.data.get('password')

    try:
        user = User.objects.get(email=email, password=password)

        if not user.is_verified:
            return Response({"message": "Please verify your email first"})

        return Response({
            "message": "Login successful",
            "auth_id": str(user.auth_token)
        })

    except User.DoesNotExist:
        return Response({"message": "Invalid email or password"})