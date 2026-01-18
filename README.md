# DD1750 Vision Assistant

Extract items from **any BOM format** (handwritten, scanned, EPP, etc.) using AI vision and generate filled DD1750 Packing Lists.

## For Users

1. Upload your BOM PDF
2. Click "Extract Items with AI" 
3. Review and edit the extracted items
4. Fill in header info
5. Download your completed DD1750

**Need more extractions?** Contact the admin via Venmo/CashApp for an access code.

---

## Admin Setup

### 1. Deploy to Railway

1. Push this code to GitHub
2. Create new project on [Railway](https://railway.app)
3. Connect your repo
4. Set environment variables (see below)

### 2. Environment Variables

Set these in Railway → Variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Random string for sessions | `your-random-secret-123` |
| `ANTHROPIC_API_KEY` | Your Claude API key | `sk-ant-api03-...` |
| `ADMIN_PASSWORD` | Password for admin panel | `your-admin-password` |
| `FREE_EXTRACTIONS` | Free extractions per user (default: 3) | `3` |

### 3. Get Your Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create account → API Keys → Create new key
3. Copy the key (starts with `sk-ant-`)

---

## How to Generate & Sell Access Codes

### Generate Codes

1. Go to `yourapp.railway.app/admin`
2. Enter your admin password
3. Choose number of codes and credits per code
4. Click "Generate Codes"
5. Copy the codes

### Sell Codes

1. User pays you via Venmo/CashApp/Zelle
2. You send them an access code
3. They redeem it on the site

### Pricing Suggestion

| You Charge | Credits | Your Cost* | Profit |
|------------|---------|------------|--------|
| $5 | 25 | ~$1.25-3.75 | ~$1.25-3.75 |
| $10 | 60 | ~$3-9 | ~$1-7 |

*Claude Vision API costs ~$0.05-0.15 per extraction depending on PDF size

---

## Code Format

Access codes look like: `DD17-A1B2-3456`

- Automatically generated
- One-time use
- Easy to send via text message

---

## File Structure

```
dd1750_assistant/
├── app.py              # Flask app with access code system
├── vision_extractor.py # Claude Vision API
├── dd1750_generator.py # PDF generation
├── blank_1750.pdf      # DD1750 template
├── templates/
│   ├── index.html      # User interface  
│   └── admin.html      # Admin panel
├── requirements.txt
├── Procfile           
└── nixpacks.toml
```

---

## Important Notes

### Storage

Current version uses in-memory storage. This means:
- Access codes reset if server restarts
- User credits reset if server restarts

For production with many users, you'd want to add Redis or a database. Let me know if you need that.

### Server Restarts

Railway free tier may restart your app. To prevent losing codes:
- Generate codes right before selling them
- Or upgrade to a paid Railway plan for persistent servers
- Or let me know and I can add database storage

---

## Local Development

```bash
pip install -r requirements.txt

# Install poppler (for PDF conversion)
# Mac: brew install poppler
# Ubuntu: sudo apt install poppler-utils

export ANTHROPIC_API_KEY="sk-ant-..."
export ADMIN_PASSWORD="test123"
export SECRET_KEY="dev-secret"

python app.py
```

Open http://localhost:8000 (user) or http://localhost:8000/admin (admin)
