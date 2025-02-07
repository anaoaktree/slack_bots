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
- Make it async with aiothttp
- Add database and fix home tab
- Add more LLMs (decide if creating different apps or use commands)