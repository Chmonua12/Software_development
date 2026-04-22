from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass, asdict

import aio_pika
import redis.asyncio as aioredis


@dataclass
class RunResult:
    broker: str
    payload_bytes: int
    rate: int
    duration_sec: float
    sent: int
    received: int
    send_errors: int
    recv_errors: int
    avg_ms: float
    p95_ms: float
    max_ms: float
    recv_msg_per_sec: float
    sent_msg_per_sec: float
    backlog: int | None = None


def now_ns() -> int:
    return time.time_ns()


def make_payload(size: int) -> str:
    return "x" * size


def make_message(payload: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "payload": payload,
        "sent_ts_ns": now_ns()
    }


def encode_message(msg: dict) -> str:
    return json.dumps(msg)


def decode_message(data: str) -> dict:
    return json.loads(data)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * p / 100.0
    if idx.is_integer():
        return sorted_vals[int(idx)]
    lower = sorted_vals[int(idx)]
    upper = sorted_vals[int(idx) + 1]
    return lower + (upper - lower) * (idx - int(idx))


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


async def rabbit_setup():
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    await channel.declare_queue("test", durable=False)
    await connection.close()


async def rabbit_purge():
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=False)
    await queue.purge()
    await connection.close()


async def rabbit_backlog() -> int:
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=False)
    count = queue.declaration_result.message_count
    await connection.close()
    return count


async def redis_setup():
    r = await aioredis.from_url("redis://localhost")
    await r.delete("test")
    await r.close()


async def redis_purge():
    r = await aioredis.from_url("redis://localhost")
    await r.delete("test")
    await r.close()


async def redis_backlog() -> int:
    r = await aioredis.from_url("redis://localhost")
    length = await r.llen("test")
    await r.close()
    return length


async def run_one(broker: str, payload_bytes: int, rate: int, duration_sec: float) -> RunResult:
    lat_ms: list[float] = []
    recv_errors = 0
    received = 0
    stop_event = asyncio.Event()

    if broker == "rabbitmq":
        await rabbit_setup()
        await rabbit_purge()

        connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
        channel = await connection.channel()
        queue = await channel.declare_queue("test", durable=False)

        async def consumer_loop():
            nonlocal received, recv_errors
            try:
                async with queue.iterator() as q_iter:
                    async for message in q_iter:
                        if stop_event.is_set():
                            break
                        async with message.process():
                            try:
                                data = decode_message(message.body.decode())
                                sent_ts = data.get("sent_ts_ns")
                                if sent_ts:
                                    latency_ms = (now_ns() - sent_ts) / 1e6
                                    lat_ms.append(latency_ms)
                                received += 1
                            except Exception:
                                recv_errors += 1
            except asyncio.CancelledError:
                pass

        consumer_task = asyncio.create_task(consumer_loop())

        await asyncio.sleep(2)

        payload = make_payload(payload_bytes)
        interval = 1.0 / rate if rate > 0 else 0
        end_time = time.time() + duration_sec
        sent = 0
        send_errors = 0

        while time.time() < end_time:
            try:
                msg = make_message(payload)
                await channel.default_exchange.publish(
                    aio_pika.Message(body=encode_message(msg).encode()),
                    routing_key="test"
                )
                sent += 1
            except Exception:
                send_errors += 1
            if interval > 0:
                await asyncio.sleep(interval)

        await asyncio.sleep(3)

        stop_event.set()
        consumer_task.cancel()
        try:
            await asyncio.wait_for(consumer_task, timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        await connection.close()
        backlog = await rabbit_backlog()

    elif broker == "redis":
        await redis_setup()
        await redis_purge()

        r = await aioredis.from_url("redis://localhost")

        async def consumer_loop():
            nonlocal received, recv_errors
            try:
                while not stop_event.is_set():
                    try:
                        result = await asyncio.wait_for(r.brpop("test", timeout=1), timeout=1)
                        if result:
                            _, data = result
                            msg = decode_message(data)
                            sent_ts = msg.get("sent_ts_ns")
                            if sent_ts:
                                latency_ms = (now_ns() - sent_ts) / 1e6
                                lat_ms.append(latency_ms)
                            received += 1
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        recv_errors += 1
            except asyncio.CancelledError:
                pass

        consumer_task = asyncio.create_task(consumer_loop())

        await asyncio.sleep(2)

        payload = make_payload(payload_bytes)
        interval = 1.0 / rate if rate > 0 else 0
        end_time = time.time() + duration_sec
        sent = 0
        send_errors = 0

        while time.time() < end_time:
            try:
                msg = make_message(payload)
                await r.lpush("test", encode_message(msg))
                sent += 1
            except Exception:
                send_errors += 1
            if interval > 0:
                await asyncio.sleep(interval)

        await asyncio.sleep(3)

        stop_event.set()
        consumer_task.cancel()
        try:
            await asyncio.wait_for(consumer_task, timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

        await r.close()
        backlog = await redis_backlog()

    else:
        raise ValueError(f"Unknown broker: {broker}")

    avg_ms = statistics.fmean(lat_ms) if lat_ms else 0.0
    p95_ms = percentile(lat_ms, 95.0)
    max_ms = max(lat_ms) if lat_ms else 0.0

    recv_mps = received / duration_sec if duration_sec > 0 else 0.0
    sent_mps = sent / duration_sec if duration_sec > 0 else 0.0

    return RunResult(
        broker=broker,
        payload_bytes=payload_bytes,
        rate=rate,
        duration_sec=duration_sec,
        sent=sent,
        received=received,
        send_errors=send_errors,
        recv_errors=recv_errors,
        avg_ms=float(avg_ms),
        p95_ms=float(p95_ms),
        max_ms=float(max_ms),
        recv_msg_per_sec=float(recv_mps),
        sent_msg_per_sec=float(sent_mps),
        backlog=backlog,
    )


def write_results_csv(path: str, results: list[RunResult]) -> None:
    ensure_dir(os.path.dirname(path))
    rows = [asdict(r) for r in results]
    fieldnames = list(rows[0].keys()) if rows else []
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def write_report_md(path: str, results: list[RunResult]) -> None:
    ensure_dir(os.path.dirname(path))
    lines: list[str] = []
    lines.append("# Результаты сравнения RabbitMQ и Redis\n")
    lines.append("## Сводная таблица\n")
    lines.append("| broker | payload_bytes | rate | duration | sent | received | lost | send_err | recv_err | sent_mps | recv_mps | avg_ms | p95_ms | max_ms | backlog |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        lost = max(0, int(r.sent - r.received))
        lines.append(
            f"| {r.broker} | {r.payload_bytes} | {r.rate} | {r.duration_sec} | {r.sent} | {r.received} | {lost} | {r.send_errors} | {r.recv_errors} | "
            f"{r.sent_msg_per_sec:.1f} | {r.recv_msg_per_sec:.1f} | {r.avg_ms:.2f} | {r.p95_ms:.2f} | {r.max_ms:.2f} | {r.backlog if r.backlog is not None else '-'} |"
        )
    lines.append("\n## Выводы\n")
    lines.append("- **Пропускная способность**: ...\n")
    lines.append("- **Влияние размера сообщения**: ...\n")
    lines.append("- **Точка деградации single instance**: ...\n")
    lines.append("- **Какой брокер лучше**: ...\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_args():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run")
    run.add_argument("--broker", choices=["rabbitmq", "redis"], required=True)
    run.add_argument("--payload-bytes", type=int, required=True)
    run.add_argument("--rate", type=int, required=True)
    run.add_argument("--duration-sec", type=float, default=10.0)

    suite = sub.add_parser("suite")
    suite.add_argument("--brokers", nargs="+", default=["rabbitmq", "redis"])
    suite.add_argument("--payload-bytes", nargs="+", type=int, default=[128, 1024, 10240, 102400])
    suite.add_argument("--rates", nargs="+", type=int, default=[1000, 5000, 10000])
    suite.add_argument("--duration-sec", type=float, default=10.0)
    suite.add_argument("--out-dir", default="results")

    return p.parse_args()


async def main():
    args = parse_args()

    if args.cmd == "run":
        result = await run_one(
            broker=args.broker,
            payload_bytes=args.payload_bytes,
            rate=args.rate,
            duration_sec=args.duration_sec
        )
        print(asdict(result))

    elif args.cmd == "suite":
        results: list[RunResult] = []
        total = len(args.brokers) * len(args.payload_bytes) * len(args.rates)
        current = 0

        print(f"\nRunning {total} tests...\n")

        for broker in args.brokers:
            for payload in args.payload_bytes:
                for rate in args.rates:
                    current += 1
                    print(f"[{current}/{total}] {broker} | {payload}B | {rate} msg/s")
                    result = await run_one(
                        broker=broker,
                        payload_bytes=payload,
                        rate=rate,
                        duration_sec=args.duration_sec
                    )
                    results.append(result)
                    lost = result.sent - result.received
                    print(f"    sent={result.sent}, received={result.received}, lost={lost}, p95={result.p95_ms}ms")

        csv_path = os.path.join(args.out_dir, "results.csv")
        md_path = os.path.join(args.out_dir, "report.md")
        write_results_csv(csv_path, results)
        write_report_md(md_path, results)
        print(f"\nResults saved to {csv_path}")
        print(f"Report saved to {md_path}")


if __name__ == "__main__":
    asyncio.run(main())
