from django.urls import path, include

urlpatterns = [
    path('', include('exams.urls')),
]
