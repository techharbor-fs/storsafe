# OneDrive API Setup Guide for Railway

This guide walks you through setting up Microsoft Graph API access for OneDrive integration in Railway.

## Prerequisites

- Microsoft account with OneDrive access
- Azure account (free tier is sufficient)

---

## Step 1: Azure App Registration

1. **Go to Azure Portal:**
   - Visit: [https://portal.azure.com](https://portal.azure.com)
   - Sign in with your Microsoft account

1. **Navigate to App Registrations:**
   - Search for "App registrations" in the top search bar
   - Click "App registrations"

1. **Create New Registration:**
   - Click "+ New registration"
   - **Name:** `Westons Dashboard OneDrive Access`
   - **Supported account types:** Select "Accounts in any organizational directory and personal Microsoft accounts"
   - **Redirect URI:** Select "Web" and enter: `http://localhost:8080/auth/callback`
   - Click "Register"

1. **Note Your Application (client) ID:**
   - On the Overview page, copy the **Application (client) ID**
   - Save this as `ONEDRIVE_CLIENT_ID` = c3d80c5b-c29a-41d6-9d5b-b55b59b7d0f6

1. **Note Your Directory (tenant) ID:**
   - Also on Overview page, copy **Directory (tenant) ID**
   - Save this as `ONEDRIVE_TENANT_ID` = 58091191-40b2-4a9b-8c5a-69dc49a1e298

---

## Step 2: Create Client Secret

1. **Navigate to Certificates & secrets:**
   - In left menu, click "Certificates & secrets"

1. **Create New Client Secret:**
   - Under "Client secrets" tab, click "+ New client secret"
   - **Description:** `Railway Dashboard Secret`
   - **Expires:** 24 months (maximum)
   - Click "Add"

1. **Copy the Secret Value:**
   - **IMPORTANT:** Copy the "Value" immediately (not the "Secret ID")
   - You won't be able to see this again!
   - Save this as `ONEDRIVE_CLIENT_SECRET`

   ```text
   Value = YOUR_CLIENT_SECRET_VALUE_HERE
   Secret ID = YOUR_SECRET_ID_HERE
   ```

---

## Step 3: Configure API Permissions

1. **Navigate to API permissions:**
   - In left menu, click "API permissions"

1. **Add Microsoft Graph Permissions:**
   - Click "+ Add a permission"
   - Select "Microsoft Graph"
   - Select "Delegated permissions"
   - Search and add these permissions:
     - `Files.ReadWrite.All` (Read and write all files user can access)
     - `offline_access` (Maintain access to data you've given it access to)
   - Click "Add permissions"

1. **Grant Admin Consent:**
   - **IMPORTANT:** For shared OneDrive folders, you have two options:

   **Option A - User Consent (Works for personal shared access):**

   - Skip admin consent button (you'll consent during OAuth flow)
   - When you authenticate, YOU grant permission to access files shared with you
   - No admin needed if files are shared with your personal account

   **Option B - Admin Consent (Required for organization-wide access):**

   - Contact Westons Corporation IT administrator
   - They must click "Grant admin consent for WESTONS CORPORATION"
   - Required if accessing company OneDrive without individual user auth

---

## Step 4: Get Refresh Token

You need to authenticate once to get a refresh token that Railway can use.

### Option A: Use Python Script (Recommended)

1. **Create `get_onedrive_token.py` on your local computer:**

```python
"""
One-time script to get OneDrive refresh token
Run this locally, NOT in Railway
"""
import requests
from urllib.parse import urlencode, parse_qs
import webbrowser

# Your Azure App credentials
CLIENT_ID = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"
REDIRECT_URI = "http://localhost:8080/auth/callback"
TENANT_ID = "common"  # or your specific tenant ID

# Microsoft OAuth URLs
AUTH_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
TOKEN_URL = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"

# Scopes needed
SCOPES = [
    "https://graph.microsoft.com/Files.ReadWrite.All",
    "https://graph.microsoft.com/offline_access"
]

def get_auth_url():
    """Generate authorization URL"""
    params = {
        'client_id': CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': REDIRECT_URI,
        'scope': ' '.join(SCOPES),
        'response_mode': 'query'
    }
    return f"{AUTH_URL}?{urlencode(params)}"

def get_tokens_from_code(auth_code):
    """Exchange authorization code for tokens"""
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': auth_code,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code',
        'scope': ' '.join(SCOPES)
    }

    response = requests.post(TOKEN_URL, data=data)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.text}")
        return None

def main():
    print("="*60)
    print("OneDrive Refresh Token Generator")
    print("="*60)
    print()

    # Step 1: Get authorization URL
    auth_url = get_auth_url()
    print("Step 1: Opening browser for authentication...")
    print(f"URL: {auth_url}")
    print()

    webbrowser.open(auth_url)

    print("After signing in, you'll be redirected to localhost:8080")
    print("The browser will show an error (that's expected)")
    print()

    # Step 2: Get authorization code from user
    print("Step 2: Copy the ENTIRE URL from your browser address bar")
    redirected_url = input("Paste URL here: ").strip()

    # Extract code from URL
    if '?' not in redirected_url:
        print("Error: Invalid URL. Make sure you copied the entire URL.")
        return

    query_string = redirected_url.split('?')[1]
    params = parse_qs(query_string)

    if 'code' not in params:
        print("Error: No authorization code found in URL")
        return

    auth_code = params['code'][0]
    print(f"\n✅ Authorization code extracted: {auth_code[:20]}...")

    # Step 3: Exchange code for tokens
    print("\nStep 3: Exchanging code for tokens...")
    tokens = get_tokens_from_code(auth_code)

    if not tokens:
        print("❌ Failed to get tokens")
        return

    # Step 4: Display results
    print("\n" + "="*60)
    print("✅ SUCCESS! Copy these to Railway environment variables:")
    print("="*60)
    print()
    print(f"ONEDRIVE_CLIENT_ID={CLIENT_ID}")
    print(f"ONEDRIVE_CLIENT_SECRET={CLIENT_SECRET}")
    print(f"ONEDRIVE_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"ONEDRIVE_TENANT_ID={TENANT_ID}")
    print()
    print("="*60)
    print("⚠️  IMPORTANT: Keep these secrets secure!")
    print("="*60)

if __name__ == "__main__":
    main()
```

1. **Update the script with your credentials:**
   - Replace `YOUR_CLIENT_ID_HERE` with your Application (client) ID
   - Replace `YOUR_CLIENT_SECRET_HERE` with your client secret value

1. **Run the script:**

   ```bash
   python get_onedrive_token.py
   ```

1. **Follow the prompts:**
   - Browser will open for Microsoft login
   - Sign in with your OneDrive account
   - Grant permissions to the app
   - Browser redirects to localhost (will show error - that's expected)
   - Copy the ENTIRE URL from browser address bar
   - Paste into the script prompt

1. **Copy the environment variables:**
   - Script will display all credentials needed
   - Save these for Railway configuration

---

## Step 5: Configure Railway Environment Variables

1. **Go to Railway Dashboard:**
   - Visit: [https://railway.app](https://railway.app)
   - Open your Westons Dashboard project

1. **Add Environment Variables:**
   - Go to "Variables" tab
   - Click "+ New Variable"
   - Add each of these:

   ```text
   ONEDRIVE_CLIENT_ID=<your-client-id>
   ONEDRIVE_CLIENT_SECRET=<your-client-secret>
   ONEDRIVE_REFRESH_TOKEN=<your-refresh-token>
   ONEDRIVE_TENANT_ID=<your-tenant-id>
   ```

1. **Deploy Changes:**
   - Railway will automatically redeploy with new environment variables

---

## Step 6: Test OneDrive Connection

1. **Run test script in Railway:**

   ```python
   from utils.onedrive_client import get_onedrive_client

   client = get_onedrive_client()
   items = client.list_folder("/")
   print(f"✅ OneDrive connected! Found {len(items)} items in root")
   ```

1. **Expected output:**

   ```text
   ✅ OneDrive connected! Found 5 items in root
   ```

---

## Troubleshooting

### Error: "Invalid client secret"

- Client secret may have expired (24 month max)
- Generate new secret in Azure Portal → Certificates & secrets
- Update `ONEDRIVE_CLIENT_SECRET` in Railway

### Error: "Invalid refresh token"

- Refresh token may have been revoked
- Re-run `get_onedrive_token.py` to get new refresh token
- Update `ONEDRIVE_REFRESH_TOKEN` in Railway

### Error: "Insufficient permissions"

- Check API permissions in Azure Portal
- Ensure `Files.ReadWrite.All` and `offline_access` are granted
- Grant admin consent if not already done

### Error: "Token expired"

- This is normal - OneDriveClient automatically refreshes tokens
- If refresh fails, check client secret and refresh token

---

## Security Best Practices

1. **Never commit credentials to Git:**
   - Credentials should only exist in Railway environment variables
   - Add `.env` to `.gitignore`

1. **Rotate secrets periodically:**
   - Generate new client secret every 12-18 months
   - Update Railway environment variables

1. **Use least-privilege permissions:**
   - Only grant `Files.ReadWrite.All` (no admin permissions needed)

1. **Monitor access:**
   - Check Azure Portal → App registrations → Your app → Sign-in logs
   - Review unusual activity

---

## Next Steps

After completing setup:

1. Test OneDrive connection (Step 6)
1. Update `parse_timesheets.py` to use OneDrive API
1. Update invoice automation to use OneDrive API for attachments
1. Test end-to-end workflow in Railway

---

## Reference Links

- Azure Portal: [https://portal.azure.com](https://portal.azure.com)
- Microsoft Graph API Docs: [https://docs.microsoft.com/graph/api/overview](https://docs.microsoft.com/graph/api/overview)
- OneDrive API Reference: [https://docs.microsoft.com/graph/api/resources/onedrive](https://docs.microsoft.com/graph/api/resources/onedrive)
- Railway Dashboard: [https://railway.app](https://railway.app)

---

**Questions? Issues?**
Check Railway logs for detailed error messages or contact support.
