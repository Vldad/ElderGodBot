import subprocess
import sys
from datetime import datetime
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_file = f"out/output_{timestamp}.txt"
error_file = f"out/error_{timestamp}.txt"

print(f"Starting bot...")
print(f"Output: {output_file}")
print(f"Errors: {error_file}")

with open(output_file, 'w') as out, open(error_file, 'w') as err:
    subprocess.run([sys.executable, "-u", "egb.py"], stdout=out, stderr=err)