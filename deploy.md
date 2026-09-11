# VPS Deployment Guide with PM2

> **Optional.** The recommended setup is free on GitHub Actions — see [SETUP.md](SETUP.md).
> Use this guide only if you move the bot to your own VPS. It now uses Telegram:
> put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` wherever this guide says
> "Discord webhook URL".

This guide will help you deploy your Plaza Apartment Scraper on a VPS with PM2 for process management and monitoring.

## 🚀 Quick Setup

### 1. Upload Files to VPS
```bash
# Option 1: Using git (recommended)
git clone <your-repo-url>
cd Plaza-Apartment-scraper

# Option 2: Using scp
scp -r . user@your-vps-ip:/path/to/scraper/
```

### 2. Run Setup Script
```bash
chmod +x setup_vps.sh
./setup_vps.sh
```

### 3. Configure Environment
```bash
# Copy the example environment file
cp env.example .env

# Edit with your actual Discord webhook URL
nano .env
```

### 4. Start the Scraper
```bash
# Start with PM2
pm2 start ecosystem.config.js

# Save PM2 configuration (so it persists after reboot)
pm2 save
```

## 📊 Monitoring Options

### Option 1: Built-in PM2 Monitoring (Local)
```bash
# Terminal-based monitoring dashboard
pm2 monit

# View logs in real-time
pm2 logs plaza-scraper

# Check process status
pm2 list
```

### Option 2: PM2 Plus Web Dashboard (Recommended)
PM2 Plus provides a beautiful web dashboard for monitoring your applications.

1. **Sign up for PM2 Plus:**
   - Visit: https://app.pm2.io/
   - Create a free account
   - Create a new bucket for your server

2. **Link your server:**
   ```bash
   # You'll get these keys from PM2 Plus dashboard
   pm2 link <secret_key> <public_key>
   ```

3. **Access your dashboard:**
   - Go to https://app.pm2.io/
   - View real-time metrics, logs, and process status
   - Set up alerts and notifications

### Option 3: Custom Web Dashboard (Advanced)
If you want a custom solution, you can use PM2's programmatic API:

```bash
# Install PM2 web interface
npm install -g pm2-gui
pm2-gui start
```

## 🔧 PM2 Commands Reference

### Process Management
```bash
# Start the scraper
pm2 start ecosystem.config.js

# Stop the scraper
pm2 stop plaza-scraper

# Restart the scraper
pm2 restart plaza-scraper

# Delete the process
pm2 delete plaza-scraper

# Reload (zero-downtime restart)
pm2 reload plaza-scraper
```

### Monitoring & Logs
```bash
# View all processes
pm2 list

# Monitor processes (terminal dashboard)
pm2 monit

# View logs
pm2 logs plaza-scraper

# View only error logs
pm2 logs plaza-scraper --err

# View only output logs
pm2 logs plaza-scraper --out

# Clear logs
pm2 flush
```

### Configuration
```bash
# Save current PM2 configuration
pm2 save

# Resurrect saved processes (useful after reboot)
pm2 resurrect

# Show detailed process info
pm2 show plaza-scraper
```

## 🔄 Auto-Start on Boot

The setup script configures PM2 to start automatically on boot. If you need to set it up manually:

```bash
# Generate startup script
pm2 startup

# Follow the instructions PM2 provides
# Usually something like:
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u $USER --hp $HOME

# Save current processes
pm2 save
```

## 📁 File Structure

After setup, your directory should look like this:
```
Plaza-Apartment-scraper/
├── scraper.py              # Main scraper script
├── ecosystem.config.js     # PM2 configuration
├── requirements.txt        # Python dependencies
├── setup_vps.sh           # Setup script
├── env.example            # Environment template
├── .env                   # Your environment variables (create this)
├── logs/                  # PM2 logs directory
│   ├── err.log           # Error logs
│   ├── out.log           # Output logs
│   └── combined.log      # Combined logs
└── seen_listings.json    # Scraper state file
```

## 🛠 Troubleshooting

### Common Issues

1. **Python not found:**
   ```bash
   # Make sure Python3 is installed
   python3 --version
   
   # Update ecosystem.config.js if needed
   # Change interpreter to full path: '/usr/bin/python3'
   ```

2. **Permission denied:**
   ```bash
   # Make sure setup script is executable
   chmod +x setup_vps.sh
   
   # Check file permissions
   ls -la
   ```

3. **PM2 not starting on boot:**
   ```bash
   # Re-run startup command
   pm2 startup
   pm2 save
   ```

4. **Discord notifications not working:**
   ```bash
   # Check your .env file
   cat .env
   
   # Test webhook URL manually
   curl -X POST -H "Content-Type: application/json" \
        -d '{"content":"Test message"}' \
        YOUR_WEBHOOK_URL
   ```

### Viewing Detailed Logs
```bash
# Real-time logs with timestamps
pm2 logs plaza-scraper --timestamp

# Last 100 lines
pm2 logs plaza-scraper --lines 100

# Follow logs (like tail -f)
pm2 logs plaza-scraper -f
```

## 🔒 Security Considerations

1. **Environment Variables:** Never commit your `.env` file to version control
2. **Firewall:** Configure your VPS firewall appropriately
3. **Updates:** Keep your system and dependencies updated
4. **Monitoring:** Set up alerts for when the scraper goes down

## 📈 Performance Monitoring

With PM2 Plus, you can monitor:
- CPU and Memory usage
- Process uptime and restarts
- Error rates and logs
- Custom metrics
- Real-time notifications

## 🆘 Support

If you encounter issues:
1. Check the logs: `pm2 logs plaza-scraper`
2. Verify your environment variables
3. Ensure all dependencies are installed
4. Check PM2 process status: `pm2 list` 