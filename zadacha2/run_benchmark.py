import os
import sys
import subprocess
import csv
import time
import re

BROKERS = ["rabbit", "redis"]
PAYLOADS = [128, 1024, 10240, 102400]
RATES = [1000, 5000, 10000]
DURATION = 10

RESULTS_DIR = "results"
RESULTS_FILE = f"{RESULTS_DIR}/results.csv"


def ensure_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)


def init_csv():
    with open(RESULTS_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "broker", "payload_bytes", "target_rate",
            "sent", "received", "send_errors", "recv_errors",
            "sent_mps", "recv_mps", "lost",
            "avg_latency_ms", "p95_latency_ms", "max_latency_ms"
        ])


def run_producer(broker, payload, rate, duration):
    env = os.environ.copy()
    env["BROKER"] = broker
    env["RATE"] = str(rate)
    env["SIZE"] = str(payload)
    env["DURATION"] = str(duration)
    
    result = subprocess.run(
        ["python", "producer.py"],
        env=env,
        capture_output=True,
        text=True
    )
    return result.stdout


def run_consumer(broker, duration):
    env = os.environ.copy()
    env["BROKER"] = broker
    
    proc = subprocess.Popen(
        ["python", "consumer.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    time.sleep(duration + 2)
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=5)
    return stdout


def parse_producer_output(output):
    sent = 0
    errors = 0
    
    for line in output.split('\n'):
        if 'Sent:' in line:
            parts = line.split(',')
            for part in parts:
                if 'Sent:' in part:
                    sent = int(part.split(':')[1].strip())
                if 'Errors:' in part:
                    errors = int(part.split(':')[1].strip())
    
    return sent, errors


def parse_consumer_output(output):
    received = 0
    avg_lat = 0
    p95_lat = 0
    max_lat = 0
    
    lines = output.split('\n')
    for line in lines:
        if 'Processed:' in line:
            parts = line.split('|')
            if len(parts) > 0:
                received = int(parts[0].split(':')[1].strip())
        if 'Latency - Avg:' in line:
            nums = re.findall(r'[\d.]+', line)
            if len(nums) >= 3:
                avg_lat = float(nums[0])
                p95_lat = float(nums[1])
                max_lat = float(nums[2])
    
    return received, avg_lat, p95_lat, max_lat


def run_benchmark(broker, payload, rate, duration, test_num, total):
    print(f"[{test_num}/{total}] {broker} | {payload}B | {rate} msg/s", end=" ", flush=True)
    
    consumer_proc = subprocess.Popen(
        ["python", "consumer.py"],
        env={**os.environ, "BROKER": broker},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    time.sleep(1)
    
    producer_output = run_producer(broker, payload, rate, duration)
    
    time.sleep(2)
    consumer_proc.terminate()
    consumer_output, _ = consumer_proc.communicate(timeout=5)
    
    sent, send_errors = parse_producer_output(producer_output)
    received, avg_lat, p95_lat, max_lat = parse_consumer_output(consumer_output)
    
    lost = sent - received
    sent_mps = sent / duration
    recv_mps = received / duration
    
    result = {
        "broker": broker,
        "payload_bytes": payload,
        "target_rate": rate,
        "sent": sent,
        "received": received,
        "send_errors": send_errors,
        "recv_errors": 0,
        "sent_mps": round(sent_mps, 2),
        "recv_mps": round(recv_mps, 2),
        "lost": lost,
        "avg_latency_ms": round(avg_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "max_latency_ms": round(max_lat, 2)
    }
    
    print(f"✓ recv={received}, lost={lost}, p95={round(p95_lat, 2)}ms")
    return result


def save_result(result):
    with open(RESULTS_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            result["broker"], result["payload_bytes"], result["target_rate"],
            result["sent"], result["received"], result["send_errors"], result["recv_errors"],
            result["sent_mps"], result["recv_mps"], result["lost"],
            result["avg_latency_ms"], result["p95_latency_ms"], result["max_latency_ms"]
        ])


def generate_report():
    report_file = f"{RESULTS_DIR}/report.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("# Результаты сравнения RabbitMQ и Redis\n\n")
        f.write("| Broker | Payload (B) | Rate (msg/s) | Sent | Received | Lost | Recv MPS | Avg Lat (ms) | P95 Lat (ms) | Max Lat (ms) |\n")
        f.write("|--------|-------------|--------------|------|----------|------|----------|--------------|--------------|--------------|\n")
        
        with open(RESULTS_FILE, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                f.write(f"| {row['broker']} | {row['payload_bytes']} | {row['target_rate']} | "
                       f"{row['sent']} | {row['received']} | {row['lost']} | "
                       f"{row['recv_mps']} | {row['avg_latency_ms']} | "
                       f"{row['p95_latency_ms']} | {row['max_latency_ms']} |\n")
    
    print(f"\nОтчёт сохранён: {report_file}")


def main():
    if len(sys.argv) < 2:
        print("Использование:")
        print("  python run_benchmark.py suite")
        print("  python run_benchmark.py run --broker rabbitmq --payload-bytes 1024 --rate 5000 --duration-sec 10")
        sys.exit(1)
    
    if sys.argv[1] == "suite":
        ensure_dir()
        init_csv()
        
        total = len(BROKERS) * len(PAYLOADS) * len(RATES)
        current = 0
        
        print(f"\nЗапуск {total} тестов...\n")
        
        for broker in BROKERS:
            for payload in PAYLOADS:
                for rate in RATES:
                    current += 1
                    result = run_benchmark(broker, payload, rate, DURATION, current, total)
                    save_result(result)
        
        generate_report()
        print(f"\nГотово! Результаты в {RESULTS_FILE}")
    
    elif sys.argv[1] == "run":
        broker = None
        payload = None
        rate = None
        duration = 10
        
        for i, arg in enumerate(sys.argv):
            if arg == "--broker" and i+1 < len(sys.argv):
                broker = sys.argv[i+1]
            if arg == "--payload-bytes" and i+1 < len(sys.argv):
                payload = int(sys.argv[i+1])
            if arg == "--rate" and i+1 < len(sys.argv):
                rate = int(sys.argv[i+1])
            if arg == "--duration-sec" and i+1 < len(sys.argv):
                duration = int(sys.argv[i+1])
        
        if not broker or not payload or not rate:
            print("Ошибка: не хватает аргументов")
            sys.exit(1)
        
        if broker == "rabbitmq":
            broker = "rabbit"
        
        result = run_benchmark(broker, payload, rate, duration, 1, 1)
        
        print("Результаты:")
        print(f"  Sent: {result['sent']}")
        print(f"  Received: {result['received']}")
        print(f"  Lost: {result['lost']}")
        print(f"  Send errors: {result['send_errors']}")
        print(f"  Sent MPS: {result['sent_mps']}")
        print(f"  Recv MPS: {result['recv_mps']}")
        print(f"  Avg latency: {result['avg_latency_ms']} ms")
        print(f"  P95 latency: {result['p95_latency_ms']} ms")
        print(f"  Max latency: {result['max_latency_ms']} ms")


if __name__ == "__main__":
    main()
