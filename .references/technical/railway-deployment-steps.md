# 🚀 Quick Deployment Guide - Flask App to Railway

A simple step-by-step guide for deploying Flask web apps to Railway with custom domain.

---

## 📋 Prerequisites

- Flask app working locally
- GitHub account
- Railway account (sign up at [https://railway.app](https://railway.app))
- Domain access (GoDaddy, Namecheap, etc.)

---

## Step 1: Prepare Deployment Files

### 1.1 Create `requirements.txt`

```txt
flask==3.0.0
waitress==3.0.0
# Add other dependencies your app uses
```

### 1.2 Create `Procfile` (no file extension)

```text
web: python app.py
```

### 1.3 Create `runtime.txt`

```text
python-3.11
```

### 1.4 Create `railway.json` (optional)

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "numReplicas": 1,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 1.5 Update your `app.py` to use Waitress

```python
from waitress import serve

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    serve(app, host='0.0.0.0', port=port)
```

---

## Step 2: Create GitHub Repository

### 2.1 Initialize Git (if not already)

```bash
cd "path/to/your/app"
git init
git add .
git commit -m "Initial commit"
git branch -M main
```

### 2.2 Create GitHub Repo

1. Go to [https://github.com/new](https://github.com/new)
1. Repository name: `your-app-name`
1. Choose **Private** or **Public**
1. **Don't initialize** with README (you already have code)
1. Click "Create repository"

### 2.3 Push to GitHub

```bash
git remote add origin https://github.com/YOUR-USERNAME/your-app-name.git
git push -u origin main
```

---

## Step 3: Deploy to Railway

### 3.1 Sign Up & Login

1. Go to [https://railway.app](https://railway.app)
1. Click "Login" → "Login with GitHub"
1. Authorize Railway

### 3.2 Create New Project

1. Click "New Project"
1. Select "Deploy from GitHub repo"
1. If repos not showing:
   - Click "Configure GitHub App"
   - Grant access to your repository
   - Select specific repo
1. Click on your repository

### 3.3 Wait for Initial Build

- Railway will automatically detect Python app
- First deployment will likely **fail** (missing environment variables)
- This is normal!

---

## Step 4: Configure Environment Variables

### 4.1 Access Variables

1. Click on your service in Railway
1. Go to "Variables" tab
1. Click "Raw Editor"

### 4.2 Add Your Variables

```env
# Example variables - adjust for your app
DATABASE_URL=your_database_url
API_KEY=your_api_key
SECRET_KEY=your_secret_key
# Add all required environment variables
```

### 4.3 Apply Changes

1. Click "Update Variables" or "Save"
1. Railway will automatically redeploy
1. Wait 1-2 minutes for build to complete

---

## Step 5: Generate Public URL

### 5.1 Create Domain

1. Click on your service
1. Go to "Settings" → "Networking"
1. Click "Generate Domain"
1. Select your port (usually **8080** for Waitress)
1. Railway generates URL like: `your-app-production.up.railway.app`

### 5.2 Test Your App

1. Click the generated URL
1. Verify app loads correctly
1. Test all features work

---

## Step 6: Add Custom Domain (Optional)

### 6.1 Add Domain in Railway

1. In "Networking" section
1. Click "+ Custom Domain"
1. Enter: `subdomain.yourdomain.com` (e.g., `app.example.com`)
1. Select port: **8080**
1. Click "Add Domain"

**Railway will show:**

```text
Type: CNAME
Name: subdomain
Value: xyz123.up.railway.app
Status: Record not yet detected
```

### 6.2 Configure DNS (GoDaddy Example)

1. Log into your domain registrar (GoDaddy, Namecheap, etc.)
1. Go to DNS Management
1. Click "Add Record"
1. Fill in:
   - **Type:** CNAME
   - **Name:** `subdomain` (or `app`, `dashboard`, etc.)
   - **Value:** `xyz123.up.railway.app` (from Railway)
   - **TTL:** 1 Hour
1. Click "Save"

### 6.3 Wait for DNS Propagation

- Usually takes **15-30 minutes**
- Can take up to 48 hours
- Railway will auto-detect when ready
- SSL certificate provisions automatically

---

## Step 7: Verify Everything Works

### 7.1 Test Both URLs

- Railway URL: `https://your-app-production.up.railway.app`
- Custom domain: `https://subdomain.yourdomain.com`

### 7.2 Check Features

- All pages load
- Database connections work
- API calls succeed
- Authentication works

---

## 🔄 Future Updates

### To Update Your App

```bash
# Make changes to code
git add .
git commit -m "Description of changes"
git push origin main

# Railway automatically detects and redeploys (2-3 minutes)
```

### To Update Environment Variables

1. Railway → Service → Variables
1. Edit or add variables
1. Railway redeploys automatically

---

## 🐛 Common Issues & Fixes

### Issue: "No repositories found" in Railway

**Fix:** Click "Configure GitHub App" → Grant repository access

### Issue: Deployment crashes immediately

**Fix:** Check environment variables are set correctly

### Issue: Port binding error

**Fix:** Make sure app binds to `0.0.0.0` and uses `PORT` environment variable

### Issue: Custom domain not working

**Fix:** Wait 30-60 minutes for DNS propagation, verify CNAME record is correct

### Issue: Railway GitHub loading very slow

**Fix:** Create separate repository (not subfolder), or refresh page

---

## 📝 Deployment Checklist

Before deploying:

- [ ] `requirements.txt` exists with all dependencies
- [ ] `Procfile` created with start command
- [ ] `runtime.txt` specifies Python version
- [ ] App uses `0.0.0.0` host binding
- [ ] Environment variables documented
- [ ] `.gitignore` excludes sensitive files
- [ ] App tested locally

After deploying:

- [ ] Railway build succeeded
- [ ] Environment variables added
- [ ] Public URL works
- [ ] All features tested
- [ ] Custom domain configured (if needed)
- [ ] DNS propagated (if using custom domain)
- [ ] SSL certificate active

---

## 💰 Cost Estimate

**Railway:**

- Free tier: $5 credit/month
- Typical small app: $0-10/month
- Billed by usage (CPU, RAM, bandwidth)

**Domain:**

- If you already own it: $0
- New domain: ~$12/year

**SSL Certificate:**

- Free (automatic from Railway)

**Total:** $0-10/month

---

## 🔗 Useful Links

- Railway: [https://railway.app](https://railway.app)
- Railway Docs: [https://docs.railway.app](https://docs.railway.app)
- Railway Support: [https://railway.app/help](https://railway.app/help)
- Railway Status: [https://status.railway.app](https://status.railway.app)

---

**That's it! Your Flask app is now deployed and accessible worldwide.** 🎉
