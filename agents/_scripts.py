import subprocess


def dev():
    subprocess.run(["langgraph", "dev", "--no-browser"], check=True)  # "--no-reload"
