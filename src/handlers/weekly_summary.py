from datetime import datetime, timedelta
from collections import Counter, defaultdict
import json
from config.settings import Settings
from utils.sentiment import analyze_sentiment
import random

class WeeklySummary:
    def __init__(self, app):
        self.app = app
        self.messages = []
        self.user_message_counts = Counter()
        self.topics = defaultdict(int)
        self.questions = []
        
        # Load book recommendations
        with open('src/data/book_recommendations.json', 'r') as f:
            self.book_recommendations = json.load(f)
    
    def process_message(self, message):
        """Process a new message for the weekly summary"""
        self.messages.append({
            'text': message.get('text', ''),
            'user': message['user'],
            'ts': message['ts'],
            'sentiment': analyze_sentiment(message.get('text', ''))
        })
        
        self.user_message_counts[message['user']] += 1
        self._extract_topics(message.get('text', ''))
        
        if message.get('text', '').strip().endswith('?'):
            self.questions.append(message)
    
    def _extract_topics(self, text):
        """Simple topic extraction based on keywords"""
        # This is a basic implementation - could be enhanced with NLP
        keywords = ['data', 'analytics', 'python', 'sql', 'dashboard']
        for keyword in keywords:
            if keyword.lower() in text.lower():
                self.topics[keyword] += 1
    
    def generate_and_post_summary(self):
        """Generate and post the weekly summary"""
        if not self.messages:
            return
            
        # Calculate overall mood score
        mood_score = sum(m['sentiment'] for m in self.messages) / len(self.messages)
        
        # Get top contributors
        top_users = self.user_message_counts.most_common(5)
        
        # Get top topics
        top_topics = sorted(self.topics.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Get random book recommendation
        recommendation = random.choice(self.book_recommendations)
        
        # Format the summary message
        summary = (
            "*📊 Weekly Channel Summary*\n\n"
            "*Top Contributors:*\n"
            + "\n".join(f"• <@{user}>: {count} messages" 
                       for user, count in top_users)
            + "\n\n*Popular Topics:*\n"
            + "\n".join(f"• {topic}: {count} mentions" 
                       for topic, count in top_topics)
            + f"\n\n*Channel Mood:* {'😊' if mood_score > 0 else '😐' if mood_score == 0 else '😟'}"
            + f"\n\n*📚 Weekly Reading Recommendation:*\n{recommendation['title']}"
            + f"\n_{recommendation['description']}_"
        )
        
        try:
            self.app.client.chat_postMessage(
                channel=Settings.SUMMARY_CHANNEL,
                text=summary,
                unfurl_links=False
            )
            
            # Reset weekly data
            self.messages = []
            self.user_message_counts.clear()
            self.topics.clear()
            self.questions = []
            
        except Exception as e:
            print(f"Error posting summary: {e}") 