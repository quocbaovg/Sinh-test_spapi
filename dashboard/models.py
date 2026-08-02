from django.db import models
from django.utils import timezone


def job_image_path(instance, filename):
    return f"jobs/{instance.job_id}/{filename}"


class GenerationJob(models.Model):
    """Hàng chờ sinh testcase: đề bài + code AC → worker → DeepSeek → Python gen → validate."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Đang chờ"
        WORKER = "worker", "Đang xử lý"
        CALLING_API = "calling_api", "Phân tích đề"
        GEN_SCRIPT = "gen_script", "Chuẩn bị sinh"
        RUNNING_GEN = "running_gen", "Sinh testcase"
        VALIDATING = "validating", "Kiểm chứng"
        DONE = "done", "Hoàn tất"
        NEED_RERUN = "need_rerun", "Cần sinh lại"
        FAILED = "failed", "Lỗi"

    class Language(models.TextChoices):
        PYTHON = "python", "Python"
        CPP = "cpp", "C++"

    problem = models.TextField(blank=True, default="")
    ac_code = models.TextField()
    language = models.CharField(
        max_length=16, choices=Language.choices, default=Language.PYTHON
    )
    testcase_count = models.PositiveSmallIntegerField(default=8)
    ai_model = models.CharField(max_length=64, default="deepseek-v4-flash")
    status = models.CharField(
        max_length=32, choices=Status.choices, default=Status.QUEUED
    )
    attempt = models.PositiveIntegerField(default=1)
    gen_script = models.TextField(blank=True, default="")
    testcases_json = models.TextField(blank=True, default="[]")
    pass_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Job#{self.pk} {self.status}"

    @property
    def pass_rate(self):
        if not self.total_count:
            return 0
        return round(100 * self.pass_count / self.total_count, 1)


class JobImage(models.Model):
    job = models.ForeignKey(
        GenerationJob, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=job_image_path)
    uploaded_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Job#{self.job_id} img#{self.pk}"


class DataPool(models.Model):
    """Bộ testcase đã lưu trữ vào Kho dữ liệu."""

    name = models.CharField(max_length=120)
    job = models.ForeignKey(
        GenerationJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stored_pools",
    )
    language = models.CharField(max_length=16, default="python")
    problem = models.TextField(blank=True, default="")
    ac_code = models.TextField(blank=True, default="")
    testcases_json = models.TextField(default="[]")
    pass_count = models.PositiveIntegerField(default=0)
    total_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def pass_rate(self):
        if not self.total_count:
            return 0
        return round(100 * self.pass_count / self.total_count, 1)
