#!/usr/bin/env python3

import logging
import os
import requests
import json
import sys
import webbrowser
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


CONSUMER_KEY = os.getenv("POCKET_CONSUMER_KEY")
BASE_URL = "https://getpocket.com"
REDIRECT_URL = "localhost"
GROQ_API_KEY = os.getenv("GROQ_API")

# Predefined list of candidate tags
TAG_LIST = ["ai/ml", "amazon", "apple", "auto", "books", "business", "design", "dev", "dogs", "edu", "facebook", "funny", "future", "google", "harvard", "history", "hockey", "life", "longreads", "math", "media", "microsoft", "misc", "music", "news", "parenting", "policy", "reviews", "science", "seattle", "security", "sfbay", "sports", "tech", "tv", "video games", "videos", "work"]


logger = logging.getLogger(__name__)

    
# POCKET API OAUTH FUNCTIONS
def post(url, data):
    headers = {
        "Content-Type": "application/json",
        "X-Accept": "application/json",
    }
    response = requests.post(url, json=data, headers=headers)
    error = response.headers.get("X-Error")
    
    # Debug info
    print(f"Status code: {response.status_code}")
    print(f"Response text: {response.text}")
    
    if error:
        logger.error(f"{response.status_code}, {error}")
        response.raise_for_status()
    elif response.text.strip():  # Only try to parse if there's content
        return response.json()
    else:
        return {}  # Return empty dict if no content


def request_code():
    payload = {
        "consumer_key": CONSUMER_KEY,
        "redirect_uri": REDIRECT_URL,
    }
    response = post(f"{BASE_URL}/v3/oauth/request", payload)
    return response["code"]


def request_access_token(code):
    payload = {
        "consumer_key": CONSUMER_KEY,
        "code": code,
    }
    response = post(f"{BASE_URL}/v3/oauth/authorize", payload)
    return response["access_token"]


def request_authorization(code):
    url = f"{BASE_URL}/auth/authorize?request_token={code}&redirect_uri={REDIRECT_URL}"
    webbrowser.open(url, new=2)


# GROQ API FUNCTIONS
def get_tag_suggestions(article):
    """
    Use Groq API to suggest tags from the TAG_LIST for a given article.
    
    Args:
        article: The article dictionary from Pocket API
        
    Returns:
        List of suggested tags
    """
    client = Groq(api_key=GROQ_API_KEY)
    
    # Extract article information
    title = article.get('resolved_title') or article.get('given_title') or 'No title'
    url = article.get('resolved_url') or article.get('given_url') or 'No URL'
    excerpt = article.get('excerpt', '')
    
    # Create prompt for Groq
    prompt = f"""
    I have an article with the following details:
    
    Title: {title}
    URL: {url}
    Excerpt: {excerpt}
    
    Based on this information, suggest 1-5 tags from the following list that best match this article's content:
    {', '.join(TAG_LIST)}
    
    Respond with ONLY the most relevant tags separated by commas. No explanations or additional text.
    """
    
    try:
        # Call Groq API
        print(f"Requesting tag suggestions for: {title}")
        
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that suggests relevant tags for articles."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=50
        )
        
        # Extract and process tags
        suggested_tags_text = response.choices[0].message.content.strip()
        suggested_tags = [tag.strip() for tag in suggested_tags_text.split(',')]
        
        # Filter to ensure we only have valid tags from our list
        valid_tags = [tag for tag in suggested_tags if tag in TAG_LIST]
        
        print(f"Suggested tags: {', '.join(valid_tags)}")
        return valid_tags
        
    except Exception as e:
        print(f"Error getting tag suggestions from Groq: {e}")
        return []


# POCKET API FUNCTIONS
def authenticate_pocket():
    code = request_code()
    request_authorization(code)
    input("Press any key after authorizing app...")
    return request_access_token(code)


# not doing add operations
# def add_item(url, token):
#     payload = {
#         "url": url,
#         "consumer_key": CONSUMER_KEY,
#         "access_token": token,
#     }
#     return post("https://getpocket.com/v3/add", payload)

def get_unread_articles(token):
    """
    Retrieves unread Pocket articles that do not have tags assigned.
    """
    url = "https://getpocket.com/v3/get"
    payload = {
        "consumer_key": CONSUMER_KEY,
        "access_token": token,
        "state": "unread",
        "detailType": "complete",
        "tag": "_untagged_"
    }
    print("Fetching unread articles from Pocket...")
    response = requests.post(url, json=payload)
    data = response.json()

    articles = []
    if "list" in data:
        for article_id, article in data["list"].items():
            # Check if the article has no tags (or an empty tag dict)
            if not article.get("tags"):
                articles.append((article_id, article))
    print(f"Found {len(articles)} unread articles without tags.\n")
    return articles

def add_tags_to_article(token, article_id, tags):
    """
    Add tags to a Pocket article
    
    Args:
        token: Pocket API access token
        article_id: ID of the article to tag
        tags: List of tags to add
        
    Returns:
        Boolean indicating success
    """
    if not tags:
        return False
        
    url = f"{BASE_URL}/v3/send"
    payload = {
        "consumer_key": CONSUMER_KEY,
        "access_token": token,
        "actions": json.dumps([
            {
                "action": "tags_add",
                "item_id": article_id,
                "tags": ",".join(tags)
            }
        ])
    }
    
    try:
        print(f"Adding tags to article {article_id}: {', '.join(tags)}")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("status", 0) == 1
    except Exception as e:
        print(f"Error adding tags: {e}")
        return False


def main():
    access_token = authenticate_pocket()
    print("Successfully authenticated with Pocket")
    
    # Get unread articles and store the result
    unread_articles = get_unread_articles(access_token)
    
    # Now you can process the unread articles
    if unread_articles:
        print(f"Processing {len(unread_articles)} unread articles...")
        for article_id, article in unread_articles:
            # Do something with each article
            print(f"Article: {article.get('resolved_title', 'No title')} - {article.get('resolved_url', 'No URL')}")
            # GROQ get relevant tags
            suggested_tags = get_tag_suggestions(article)
            # pocket print relevant tags, update
            add_tags_to_article(access_token, article_id, suggested_tags) 
    else:
        print("No unread articles found without tags.")


if __name__ == '__main__':
    sys.exit(main())
