import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from .models import GenerationJob
from . import worker

PIPELINE = [
    GenerationJob.Status.QUEUED,
    GenerationJob.Status.WORKER,
    GenerationJob.Status.CALLING_API,
    GenerationJob.Status.GEN_SCRIPT,
    GenerationJob.Status.RUNNING_GEN,
    GenerationJob.Status.VALIDATING,
]

STAGE_MSG = {
    GenerationJob.Status.QUEUED: "Đã tiếp nhận yêu cầu — đang chờ xử lý…",
    GenerationJob.Status.WORKER: "Đang chuẩn bị sinh testcase…",
    GenerationJob.Status.CALLING_API: "Đang phân tích đề bài và soạn mã sinh test…",
    GenerationJob.Status.GEN_SCRIPT: "Đã có mã sinh test — chuẩn bị chạy…",
    GenerationJob.Status.RUNNING_GEN: "Đang tạo testcase bằng mã nguồn…",
    GenerationJob.Status.VALIDATING: "Đang kiểm chứng từng testcase với code AC…",
    GenerationJob.Status.DONE: "Hoàn tất — testcase đã được kiểm chứng.",
    GenerationJob.Status.NEED_RERUN: "Một số testcase chưa khớp. Bạn có muốn sinh lại không?",
    GenerationJob.Status.FAILED: "Không hoàn tất được. Vui lòng thử lại.",
}


def workspace(request):
    from . import pool
    from django.conf import settings as dj_settings

    ws = pool.worker_stats()
    kpi = {
        "active_clusters": ws["online"],
        "total_clusters": dj_settings.WORKER_COUNT,
        "cluster_load": int(100 * ws["busy"] / max(1, dj_settings.WORKER_COUNT)),
        "tokens_used": "1,248,560",
        "tokens_limit": "5,000,000",
        "tokens_pct": 25,
        "total_testcases": "12,480",
        "today_testcases": "342",
        "api_latency": "40 ms",
        "api_p99": "118 ms",
    }
    chart_labels = [f"{h:02d}:00" for h in range(24)]
    chart_counts = [
        8, 5, 3, 2, 4, 12, 28, 45, 62, 78, 55, 48,
        70, 92, 85, 74, 98, 110, 88, 64, 42, 30, 22, 15,
    ]
    logs = [
        {"tag": "SINH MÃ", "tag_class": "tag-gen", "time": "14:22:01",
         "text": "DeepSeek tạo 50 testcase cho [Secure-Bank-Login-Flow]"},
        {"tag": "CẬP NHẬT", "tag_class": "tag-upd", "time": "14:18:44",
         "text": "Engine xác thực cập nhật đồ thị phụ thuộc cho Pool-Alpha"},
        {"tag": "XUẤT", "tag_class": "tag-exp", "time": "14:05:12",
         "text": "Xuất 1,200 vector test sang pipeline CI/CD #882"},
        {"tag": "SINH MÃ", "tag_class": "tag-gen", "time": "13:58:30",
         "text": "DeepSeek-V3 sinh bộ biên cho calculate_derivative"},
        {"tag": "CẬP NHẬT", "tag_class": "tag-upd", "time": "13:41:09",
         "text": "Cluster-07 hiệu chỉnh lại baseline độ trễ (p99 → 118ms)"},
    ]
    pools = [
        {"id": "DS-ALPHA-982", "status": "ĐÃ HIỆU CHỈNH", "status_class": "status-ok",
         "records": "402,129", "inference": "1.2ms / tb", "sync": "2 phút trước"},
        {"id": "DS-BETA-441", "status": "ĐANG ĐỒNG BỘ", "status_class": "status-sync",
         "records": "218,004", "inference": "2.8ms / tb", "sync": "vừa xong"},
        {"id": "DS-GAMMA-110", "status": "ĐÃ HIỆU CHỈNH", "status_class": "status-ok",
         "records": "891,552", "inference": "0.9ms / tb", "sync": "8 phút trước"},
        {"id": "DS-DELTA-077", "status": "SUY GIẢM", "status_class": "status-warn",
         "records": "54,301", "inference": "6.4ms / tb", "sync": "21 phút trước"},
    ]
    return render(
        request,
        "dashboard/workspace.html",
        {
            "nav": "workspace",
            "kpi": kpi,
            "logs": logs,
            "pools": pools,
            "chart_labels": json.dumps(chart_labels),
            "chart_counts": json.dumps(chart_counts),
        },
    )


def hub(request):
    from . import pool
    from django.conf import settings as dj_settings

    queue = GenerationJob.objects.all()[:8]
    ws = pool.worker_stats()
    return render(
        request,
        "dashboard/hub.html",
        {
            "nav": "hub",
            "queue": queue,
            "ai_models": worker.ready_models(),
            "worker_total": dj_settings.WORKER_COUNT,
            "worker_online": ws["online"] or dj_settings.WORKER_COUNT,
            "worker_busy": ws["busy"],
            "sample_problem": (
                "Cho hai số nguyên a, b (1 ≤ a, b ≤ 100).\n"
                "In ra tổng a + b.\n\n"
                "Input: một dòng chứa hai số a b\n"
                "Output: một số nguyên — tổng a + b"
            ),
            "sample_ac_python": (
                "a, b = map(int, input().split())\n"
                "print(a + b)\n"
            ),
            "sample_ac_cpp": (
                "#include <bits/stdc++.h>\n"
                "using namespace std;\n"
                "int main() {\n"
                "  long long a, b;\n"
                "  cin >> a >> b;\n"
                "  cout << a + b << \"\\n\";\n"
                "  return 0;\n"
                "}\n"
            ),
        },
    )


def placeholder(request, page):
    titles = {
        "logs": "Nhật ký hệ thống",
    }
    return render(
        request,
        "dashboard/placeholder.html",
        {"nav": page, "title": titles.get(page, page)},
    )


def models_page(request):
    from django.conf import settings as dj_settings

    models = worker.probe_models_status()
    online = sum(1 for m in models if m.get("status") == "online")
    return render(
        request,
        "dashboard/models.html",
        {
            "nav": "models",
            "models": models,
            "online_count": online,
            "total_count": len(models),
            "base_url": getattr(dj_settings, "DEEPSEEK_BASE_URL", ""),
            "has_key": bool(getattr(dj_settings, "DEEPSEEK_API_KEY", "")),
        },
    )


def data_pools(request):
    from .models import DataPool

    pools = DataPool.objects.all()[:50]
    return render(
        request,
        "dashboard/data_pools.html",
        {"nav": "data_pools", "pools": pools},
    )


def data_pool_detail(request, pool_id):
    """Xem lại testcase đã lưu trong một pool."""
    from .models import DataPool

    pool = get_object_or_404(DataPool, pk=pool_id)
    try:
        cases = json.loads(pool.testcases_json or "[]")
    except json.JSONDecodeError:
        cases = []
    return render(
        request,
        "dashboard/data_pool_detail.html",
        {
            "nav": "data_pools",
            "pool": pool,
            "cases": cases,
        },
    )


@require_POST
def api_store_pool(request, job_id):
    """Lưu kết quả job vào Kho dữ liệu."""
    from .models import DataPool

    job = get_object_or_404(GenerationJob, pk=job_id)
    if not job.testcases_json or job.testcases_json == "[]":
        return JsonResponse(
            {"ok": False, "error": "Job chưa có testcase để lưu"}, status=400
        )

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}

    name = (body.get("name") or "").strip()
    if not name:
        name = f"Pool-Job#{job.pk}-{timezone_now_str()}"

    # Tránh lưu trùng cùng job + cùng số test
    existing = DataPool.objects.filter(job=job, total_count=job.total_count).first()
    if existing:
        return JsonResponse({
            "ok": True,
            "already": True,
            "pool": {
                "id": existing.pk,
                "name": existing.name,
                "total_count": existing.total_count,
                "pass_rate": existing.pass_rate,
            },
        })

    pool = DataPool.objects.create(
        name=name,
        job=job,
        language=job.language,
        problem=job.problem,
        ac_code=job.ac_code,
        testcases_json=job.testcases_json,
        pass_count=job.pass_count,
        total_count=job.total_count,
    )
    return JsonResponse({
        "ok": True,
        "already": False,
        "pool": {
            "id": pool.pk,
            "name": pool.name,
            "total_count": pool.total_count,
            "pass_rate": pool.pass_rate,
        },
    })


def timezone_now_str():
    from django.utils import timezone

    return timezone.localtime().strftime("%m%d-%H%M")


def _job_payload(job):
    try:
        cases = json.loads(job.testcases_json or "[]")
    except json.JSONDecodeError:
        cases = []
    return {
        "id": job.pk,
        "status": job.status,
        "status_label": job.get_status_display(),
        "message": job.message or STAGE_MSG.get(job.status, ""),
        "attempt": job.attempt,
        "language": job.language,
        "testcase_count": job.testcase_count,
        "ai_model": job.ai_model,
        "image_count": job.images.count(),
        "images": [img.image.url for img in job.images.all() if img.image],
        "pass_count": job.pass_count,
        "total_count": job.total_count,
        "pass_rate": job.pass_rate,
        "gen_script": job.gen_script,
        "testcases": cases,
        "need_rerun": job.status == GenerationJob.Status.NEED_RERUN,
        "done": job.status in (
            GenerationJob.Status.DONE,
            GenerationJob.Status.NEED_RERUN,
            GenerationJob.Status.FAILED,
        ),
    }


def _fail(job, err: Exception):
    job.status = GenerationJob.Status.FAILED
    job.message = f"Lỗi: {err}"[:250]
    job.save()


def _advance_job(job):
    """Tiến pipeline; gọi DeepSeek / chạy script / validate AC ở các bước tương ứng."""
    if job.status in (
        GenerationJob.Status.DONE,
        GenerationJob.Status.NEED_RERUN,
        GenerationJob.Status.FAILED,
    ):
        return

    try:
        idx = PIPELINE.index(job.status)
    except ValueError:
        job.status = GenerationJob.Status.QUEUED
        job.message = STAGE_MSG[job.status]
        job.save(update_fields=["status", "message", "updated_at"])
        return

    # Bước kế tiếp
    if idx >= len(PIPELINE) - 1:
        # đang VALIDATING → chạy validate rồi kết thúc
        try:
            cases = json.loads(job.testcases_json or "[]")
            results = worker.validate_ac(job.ac_code, cases, language=job.language)
            job.testcases_json = json.dumps(results, ensure_ascii=False)
            job.total_count = len(results)
            job.pass_count = sum(1 for c in results if c.get("ok"))
            if job.pass_count == job.total_count and job.total_count > 0:
                job.status = GenerationJob.Status.DONE
            else:
                job.status = GenerationJob.Status.NEED_RERUN
            job.message = STAGE_MSG[job.status]
            job.save()
        except Exception as e:
            _fail(job, e)
        return

    nxt = PIPELINE[idx + 1]
    job.status = nxt
    job.message = STAGE_MSG[nxt]
    job.save(update_fields=["status", "message", "updated_at"])

    # Side-effects theo stage vừa vào
    try:
        if nxt == GenerationJob.Status.CALLING_API:
            # Gọi API ngay trong bước này (có thể mất vài giây)
            image_paths = [
                img.image.path for img in job.images.all() if img.image
            ]
            script = worker.request_gen_script(
                job.problem,
                job.ac_code,
                attempt=job.attempt,
                testcase_count=job.testcase_count,
                language=job.language,
                ai_model=job.ai_model,
                image_paths=image_paths,
            )
            job.gen_script = script
            job.status = GenerationJob.Status.GEN_SCRIPT
            job.message = STAGE_MSG[GenerationJob.Status.GEN_SCRIPT]
            job.save()

        elif nxt == GenerationJob.Status.RUNNING_GEN:
            cases = worker.run_python_script(job.gen_script)
            job.testcases_json = json.dumps(cases, ensure_ascii=False)
            job.total_count = len(cases)
            job.pass_count = 0
            job.message = f"Đã sinh {len(cases)} testcase — chuẩn bị chạy AC…"
            job.save()

        elif nxt == GenerationJob.Status.VALIDATING:
            cases = json.loads(job.testcases_json or "[]")
            results = worker.validate_ac(job.ac_code, cases, language=job.language)
            job.testcases_json = json.dumps(results, ensure_ascii=False)
            job.total_count = len(results)
            job.pass_count = sum(1 for c in results if c.get("ok"))
            if job.pass_count == job.total_count and job.total_count > 0:
                job.status = GenerationJob.Status.DONE
            else:
                job.status = GenerationJob.Status.NEED_RERUN
            job.message = STAGE_MSG[job.status]
            job.save()

    except Exception as e:
        _fail(job, e)


@require_POST
def api_create_job(request):
    # Hỗ trợ JSON hoặc multipart (khi có ảnh đề)
    if request.content_type and "multipart/form-data" in request.content_type:
        problem = (request.POST.get("problem") or "").strip()
        ac_code = (request.POST.get("ac_code") or "").strip()
        language = (request.POST.get("language") or "python").strip().lower()
        ai_model = (request.POST.get("ai_model") or "deepseek-v4-flash").strip()
        try:
            testcase_count = int(request.POST.get("testcase_count") or 8)
        except (TypeError, ValueError):
            testcase_count = 8
        files = request.FILES.getlist("images")
    else:
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "JSON không hợp lệ"}, status=400)
        problem = (body.get("problem") or "").strip()
        ac_code = (body.get("ac_code") or "").strip()
        language = (body.get("language") or "python").strip().lower()
        ai_model = (body.get("ai_model") or "deepseek-v4-flash").strip()
        try:
            testcase_count = int(body.get("testcase_count") or 8)
        except (TypeError, ValueError):
            testcase_count = 8
        files = []

    if not ac_code:
        return JsonResponse({"ok": False, "error": "Cần nhập code AC"}, status=400)
    if not problem and not files:
        return JsonResponse(
            {"ok": False, "error": "Cần đề bài (text và/hoặc ảnh)"}, status=400
        )

    if language not in worker.ALLOWED_LANGS:
        return JsonResponse(
            {"ok": False, "error": "Chỉ hỗ trợ ngôn ngữ Python hoặc C++"}, status=400
        )

    testcase_count = max(3, min(testcase_count, 30))
    model_ids = {m["id"] for m in worker.ready_models()}
    if ai_model not in model_ids:
        ai_model = "deepseek-v4-flash"

    # Validate ảnh
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    if len(files) > 5:
        return JsonResponse({"ok": False, "error": "Tối đa 5 ảnh đề"}, status=400)
    for f in files:
        if f.content_type not in allowed:
            return JsonResponse(
                {"ok": False, "error": f"Định dạng không hỗ trợ: {f.content_type}"},
                status=400,
            )
        if f.size > 5 * 1024 * 1024:
            return JsonResponse({"ok": False, "error": "Mỗi ảnh tối đa 5MB"}, status=400)

    from .models import JobImage

    job = GenerationJob.objects.create(
        problem=problem,
        ac_code=ac_code,
        language=language,
        testcase_count=testcase_count,
        ai_model=ai_model,
        status=GenerationJob.Status.QUEUED,
        message=STAGE_MSG[GenerationJob.Status.QUEUED],
    )
    for f in files:
        JobImage.objects.create(job=job, image=f)

    return JsonResponse({"ok": True, "job": _job_payload(job)})


@require_GET
def api_job_status(request, job_id):
    job = get_object_or_404(GenerationJob, pk=job_id)
    # Worker pool tự chạy pipeline — poll chỉ đọc trạng thái
    # (tick=1 vẫn hỗ trợ fallback nếu worker chưa start)
    tick = request.GET.get("tick", "0") == "1"
    if tick:
        from . import pool
        if pool.worker_stats()["online"] == 0:
            _advance_job(job)
            job.refresh_from_db()
    return JsonResponse({"ok": True, "job": _job_payload(job)})


@require_POST
def api_rerun_job(request, job_id):
    job = get_object_or_404(GenerationJob, pk=job_id)
    job.attempt += 1
    job.status = GenerationJob.Status.QUEUED
    job.message = f"Chạy lại lần {job.attempt} — vào hàng chờ…"
    job.gen_script = ""
    job.testcases_json = "[]"
    job.pass_count = 0
    job.total_count = 0
    job.save()
    return JsonResponse({"ok": True, "job": _job_payload(job)})


@require_GET
def api_queue(request):
    from . import pool

    jobs = GenerationJob.objects.all()[:12]
    return JsonResponse({
        "ok": True,
        "workers": pool.worker_stats(),
        "queue": [
            {
                "id": j.pk,
                "status": j.status,
                "status_label": j.get_status_display(),
                "attempt": j.attempt,
                "pass_rate": j.pass_rate,
                "created_at": j.created_at.strftime("%H:%M:%S"),
            }
            for j in jobs
        ],
    })
