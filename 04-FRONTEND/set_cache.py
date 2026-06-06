import subprocess

gsutil = r'C:\Users\Matth\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gsutil.cmd'

urls = [
    'gs://nfl-frontend-nfl-model-471509/assets/index-DSBzqtcP.js',
    'gs://nfl-frontend-nfl-model-471509/assets/index-BZSIAztk.css',
]

for url in urls:
    r = subprocess.run(
        [gsutil, 'setmeta', '-h', 'Cache-Control:public, max-age=31536000, immutable', url],
        capture_output=True, text=True, shell=True
    )
    print(f"URL: {url}")
    print(f"stdout: {r.stdout}")
    print(f"stderr: {r.stderr}")
    print(f"returncode: {r.returncode}")

print("ALL DONE")
