# Slack Analytics Bot

A Slack bot that helps maintain channel engagement, track questions, and provide weekly analytics summaries.

## Features

1. **Quiet Channel Nudge**
   - Monitors channel activity during working hours
   - Sends friendly reminders with data jokes when channels are inactive
   - Configurable quiet threshold (default: 4 hours)

2. **Question Tracking**
   - Automatically detects and tracks questions
   - Sends private reminders for unanswered questions
   - Suggests ways to improve question visibility

3. **Weekly Summary**
   - Generates comprehensive weekly channel analytics
   - Tracks top contributors and popular topics
   - Includes mood analysis and book recommendations
   - Posts every Friday at 4 PM (configurable)

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/slack-analytics-bot
   cd slack-analytics-bot
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   - Copy `.env.example` to `.env`
   - Fill in your Slack credentials and preferences
   ```bash
   cp .env.example .env
   ```

## Slack App Configuration

1. **Create a new Slack App**
   - Go to [api.slack.com/apps](https://api.slack.com/apps)
   - Click "Create New App"
   - Choose "From scratch"
   - Name your app and select your workspace

2. **Configure Bot Token Scopes**
   Navigate to "OAuth & Permissions" and add these scopes:
   - `channels:history`
   - `channels:read`
   - `chat:write`
   - `im:write`
   - `users:read`

3. **Enable Socket Mode**
   - Go to "Socket Mode"
   - Enable Socket Mode
   - Generate and save your app-level token

4. **Install the App**
   - Go to "Install App"
   - Click "Install to Workspace"
   - Copy the Bot User OAuth Token

5. **Update Environment Variables**
   Add these tokens to your `.env` file:
   ```
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_APP_TOKEN=xapp-your-app-token
   ```

## Configuration

Edit `.env` to customize the bot's behavior:

## Running the Bot

1. **Start the bot**
   ```bash
   python src/app.py
   ```

2. **Running in production**
   - Use a process manager like PM2 or Supervisor
   - Example PM2 configuration:
   ```bash
   pm2 start src/app.py --name "slack-analytics-bot" --interpreter python3
   ```

## Customization

### Adding Data Jokes
Edit `src/data/jokes.json` to add or modify jokes:

### Customizing Sentiment Analysis
The bot uses NLTK's VADER sentiment analyzer by default. To modify:
1. Edit `src/utils/sentiment.py`
2. Implement your own sentiment analysis logic
3. Return values between -1 (negative) and 1 (positive)

## Troubleshooting

Common issues and solutions:

1. **Bot not responding**
   - Check if tokens are correct in `.env`
   - Verify bot is invited to channels
   - Check logs for errors

2. **Missing permissions**
   - Review OAuth scopes in Slack App settings
   - Reinstall app to workspace

3. **Timezone issues**
   - Verify TIMEZONE in `.env`
   - Use IANA timezone names (e.g., "America/New_York")

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - feel free to use and modify as needed.
