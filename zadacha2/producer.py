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
        except:
            errors += 1
        await asyncio.sleep(interval)
    
    print(f"Sent: {sent}, Errors: {errors}")

async def redis():
    global sent, errors
    r = aioredis.from_url("redis://localhost")
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
        except:
            errors += 1
        await asyncio.sleep(interval)
    
    print(f"Sent: {sent}, Errors: {errors}")

if BROKER == "rabbit":
    asyncio.run(rabbit())
else:
    asyncio.run(redis())
