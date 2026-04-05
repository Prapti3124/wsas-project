import subprocess

try:
    out1 = subprocess.check_output(["git", "log", "--oneline", "frontend/index.html"], text=True)
    out2 = subprocess.check_output(["git", "log", "--oneline", "frontend/css/style.css"], text=True)
    
    with open("commit_logs.txt", "w", encoding="utf-8") as f:
        f.write("-- index.html --\n")
        f.write(out1)
        f.write("\n-- style.css --\n")
        f.write(out2)
    print("Logs written to commit_logs.txt successfully.")
except Exception as e:
    print(f"Error: {e}")
