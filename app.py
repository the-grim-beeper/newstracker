import streamlit as st
import feedparser
import time
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import re
import altair as alt
import threading
from collections import defaultdict
import pytz

# Set page configuration
st.set_page_config(
    page_title="Real-time News Tracker",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Apply custom CSS
st.markdown("""
<style>
    .main {
        background-color: #f5f7f9;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #f0f2f6;
        border-radius: 4px 4px 0px 0px;
        padding: 10px 16px;
        height: 40px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4e89ae;
        color: white;
    }
    .news-item {
        background-color: white;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 10px;
        border-left: 4px solid #4e89ae;
    }
    .term-highlight {
        background-color: #ffeb3b;
        padding: 0px 2px;
        border-radius: 3px;
    }
    .timestamp {
        color: #666;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'search_terms' not in st.session_state:
    st.session_state.search_terms = []
    
if 'tracking_data' not in st.session_state:
    st.session_state.tracking_data = {}
    
if 'articles' not in st.session_state:
    st.session_state.articles = defaultdict(list)
    
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()
    
if 'is_tracking' not in st.session_state:
    st.session_state.is_tracking = False
    
if 'start_time' not in st.session_state:
    st.session_state.start_time = datetime.now()

def fetch_google_news(search_term):
    """Fetch news from Google News RSS feed for a specific search term."""
    # Encode the search term for URL
    encoded_term = search_term.replace(' ', '+')
    
    # Different Google News RSS feed URLs to try
    urls = [
        f"https://news.google.com/rss/search?q={encoded_term}&hl=en-US&gl=US&ceid=US:en",
        f"https://news.google.com/news/rss/headlines/section/topic/{encoded_term.upper()}",
        f"https://news.google.com/news/rss/search/section/q/{encoded_term}/{encoded_term}?hl=en&gl=US"
    ]
    
    all_entries = []
    
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                for entry in feed.entries:
                    # Add the search term to the entry for reference
                    entry['search_term'] = search_term
                    all_entries.append(entry)
        except Exception as e:
            st.error(f"Error fetching news for term '{search_term}': {e}")
            continue
    
    return all_entries

def process_new_articles(entries, search_term):
    """Process new articles and update session state."""
    new_articles = []
    current_time = datetime.now()
    
    # Get existing article URLs for this term to avoid duplicates
    existing_urls = [article['link'] for article in st.session_state.articles[search_term]]
    
    for entry in entries:
        if entry.link not in existing_urls:
            # Check if the article contains the search term in title or summary
            title_match = re.search(search_term, entry.title, re.IGNORECASE)
            summary = entry.get('summary', '')
            summary_match = re.search(search_term, summary, re.IGNORECASE)
            
            if title_match or summary_match:
                article = {
                    'title': entry.title,
                    'link': entry.link,
                    'published': entry.get('published', ''),
                    'summary': summary,
                    'timestamp': current_time,
                    'search_term': search_term
                }
                new_articles.append(article)
                st.session_state.articles[search_term].append(article)
                
                # Update tracking data
                if search_term not in st.session_state.tracking_data:
                    st.session_state.tracking_data[search_term] = []
                
                st.session_state.tracking_data[search_term].append({
                    'timestamp': current_time,
                    'count': 1
                })
    
    return new_articles

def update_news():
    """Update news for all search terms."""
    if not st.session_state.search_terms:
        return
    
    st.session_state.last_update = datetime.now()
    
    for term in st.session_state.search_terms:
        entries = fetch_google_news(term)
        process_new_articles(entries, term)

def start_tracking():
    """Start tracking news mentions."""
    st.session_state.is_tracking = True
    st.session_state.start_time = datetime.now()
    st.session_state.last_update = datetime.now()
    
    # Clear existing data
    st.session_state.tracking_data = {}
    st.session_state.articles = defaultdict(list)
    
    # Initial update
    update_news()

def stop_tracking():
    """Stop tracking news mentions."""
    st.session_state.is_tracking = False

def get_time_series_data(search_term):
    """Get time series data for a search term."""
    if search_term not in st.session_state.tracking_data:
        return pd.DataFrame({'timestamp': [], 'count': []})
    
    df = pd.DataFrame(st.session_state.tracking_data[search_term])
    
    # If no data, return empty DataFrame
    if df.empty:
        return pd.DataFrame({'timestamp': [], 'count': []})
    
    # Resample data to minute intervals
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')
    
    # Create a date range from start time to now with minute frequency
    start_time = st.session_state.start_time
    end_time = datetime.now()
    full_range = pd.date_range(start=start_time, end=end_time, freq='1min')
    
    # Resample and fill with zeros
    resampled = df.resample('1min').sum().reindex(full_range, fill_value=0)
    resampled = resampled.reset_index()
    resampled.columns = ['timestamp', 'count']
    
    return resampled

def get_total_mentions():
    """Get total mentions for each search term."""
    totals = {}
    for term in st.session_state.search_terms:
        totals[term] = len(st.session_state.articles[term])
    return totals

def create_time_series_chart():
    """Create a time series chart for all search terms."""
    # Prepare data for Altair
    all_data = []
    
    for term in st.session_state.search_terms:
        df = get_time_series_data(term)
        if not df.empty:
            df['search_term'] = term
            all_data.append(df)
    
    if not all_data:
        return None
    
    # Combine all data
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # Create Altair chart
    chart = alt.Chart(combined_df).mark_line(point=True).encode(
        x=alt.X('timestamp:T', title='Time', axis=alt.Axis(format='%H:%M')),
        y=alt.Y('count:Q', title='Mentions'),
        color=alt.Color('search_term:N', title='Search Term'),
        tooltip=['timestamp:T', 'count:Q', 'search_term:N']
    ).properties(
        width=800,
        height=400,
        title='Real-time News Mentions'
    ).interactive()
    
    return chart

def highlight_term(text, term):
    """Highlight search term in text."""
    if not text or not term:
        return text
    
    pattern = re.compile(f'({re.escape(term)})', re.IGNORECASE)
    highlighted = pattern.sub(r'<span class="term-highlight">\1</span>', text)
    return highlighted

# Main app UI
st.title("📰 Real-time News Tracker")

with st.expander("About this app", expanded=False):
    st.write("""
    This app tracks mentions of your chosen search terms in Google News RSS feeds in real-time. 
    Enter up to three terms to track, and the app will update every minute to show new mentions.
    
    **Features:**
    - Track up to three search terms simultaneously
    - Visual representation of mentions over time
    - Links to the original news articles
    - Real-time updates every minute
    
    Get started by entering your search terms below and clicking "Start Tracking"!
    """)

# Sidebar for input
with st.sidebar:
    st.header("Search Configuration")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        term1 = st.text_input("Search Term 1", placeholder="Enter term")
        term2 = st.text_input("Search Term 2", placeholder="Enter term")
        term3 = st.text_input("Search Term 3", placeholder="Enter term")
    
    search_terms = [term for term in [term1, term2, term3] if term.strip()]
    
    if st.button("Set Search Terms"):
        if search_terms:
            st.session_state.search_terms = search_terms
            st.success(f"Set {len(search_terms)} search terms: {', '.join(search_terms)}")
        else:
            st.error("Please enter at least one search term")
    
    st.divider()
    
    if st.session_state.search_terms:
        st.write("Current search terms:")
        for term in st.session_state.search_terms:
            st.write(f"• {term}")
        
        if st.session_state.is_tracking:
            if st.button("Stop Tracking"):
                stop_tracking()
                st.success("Tracking stopped")
        else:
            if st.button("Start Tracking"):
                start_tracking()
                st.success("Tracking started")
    else:
        st.info("No search terms set. Please enter terms above.")
    
    if st.session_state.is_tracking:
        st.write(f"**Status:** Tracking active")
        st.write(f"Tracking since: {st.session_state.start_time.strftime('%H:%M:%S')}")
        st.write(f"Last update: {st.session_state.last_update.strftime('%H:%M:%S')}")

# Main content
if not st.session_state.search_terms:
    st.info("Please enter search terms in the sidebar to get started.")
else:
    # Auto-update check
    current_time = datetime.now()
    time_diff = (current_time - st.session_state.last_update).total_seconds()
    
    if st.session_state.is_tracking and time_diff >= 60:  # Update every minute
        update_news()
    
    # Dashboard layout
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Mentions Over Time")
        chart = create_time_series_chart()
        if chart:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No data available yet. Tracking will begin shortly...")
    
    with col2:
        st.subheader("Total Mentions")
        totals = get_total_mentions()
        
        for term in st.session_state.search_terms:
            count = totals.get(term, 0)
            st.metric(
                label=term, 
                value=count,
                delta=None
            )
    
    # Articles tabs
    st.subheader("Latest News Articles")
    
    if any(st.session_state.articles.values()):
        tabs = st.tabs(st.session_state.search_terms)
        
        for i, term in enumerate(st.session_state.search_terms):
            with tabs[i]:
                articles = st.session_state.articles.get(term, [])
                
                if articles:
                    articles.sort(key=lambda x: x['timestamp'], reverse=True)
                    
                    for article in articles:
                        with st.container():
                            st.markdown(f"""
                            <div class="news-item">
                                <h3><a href="{article['link']}" target="_blank">{highlight_term(article['title'], term)}</a></h3>
                                <p>{highlight_term(article.get('summary', ''), term)}</p>
                                <p class="timestamp">Found at: {article['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}</p>
                            </div>
                            """, unsafe_allow_html=True)
                else:
                    st.info(f"No articles found for '{term}' yet. Please wait for the next update.")
    else:
        st.info("No articles found yet. Tracking is active; articles will appear as they are found.")

    # Add an automatic refresh feature
    if st.session_state.is_tracking:
        time_to_next_update = 60 - time_diff
        st.write(f"Next update in approximately {int(time_to_next_update)} seconds")
        time.sleep(1)  # Short sleep to allow rerun
        st.experimental_rerun()

# Footer
st.markdown("---")
st.markdown("📰 **Real-time News Tracker** - Updates every minute when tracking is active.")
