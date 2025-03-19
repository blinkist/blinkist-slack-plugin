import re

def extract_mentions(text):
    """Extract user mentions from message text"""
    mention_pattern = r'<@([A-Z0-9]+)>'
    return re.findall(mention_pattern, text)

def extract_links(text):
    """Extract URLs from message text"""
    link_pattern = r'<(https?://[^>]+)>'
    return re.findall(link_pattern, text)

def clean_message(text):
    """Clean message text by removing mentions, links, and special characters"""
    # Remove user mentions
    text = re.sub(r'<@[A-Z0-9]+>', '', text)
    
    # Remove links
    text = re.sub(r'<https?://[^>]+>', '', text)
    
    # Remove special characters and extra whitespace
    text = re.sub(r'[^\w\s?!.]', ' ', text)
    text = ' '.join(text.split())
    
    return text.strip() 