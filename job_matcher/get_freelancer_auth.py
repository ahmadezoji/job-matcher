# get_freelancer_auth.py
import requests
import webbrowser

CLIENT_ID = "efd574f2-ccf7-48d6-80d6-0948332a3983"
CLIENT_SECRET = "7ac5277300eaa70384c642739115b2a42d7f69e5011460976dcfec2bf518528225f0c24e754641343a24180c2e2caa6f185fb4cf2bc38d1d1d555dab9cc7697d"
REDIRECT_URI = "http://localhost:8080/callback"  # or whatever you set in Freelancer dev portal
AUTH_URL = "https://accounts.freelancer.com/oauth/authorize"
TOKEN_URL = "https://accounts.freelancer.com/oauth/token"


def get_auth_code():
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        # optionally scope param if API requires specific scopes:
        # "scope": "projects:read", etc.
    }
    # Build the URL
    req = requests.Request("GET", AUTH_URL, params=params).prepare()
    url = req.url
    print("Open this URL in browser to authorize:")
    print(url)
    webbrowser.open(url)
    code = input("Paste the authorization code from redirect URL: ").strip()
    return code

def exchange_code_for_token(code):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    }

    resp = requests.post(TOKEN_URL, data=data)
    if resp.status_code == 200:
        token_data = resp.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if access_token:
            with open("freelancer_token.txt", "w") as f:
                f.write(access_token)
            print("✅ Access token saved in freelancer_token.txt")
            print("🔄 Refresh token:", refresh_token)
        else:
            print("⚠️ Unexpected response:", token_data)
    else:
        print("❌ Failed:", resp.status_code, resp.text)



def main():
    code = get_auth_code()
    exchange_code_for_token(code)

if __name__ == "__main__":
    main()
