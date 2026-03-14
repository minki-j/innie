import subprocess


def dev():
    subprocess.run(["langgraph", "dev", "--no-browser", "--no-reload"], check=True)
