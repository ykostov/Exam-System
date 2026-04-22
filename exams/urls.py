from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Student
    path('dashboard/', views.dashboard, name='dashboard'),
    path('exam/<str:exam_id>/start/', views.start_exam, name='start_exam'),
    path('attempt/<str:attempt_id>/', views.take_exam, name='take_exam'),
    path('attempt/<str:attempt_id>/submit/', views.submit_exam, name='submit_exam'),
    path('attempt/<str:attempt_id>/result/', views.exam_result, name='exam_result'),

    # Admin
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/exam/create/', views.create_exam, name='create_exam'),
    path('admin-panel/exam/<str:exam_id>/', views.exam_detail, name='exam_detail'),
    path('admin-panel/exam/<str:exam_id>/toggle/', views.toggle_exam, name='toggle_exam'),
    path('admin-panel/reports/', views.reports, name='reports'),
]
