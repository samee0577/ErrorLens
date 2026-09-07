from discount import apply_discount

def get_final_price(price, discount_percent):
    # discount_percent comes in as a whole number, e.g. 20 for 20%
    return apply_discount(price, discount_percent)
