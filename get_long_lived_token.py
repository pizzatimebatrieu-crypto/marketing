import requests
import sys

def get_long_lived_token(app_id, app_secret, short_token):
    # 1. Exchange short-lived user token for long-lived user token
    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token
    }
    
    print("--- Dang doi token user dai han... ---")
    r = requests.get(url, params=params)
    data = r.json()
    
    if "access_token" not in data:
        print("Loi khi lay user token:", data)
        return
    
    long_user_token = data["access_token"]
    print(f"Token User dai han (60 ngay):\n{long_user_token}\n")
    
    # 2. Get Page Access Token (this will be permanent if using a long-lived user token)
    print("--- Dang lay token Page vinh vien... ---")
    url_accounts = f"https://graph.facebook.com/v21.0/me/accounts"
    r = requests.get(url_accounts, params={"access_token": long_user_token})
    pages_data = r.json()
    
    if "data" not in pages_data:
        print("Loi khi lay danh sach Page:", pages_data)
        return
    
    print("Danh sach Page va Token:")
    for page in pages_data["data"]:
        print(f"Name: {page['name']}")
        print(f"ID: {page['id']}")
        print(f"Access Token: {page['access_token']}")
        print("-" * 20)

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Cach dung: python get_long_lived_token.py <APP_ID> <APP_SECRET> <SHORT_LIVED_TOKEN>")
    else:
        get_long_lived_token(sys.argv[1], sys.argv[2], sys.argv[3])
