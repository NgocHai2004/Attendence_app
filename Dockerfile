FROM python:3.10-bullseye

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 binutils && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python - <<'PY'
import glob
paths = glob.glob('/usr/local/lib/python*/site-packages/onnxruntime/capi/*.so')
if not paths:
    raise SystemExit('onnxruntime shared library not found')
import subprocess
for p in paths:
    print('Fixing execstack for', p)
    subprocess.check_call(['objcopy', '--remove-section', '.note.GNU-stack', p])
PY

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
