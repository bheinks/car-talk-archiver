import json
from argparse import ArgumentParser
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

FEED_URL = 'https://www.npr.org/get/510208/render/partial/next?start={}'
EPS_PER_PAGE = 24


@dataclass
class Episode:
    title: str
    description: str
    pub_date: datetime
    link: str
    audio_url: str
    duration: int
    size: str


def main(output_path):
    print('Fetching episode metadata...', end=' ')
    episodes = fetch_episode_metadata()
    print('Done.')

    print('Generating rss.xml...', end=' ')
    generate_feed(episodes, output_path)
    print('Done.')


def fetch_episode_metadata():
    # List of episode objects
    episodes = []

    # Index of first episode of each page
    start = 0

    still_eps = True
    while still_eps:
        # HTTP GET list of episodes
        response = requests.get(FEED_URL.format(start+1))

        # Initialize bs4
        soup = BeautifulSoup(response.text, 'html.parser')

        # Parse metadata for episodes
        link_tags = soup.find_all('h2', class_='title')
        teaser_tags = soup.find_all('p', class_='teaser')
        data_tags = soup.find_all('div', class_='audio-module-controls-wrap')

        # Stop parsing if we've run out of episodes 
        if len(teaser_tags) < EPS_PER_PAGE:
            still_eps = False

        for link_tag, teaser_tag, data_tag in zip(link_tags, teaser_tags, data_tags):
            # Get link
            link = link_tag.a['href']

            # Get publication date
            pub_date = datetime.strptime(teaser_tag.time['datetime'], '%Y-%m-%d')

            # As time and time zone not provided, default to noon UTC
            pub_date = pub_date.replace(tzinfo=timezone.utc) + timedelta(hours=12)

            # Discard child tags and get description
            for child in teaser_tag.findChildren():
                child.decompose()
            description = teaser_tag.get_text(strip=True)

            # Parse episode JSON
            data = json.loads(data_tag['data-audio'])
            title = data['title']
            audio_url = data['audioUrl']
            duration = data['duration']

            # Get file size from header
            size = requests.get(audio_url, stream=True).headers['Content-length']
            
            # Construct episode object
            episode = Episode(title, description, pub_date, link, audio_url, duration, size)
            episodes.append(episode)
            print(title)
        
        start += EPS_PER_PAGE
    
    return episodes


def generate_feed(episodes, output_path):
    # Initialize feed generator
    feed = FeedGenerator()
    feed.load_extension('podcast')

    # Set values for show
    feed.title('Car Talk')
    feed.description("America's funniest auto mechanics take calls from weary car owners all over the country, and crack wise while they diagnose Dodges and dismiss Diahatsus. You don't have to know anything about cars to love this one hour weekly laugh fest.")
    feed.image(
        url='https://media.npr.org/assets/img/2022/09/23/car-talk_tile_npr-network-01_sq-94167386915fb364047a98214d2d737df21465b1.jpg?s=1400',
        title='Car Talk',
        link='http://www.cartalk.com'
    )
    feed.language('en')
    feed.link(href='http://www.cartalk.com')
    feed.copyright('Copyright 2001-2021 Tappet Brothers LLC - For Personal Use Only')
    
    # Set values for each episode
    for episode in episodes:
        entry = feed.add_entry()
        entry.title(episode.title)
        entry.description(episode.description)
        entry.pubDate(episode.pub_date)
        entry.link(href=episode.link)
        entry.enclosure(url=episode.audio_url, length=episode.size, type='audio/mpeg')
        entry.podcast.itunes_author('NPR')
        entry.podcast.itunes_duration(episode.duration)
        entry.podcast.itunes_explicit('no')
        entry.podcast.itunes_summary(episode.description)

    # Write feed to file
    feed.rss_file(output_path)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('output_path', type=Path)
    args = parser.parse_args()

    main(args.output_path)