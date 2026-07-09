import os
import subprocess


def main():
    port = int(os.environ.get("PORT", 8080))
    subprocess.run(
        [
            "gunicorn", "app:app",
            "--bind", f"0.0.0.0:{port}",
            # --- AI Video reliability fix -------------------------------
            # AIVIDEO_TASKS / _AIVIDEO_DEBUG live in this process's memory,
            # so we MUST stay on a single worker (more workers would each
            # have their own copy of that dict -> polling could land on a
            # worker that never saw the task and 404 "Task tidak ditemukan").
            # Instead we use a threaded worker so one slow request (a big
            # Dropbox upload, a slow Segmind call) can't block the status
            # polling requests behind it.
            "--workers", "1",
            "--worker-class", "gthread",
            "--threads", "8",
            # Gunicorn's default timeout is 30s. Synchronous Dropbox
            # uploads (up to ~90s upload + ~30s temp-link) previously
            # exceeded that, so gunicorn's arbiter SIGKILLed the worker
            # mid-request -> wiped all in-memory task state and dropped
            # any concurrent polling connections (this is what produced
            # "Gagal mengambil status task dari server" even though
            # Segmind had already finished successfully). 180s gives a
            # safe margin above the slowest legitimate blocking call.
            "--timeout", "180",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
