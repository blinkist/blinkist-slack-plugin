import random
import json
from datetime import datetime, timedelta
from utils.sentiment import analyze_sentiment

class CommandHandler:
    def __init__(self, app):
        self.app = app
        # Load jokes
        with open('src/data/jokes.json', 'r') as f:
            self.jokes = json.load(f)['jokes']

    def tell_joke(self, respond):
        """Send a random data joke"""
        joke = random.choice(self.jokes)
        respond(f"Here's a data joke for you:\n\n:smile: _{joke}_")

    def analyze_channel_mood(self, channel_id, respond):
        """Analyze channel sentiment for the past week"""
        try:
            # Get timestamp for 1 week ago
            week_ago = (datetime.now() - timedelta(days=7)).timestamp()
            
            # Get channel history
            result = self.app.client.conversations_history(
                channel=channel_id,
                oldest=str(week_ago)
            )
            
            if not result['messages']:
                respond("No messages found in the past week!")
                return
            
            # Analyze sentiment for each message
            sentiments = []
            for message in result['messages']:
                if 'text' in message:
                    sentiment = analyze_sentiment(message['text'])
                    sentiments.append(sentiment)
            
            # Calculate average sentiment
            avg_sentiment = sum(sentiments) / len(sentiments)
            
            # Create mood indicator
            mood = "😊" if avg_sentiment > 0.2 else "😐" if avg_sentiment > -0.2 else "😟"
            
            # Format response
            response = (
                f"*Channel Mood Analysis (Past Week)*\n\n"
                f"Overall mood: {mood}\n"
                f"Average sentiment score: {avg_sentiment:.2f}\n"
                f"Messages analyzed: {len(sentiments)}\n\n"
                f"_Note: Scores range from -1 (negative) to +1 (positive)_"
            )
            
            respond(response)
            
        except Exception as e:
            respond(f"Error analyzing channel mood: {str(e)}") 