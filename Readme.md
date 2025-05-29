# LLM Slack Assistant

A Slack bot powered by the most popular LLMs that provide intelligent responses and document analysis capabilities.

## Features

- **Supported LLMs**: Claude
- **Direct Messages**: Chat with Claude directly in DMs
- **Channel Interactions**: Mention the bot in channels to get responses
- **Thread Support**: Continues conversations in threads
- **PDF Processing**: Analyzes PDF files shared in conversations (up to 32MB)
- **Citations**: Provides citations for the responses
- **Home Tab**: Configure bot settings including:
  - API key configuration
  - Model selection
- **A/B Testing**: Generates two different response variants for user feedback
- **Interactive Voting**: Users can vote for their preferred response via Slack buttons
- **Database Storage**: Stores all tests, responses, and votes in SQLite (local) or MySQL (production)
- **Conversation Context**: Maintains conversation history for better responses


## Usage

- **Direct Messages**: Simply send a message to the bot in DMs
- **Channels**: Mention the bot using `@BotName` in any channel
- **PDF Analysis**: Share a PDF file in the conversation with the bot
- **Settings**: Access the home tab in Slack to configure your preferences


## Changelog

### Version 0.0.1
- Initial release
- Basic conversation capabilities in DMs and channels
- PDF document processing support (up to 32MB) with citations for claude sonnet
- Home tab with settings configuration
- Support for Claude 3.5 models (Sonnet and Haiku)



## Up next
- Make it async with aiothttp https://tools.slack.dev/bolt-python/concepts/async
- Add database and fix home tab
- Add more LLMs (decide if creating different apps or use commands)
- Check out https://github.com/seratch/ChatGPT-in-Slack

## A/B Testing Workflow

1. **User asks a question** → Bot is mentioned or sends DM
2. **Bot generates two responses**:
   - **Response A**: Claude Sonnet 4 (standard assistant prompt, temperature=0.3)
   - **Response B**: Claude Haiku 3.5 (creative prompt, temperature=1.0)
3. **Both responses are posted** with voting buttons
4. **User votes** for their preferred response
5. **Data is stored** for analysis and model improvement

## Database Schema

### Tables Created:

- **`ab_tests`**: Stores test metadata (user, channel, original prompt, context)
- **`ab_responses`**: Stores the two generated responses with model settings
- **`ab_votes`**: Stores user voting preferences

## Setup

### Prerequisites

- Python 3.8+
- Slack App with bot permissions
- Anthropic API key
- (Optional) MySQL database for production

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up environment variables:
```bash
# Required
CHACHIBT_APP_BOT_AUTH_TOKEN=your_slack_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional (for production MySQL)
MYSQL_HOST=your_mysql_host
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=your_mysql_database
```

3. Initialize database:
```bash
FLASK_APP=server.py python -m flask db init
FLASK_APP=server.py python -m flask db upgrade
```

4. Test the A/B functionality:
```bash
python test_ab_testing.py
```

### Slack App Configuration

Your Slack app needs these **Event Subscriptions**:
- `app_mention` - When bot is mentioned
- `message.channels` - Messages in channels
- `message.im` - Direct messages

**Interactive Components** endpoint: `https://yourdomain.com/interactive`

**Bot Token Scopes**:
- `app_mentions:read`
- `channels:history`
- `chat:write`
- `im:history`
- `im:write`

## API Endpoints

- `POST /event` - Slack event handler
- `POST /interactive` - Slack interactive component handler (button clicks)
- `GET /` - Health check

## Testing

Run the comprehensive test suite:
```bash
python test_ab_testing.py
```

This validates:
- ✅ Database schema and tables
- ✅ A/B test creation
- ✅ Response generation with both models
- ✅ Slack message formatting with buttons
- ✅ Vote recording and retrieval

## Production Deployment

1. **Set up MySQL** database with credentials in environment variables
2. **Configure Slack app** with your production URLs
3. **Deploy** using your preferred method (Docker, cloud platform, etc.)
4. **Run migrations**: `FLASK_APP=server.py python -m flask db upgrade`

The app automatically detects MySQL vs SQLite based on environment variables.

## Contributing

1. Test your changes with `python test_ab_testing.py`
2. Ensure all A/B testing functionality works
3. Update documentation for any new features

For questions about the A/B testing implementation, see `services/ab_testing.py` and `models.py`.