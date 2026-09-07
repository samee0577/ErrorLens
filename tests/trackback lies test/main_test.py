from store import checkout

items = [{"price": 50}, {"price": 30}]
result = checkout(items)
print(f"Total: {result}")