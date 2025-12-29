#!/usr/bin/env python3
"""
Script to obtain Trakt access token via OAuth
"""

import os
import webbrowser
import requests
import trakt
from trakt.core import errors

# Configuration
TRAKT_CLIENT_ID = os.getenv('TRAKT_CLIENT_ID')
TRAKT_CLIENT_SECRET = os.getenv('TRAKT_CLIENT_SECRET')
TRAKT_APPLICATION_ID = os.getenv('TRAKT_APPLICATION_ID')

if not TRAKT_CLIENT_ID or not TRAKT_CLIENT_SECRET:
    print("Error: TRAKT_CLIENT_ID and TRAKT_CLIENT_SECRET must be configured")
    print("Export these variables or configure them in .env")
    exit(1)

# Configure Trakt
trakt.CLIENT_ID = TRAKT_CLIENT_ID
trakt.CLIENT_SECRET = TRAKT_CLIENT_SECRET

# Update base URL to current Trakt URL (library uses an old URL)
trakt.BASE_URL = 'https://api.trakt.tv/'

print("Starting OAuth authentication process with Trakt...")
print()

# Get Application ID from environment variable or prompt user
if TRAKT_APPLICATION_ID and TRAKT_APPLICATION_ID.strip():
    app_id = TRAKT_APPLICATION_ID.strip()
    print(f"Using Application ID from environment variable: {app_id}")
else:
    print("To get a PIN, you need to create an application in Trakt:")
    print("1. Go to https://trakt.tv/oauth/applications")
    print("2. Create a new application")
    print("3. Copy the 'Application ID' (not the Client ID)")
    print()

    # Request Application ID
    app_id = input("Enter your Trakt application Application ID: ").strip()

    if not app_id:
        print("Error: Application ID not provided")
        exit(1)

trakt.APPLICATION_ID = app_id

# Get PIN URL
pin_url = f"https://trakt.tv/pin/{app_id}"
print(f"\nPlease visit the following URL in your browser to get a PIN:")
print(f"\n{pin_url}\n")

# Try to open automatically
try:
    webbrowser.open(pin_url)
    print("(Opened automatically in your browser)")
except:
    print("(Copy and paste the URL in your browser)")

print("\nAfter authorizing, you will get a PIN code.")
print()

# Request PIN code
pin = input("Enter the PIN code: ").strip()

if not pin:
    print("Error: PIN code not provided")
    exit(1)

# Exchange PIN for token using pin_auth
try:
    print("\nExchanging PIN for access token...")
    from trakt.core import pin_auth
    
    # Build the URL correctly
    token_url = trakt.BASE_URL.rstrip('/') + '/oauth/token'
    
    # Prepare the data
    args = {
        'code': pin,
        'redirect_uri': trakt.REDIRECT_URI,
        'grant_type': 'authorization_code',
        'client_id': TRAKT_CLIENT_ID,
        'client_secret': TRAKT_CLIENT_SECRET
    }
    
    # Make the request directly with requests for better error control
    print(f"Connecting to: {token_url}")
    response = requests.post(token_url, data=args, timeout=30)
    
    if response.status_code == 200:
        data = response.json()
        access_token = data.get('access_token')
        refresh_token = data.get('refresh_token')
        
        if access_token:
            trakt.OAUTH_TOKEN = access_token
            trakt.OAUTH_REFRESH = refresh_token
            
            print("\n✓ Authentication successful!")
            print("\nConfigure these environment variables:")
            print(f"export TRAKT_ACCESS_TOKEN=\"{access_token}\"")
            
            if refresh_token:
                print(f"export TRAKT_REFRESH_TOKEN=\"{refresh_token}\"")
            
            print("\nOr add these lines to your .env file:")
            print(f"TRAKT_ACCESS_TOKEN={access_token}")
            if refresh_token:
                print(f"TRAKT_REFRESH_TOKEN={refresh_token}")
        else:
            print("Error: No access_token received in response")
            print(f"Response: {data}")
            exit(1)
    else:
        print(f"Error: Request failed with code {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)
        
except requests.exceptions.SSLError as e:
    print(f"SSL Error: {e}")
    print("\nPossible solutions:")
    print("1. Check your internet connection")
    print("2. Check that there is no proxy or firewall blocking the connection")
    print("3. Try updating SSL certificates: sudo update-ca-certificates")
    exit(1)
except requests.exceptions.RequestException as e:
    print(f"Connection error: {e}")
    print("\nCheck your internet connection and that Trakt API is available")
    exit(1)
except Exception as e:
    print(f"Error during authentication: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

