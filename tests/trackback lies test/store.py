from pricing import calculate_price

def checkout(items):
    total = 0
    for item in items:
        total += calculate_price(item["price"])
    return total