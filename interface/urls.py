from django.urls import path
from . import views

urlpatterns = [
    path('',views.setDocument),
    path('setquery/',views.setQuery),
    path('getsections/',views.getSections),
    ]