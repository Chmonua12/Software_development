import os
import time
import json
import uuid
import asyncio
import redis.asyncio as aioredis
import aio_pika

BROKER = os.getenv("BROKER")
RATE = int(os.getenv("RATE"))
SIZE = int(os.getenv("SIZE"))
DURATION = int(os.getenv("DURATION"))

payload = "x" * SIZE

sent = 0
errors = 0

async def rabbit():
    global sent, errors
    connection = await aio_pika.connect_robust("amqp://guest:guest@localhost/")
    channel = await connection.channel()
    queue = await channel.declare_queue("test", durable=False)

    interval = 1.0 / RATE
    end = time.time() + DURATION
    
    print(f"Starting producer: rate={RATE}, duration={DURATION}, interval={interval:.4f}s")

    while time.time() < end:
        body = json.dumps({
            "id": str(uuid.uuid4()),
            "payload": payload,
            "timestamp": time.time()
        }).encode()
        try:
            await channel.default_exchange.publish(
                aio_pika.Message(body=body),
                routing_key="test"
            )
            sent += 1
            if sent % 1000 == 0:
                print(f"Sent: {sent}")
        except Exception as e:
            errors += 1
            print(f"Error: {e}")
        await asyncio.sleep(interval)
    
    print(f"[PRODUCER] Sent: {sent}, Errors: {errors}")
    await connection.close()

async def redis():
    global sent, errors
    r = await aioredis.from_url("redis://localhost")
    interval = 1.0 / RATE
    end = time.time() + DURATION

    while time.time() < end:
        body = json.dumps({
            "id": str(uuid.uuid4()),
            "payload": payload,
            "timestamp": time.time()
        })
        try:
            await r.lpush("test", body)
            sent += 1
            if sent % 1000 == 0:
                print(f"Sent: {sent}")
        except Exception as e:
            errors += 1
            print(f"Error: {e}")
        await asyncio.sleep(interval)
    
    print(f"[PRODUCER] Sent: {sent}, Errors: {errors}")
    await r.close()

if BROKER == "rabbit":
    asyncio.run(rabbit())
else:
    asyncio.run(redis())
