from nltk.sentiment import SentimentIntensityAnalyzer
import nltk

# Download required NLTK data
try:
    nltk.data.find('vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

def analyze_sentiment(text):
    """
    Analyze the sentiment of text using NLTK's VADER sentiment analyzer.
    Returns a float between -1 (negative) and 1 (positive)
    """
    if not text:
        return 0.0
        
    sia = SentimentIntensityAnalyzer()
    scores = sia.polarity_scores(text)
    
    # Convert compound score to range -1 to 1
    return scores['compound'] 