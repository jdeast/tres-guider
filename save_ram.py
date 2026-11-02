import psutil
import redis
import time

def get_ram_info():
    # Get RAM information
    mem = psutil.virtual_memory()
    used_ram = str(mem.used / (1024 ** 3))  # Convert bytes to GB and then to string
    free_ram = str(mem.available / (1024 ** 3))
    return used_ram, free_ram

def save_to_redis(ip, table, used_ram, free_ram):
    # Save data to Redis database
    try:
        r = redis.Redis(host=ip, port=6379, db=table)
        data = {
            "used_ram": used_ram,
            "free_ram": free_ram
        }
        r.mset(data)
        r.close()
    except redis.RedisError as e:
        print(f"Error while saving data to Redis: {e}")

if __name__ == "__main__":
    redis_ip = "<STARLORD_REDIS_IP>"
    redis_table = "2"

    while True:
        used_ram, free_ram = get_ram_info()
        save_to_redis(redis_ip, redis_table, used_ram, free_ram)
        time.sleep(60)  # Wait for 60 seconds before the next update


