from config import DISCOUNT_RATE

def calculate_price(base_price):
    return base_price * (1 - DISCOUNT_RATE)