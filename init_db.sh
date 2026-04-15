set -e

until (echo > /dev/tcp/db/5432) 2>/dev/null; do
  sleep 1
done

python main.py
