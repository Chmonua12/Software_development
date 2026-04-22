import os
import time
import json
import asyncio
import redis.asyncio as aioredis
import aio_pika

BROKER = os.getenv("BROKER")

count = 0
latencies = []
errors = 0

async def rabbit():
    global count, latencies, errors
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=False)
    
    print("RabbitMQ consumer started, waiting for messages...")

    async with queue.iterator() as q:
        async for message in q:
            async with message.process():
                try:
                    data = json.loads(message.body)
                    sent_ts = data.get("timestamp")
                    if sent_ts:
                        latency_ms = (time.time() - sent_ts) * 1000
                        latencies.append(latency_ms)
                    count += 1
                    if count % 1000 == 0:
                        print(f"Received: {count}")
                except Exception as e:
                    errors += 1
                    print(f"Error processing: {e}")

async def redis():
    global count, latencies, errors
    r = aioredis.from_url("redis://localhost")
    print("Redis consumer started, waiting for messages...")

    while True:
        msg = await r.brpop("test")
        if msg:
            try:
                data = json.loads(msg[1])
                sent_ts = data.get("timestamp")
                if sent_ts:
                    latency_ms = (time.time() - sent_ts) * 1000
                    latencies.append(latency_ms)
                count += 1
                if count % 1000 == 0:
                    print(f"Received: {count}")
            except Exception as e:
                errors += 1
                print(f"Error processing: {e}")

async def stats():
    start = time.time()
    while True:
        await asyncio.sleep(5)
        now = time.time()
        elapsed = int(now - start)
        
        print(f"\n[{elapsed}s] Processed: {count} | Errors: {errors}")
        
        if latencies:
            sorted_lat = sorted(latencies)
            p95_idx = int(len(sorted_lat) * 0.95)
            print(f"  Latency - Avg: {sum(latencies)/len(latencies):.2f}ms | P95: {sorted_lat[p95_idx]:.2f}ms | Max: {max(latencies):.2f}ms")
            print(f"  Throughput: {count/elapsed:.2f} msg/s")

async def main():
    if BROKER == "rabbit":
        await asyncio.gather(rabbit(), stats())
    else:
        await asyncio.gather(redis(), stats())

asyncio.run(main())
