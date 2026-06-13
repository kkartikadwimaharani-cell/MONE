import os
import subprocess


def main():
    port = int(os.environ.get("PORT", 8080))
    subprocess.run(
        ["gunicorn", "app:app", "--bind", f"0.0.0.0:{port}"],
        check=True,
    )


if __name__ == "__main__":
    main()
