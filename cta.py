#!/usr/bin/env python3

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from sys import exit
from urllib.parse import urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# Global constants
FEED_URL = 'https://www.npr.org/get/510208/render/partial/next?start={}'
EPS_PER_PAGE = 24
AUDIO_BITRATE = 128
DEFAULT_OUTPUT_PATH = Path(f'cartalk_{datetime.now().strftime('%Y%m%d%H%M%S')}.xml')
ITUNES_NAMESPACE = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}


@dataclass
class Episode:
    title: str
    description: str
    pub_date: datetime
    link: str
    audio_url: str
    duration: int
    size: str


def main(input_path, output_path):
    # If input file specified, parse episodes and fetch any newer ones from the web
    if input_path:
        root = get_xml_root(input_path)
        if root is None:
            return -1

        # Get channel (container of all item tags)
        channel = root.find('channel')
        if channel is None:
            print('ERROR: Input file does not appear to be valid podcast RSS.')
            return -1

        # Fetch the published date of the most recent episode
        last_episode_date = get_last_episode_date(channel)

        # Combine episode sources
        episodes = get_episodes_from_channel(channel) + get_episodes_from_web(last_episode_date)[::-1]
    else:
        episodes = get_episodes_from_web()

    generate_feed(episodes, output_path)

    return 0


def get_last_episode_date(channel):
    def get_date(path):
        date_str = channel.find(path).text
        return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')

    # Most recent episode is likely to be first or last of the channel
    return max(get_date('./item[1]/pubDate'), get_date('./item[last()]/pubDate'))


def get_xml_root(input_path):
    try:
        tree = ET.parse(input_path)
    except FileNotFoundError:
        print('ERROR: Input file not found.')
        return None
    except ET.ParseError:
        print('ERROR: Could not parse input.')
        return None

    return tree.getroot()


def get_episodes_from_channel(channel):
    episodes = []
    for item in channel.iter('item'):
        title = item.find('title').text
        pub_date = item.find('pubDate').text
        link = item.find('link').text
        description = item.find('itunes:summary', ITUNES_NAMESPACE).text
        duration = item.find('itunes:duration', ITUNES_NAMESPACE).text

        enclosure = item.find('enclosure').attrib
        audio_url = enclosure['url']
        size = enclosure['length']

        episode = Episode(title, description, pub_date, link, audio_url, duration, size)
        episodes.append(episode)

    return episodes


def get_episodes_from_web(last_episode_date=None):
    # List of episode objects
    episodes = []

    # Index of first episode of each page
    start = 0

    still_eps = True
    while still_eps:
        # HTTP GET list of episodes
        response = requests.get(FEED_URL.format(start + 1))

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
            # Pass over NPR+ exclusives (because we can't access them) to avoid indexing None
            if link_tag.a is None:
                continue

            # Get link
            link = link_tag.a['href']

            # Get publication date
            pub_date = datetime.strptime(teaser_tag.time['datetime'], '%Y-%m-%d')

            # As time and time zone not provided, default to noon UTC
            pub_date = pub_date.replace(tzinfo=timezone.utc) + timedelta(hours=12)

            # Stop parsing if we're past last episode date
            if last_episode_date and pub_date <= last_episode_date:
                still_eps = False
                break

            # Discard child tags and get description
            for child in teaser_tag.find_all():
                child.decompose()
            description = teaser_tag.get_text(strip=True)

            # Parse episode JSON
            data = json.loads(data_tag['data-audio'])
            title = data['title']
            audio_url = data['audioUrl']
            duration = data['duration']

            # Deconstruct audio URL parameters
            params = parse_qs(urlparse(audio_url).query)
            try:
                # Get file size from parameters
                size = params['size'][0]
            except KeyError:
                # If file size is not provided, estimate using duration and bitrate
                size = str((duration * AUDIO_BITRATE * 1000) // 8)

            # Construct episode object
            episode = Episode(title, description, pub_date, link, audio_url, duration, size)
            episodes.append(episode)

        start += EPS_PER_PAGE

    return episodes


def generate_feed(episodes, output_path):
    # Initialize feed generator
    feed = FeedGenerator()
    feed.load_extension('podcast')

    # Set values for show
    feed.title('Car Talk')
    feed.description(
        "America's funniest auto mechanics take calls from weary car owners all over the country, and crack wise while "
        "they diagnose Dodges and dismiss Diahatsus. You don't have to know anything about cars to love this one hour "
        "weekly laugh fest.")
    feed.image(
        url='https://media.npr.org/assets/img/2022/09/23/car-talk_tile_npr-network-01_sq-94167386915fb364047a98214d2d737df21465b1.jpg?s=1400',
        title='Car Talk', link='https://www.cartalk.com')
    feed.language('en')
    feed.link(href='https://www.cartalk.com')
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
    parser = argparse.ArgumentParser(
        prog='cta.py',
        description='Generate a podcast RSS feed containing every Car Talk episode currently hosted by NPR.')
    parser.add_argument('-i', '--input', type=Path, metavar='file',
                        help='file name of an existing feed (if specified, script will only check for newer episodes)')
    parser.add_argument('-o', '--output', type=Path, metavar='file', default=DEFAULT_OUTPUT_PATH,
                        help='output file name (defaults to cartalk_<timestamp>.xml in current working directory)')
    args = parser.parse_args()

    exit(main(args.input, args.output))
