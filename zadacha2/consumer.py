import os
import time
import json
import asyncio
import redis.asyncio as aioredis
import aio_pika

BROKER = os.getenv("BROKER")

count = 0
latencies = []  # для p95
lost = 0        # потерянные сообщения

async def rabbit():
    global count, latencies, lost
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=False)

    async with queue.iterator() as q:
        async for message in q:
            async with message.process():
                try:
                    data = json.loads(message.body)
                    sent_time = data.get("timestamp")
                    if sent_time:
                        latency = time.time() - sent_time
                        latencies.append(latency)
                    count += 1
                except:
                    lost += 1

async def redis():
    global count, latencies, lost
    r = aioredis.from_url("redis://localhost")

    while True:
        msg = await r.brpop("test")
        if msg:
            try:
                data = json.loads(msg[1])
                sent_time = data.get("timestamp")
                if sent_time:
                    latency = time.time() - sent_time
                    latencies.append(latency)
                count += 1
            except:
                lost += 1

async def stats():
    start = time.time()
    while True:
        await asyncio.sleep(5)
        now = time.time()
        elapsed = int(now - start)
        print(f"\n--- {elapsed}s ---")
        print(f"Processed: {count}")
        print(f"Lost: {lost}")
        if latencies:
            print(f"Avg latency: {sum(latencies)/len(latencies):.4f}s")
            print(f"P95 latency: {sorted(latencies)[int(len(latencies)*0.95)]:.4f}s")
            print(f"Max latency: {max(latencies):.4f}s")

async def main():
    if BROKER == "rabbit":
        await asyncio.gather(rabbit(), stats())
    else:
        await asyncio.gather(redis(), stats())

asyncio.run(main())
