"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from video_viewer import views
from video_viewer.views_gallery import gallery_dl_page
from video_viewer.views_youtube import youtube_callback, youtube_connect, youtube_disconnect, youtube_publish

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('collections/', views.collection_list, name='collection_list'),
    path('collections/<uuid:collection_id>/', views.collection_detail, name='collection_detail'),
    path('jobs/<uuid:job_id>/', views.refresh_job_status, name='job_status'),
    path('api/v1/', include('video_viewer.api.urls')),
    path('gallery-dl/', gallery_dl_page, name='gallery_dl'),
    path('youtube/connect/', youtube_connect, name='youtube_connect'),
    path('youtube/callback/', youtube_callback, name='youtube_callback'),
    path('youtube/disconnect/', youtube_disconnect, name='youtube_disconnect'),
    path('youtube/publish/', youtube_publish, name='youtube_publish'),
]
