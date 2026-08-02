from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.workspace, name="workspace"),
    path("hub/", views.hub, name="hub"),
    path("models/", views.models_page, name="models"),
    path("data-pools/", views.data_pools, name="data_pools"),
    path("data-pools/<int:pool_id>/", views.data_pool_detail, name="data_pool_detail"),
    path("logs/", views.placeholder, {"page": "logs"}, name="logs"),
    path("api/jobs/", views.api_create_job, name="api_create_job"),
    path("api/jobs/<int:job_id>/", views.api_job_status, name="api_job_status"),
    path("api/jobs/<int:job_id>/rerun/", views.api_rerun_job, name="api_rerun_job"),
    path("api/jobs/<int:job_id>/store/", views.api_store_pool, name="api_store_pool"),
    path("api/queue/", views.api_queue, name="api_queue"),
]