from api import get_user_data

def get_user_summary():
    data = get_user_data()
    return f"{data['username']} is {data['age']} years old"
